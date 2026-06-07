"""Phase 7 tests — mock engine, cost machinery, tone pass-through, error handling.

All tests run against MockEngine (no API key, no network, no GPU).
APIEngine credential/API contract is integration-only; live items marked blocked.
"""

import math
import numpy as np
import pytest

from vorpal.tts.mock_engine import MockEngine
from vorpal.tts.api_engine import APIEngine, _resolve_openai_key
from vorpal.synth import estimate_synth_cost, _cache_key
from vorpal.normalize import Chunk


# ── MockEngine — basic synthesis ─────────────────────────────────────────

def test_mock_synth_returns_array():
    eng = MockEngine()
    audio = eng.synthesize("Hello world.")
    assert isinstance(audio, np.ndarray)
    assert audio.dtype == np.float32
    assert len(audio) > 0


def test_mock_synth_silence_for_neutral():
    eng = MockEngine()
    audio = eng.synthesize("Hello.", tone=None)
    assert np.all(audio == 0.0)


def test_mock_synth_silence_for_explicit_neutral():
    eng = MockEngine()
    audio = eng.synthesize("Hello.", tone="neutral")
    assert np.all(audio == 0.0)


def test_mock_synth_nonzero_for_somber():
    eng = MockEngine()
    audio = eng.synthesize("A grim day.", tone="somber")
    assert not np.all(audio == 0.0)


def test_mock_synth_tone_acoustic_delta():
    """Different tones produce measurably different waveforms."""
    eng = MockEngine()
    text = "The old house stood silent on the hill."
    neutral = eng.synthesize(text, tone="neutral")
    somber = eng.synthesize(text, tone="somber")
    tense = eng.synthesize(text, tone="tense")
    # Different tones → different non-zero content
    assert not np.allclose(somber, neutral)
    assert not np.allclose(tense, somber)


def test_mock_synth_deterministic():
    eng = MockEngine()
    a = eng.synthesize("Reproducible.", tone="warm")
    b = eng.synthesize("Reproducible.", tone="warm")
    assert np.array_equal(a, b)


def test_mock_synth_duration_proportional_to_text():
    eng = MockEngine()
    short = eng.synthesize("Hi.", tone="somber")
    long_ = eng.synthesize("A much longer sentence that goes on for quite a while.", tone="somber")
    assert len(long_) > len(short)


def test_mock_synth_speed_affects_duration():
    slow = MockEngine(speed=0.5).synthesize("Hello world.", tone="somber")
    fast = MockEngine(speed=2.0).synthesize("Hello world.", tone="somber")
    assert len(slow) > len(fast)


def test_mock_synth_fail_on_trigger():
    eng = MockEngine(fail_on="FAIL")
    with pytest.raises(RuntimeError, match="deliberately failing"):
        eng.synthesize("This will FAIL now.")


def test_mock_synth_fail_on_not_triggered():
    eng = MockEngine(fail_on="FAIL")
    audio = eng.synthesize("This is fine.")
    assert len(audio) > 0


def test_mock_supported_tones():
    assert "somber" in MockEngine.supported_tones
    assert "tense" in MockEngine.supported_tones
    assert "warm" in MockEngine.supported_tones
    assert "wry" in MockEngine.supported_tones


def test_mock_cost_is_zero():
    assert MockEngine.cost_per_1k_chars == 0.0


def test_mock_voice_cache_key():
    eng = MockEngine(voice="mock_narrator")
    assert eng.voice_cache_key == "mock_narrator"


# ── cost estimation ───────────────────────────────────────────────────────

def _make_chapters(texts):
    return [{"spoken_intro": "", "body": t, "skip": False} for t in texts]


def test_cost_estimate_free_engine():
    eng = MockEngine()
    chapters = _make_chapters(["Hello world.", "Another chapter."])
    chars, usd = estimate_synth_cost(chapters, eng)
    assert chars == len("Hello world.") + len("Another chapter.")
    assert usd == 0.0


def test_cost_estimate_paid_engine():
    from vorpal.tts.api_engine import APIEngine
    eng = APIEngine.__new__(APIEngine)
    eng.cost_per_1k_chars = 15.0 / 1000  # $0.015 per 1k chars
    text = "A" * 10_000   # 10 000 chars = 10k → $0.15
    chapters = _make_chapters([text])
    chars, usd = estimate_synth_cost(chapters, eng)
    assert chars == 10_000
    assert abs(usd - 0.15) < 1e-9


def test_cost_estimate_skips_excluded_chapters():
    eng = MockEngine()
    chapters = [
        {"spoken_intro": "", "body": "narrated", "skip": False},
        {"spoken_intro": "", "body": "skipped", "skip": True},
    ]
    chars, _ = estimate_synth_cost(chapters, eng)
    assert chars == len("narrated")


def test_cost_estimate_includes_spoken_intro():
    eng = MockEngine()
    chapters = [{"spoken_intro": "Chapter one.", "body": "Body text.", "skip": False}]
    chars, _ = estimate_synth_cost(chapters, eng)
    assert chars == len("Chapter one.") + len("Body text.")


def test_cost_estimate_empty_book():
    eng = MockEngine()
    chars, usd = estimate_synth_cost([], eng)
    assert chars == 0
    assert usd == 0.0


# ── APIEngine — credential and structure checks (no network) ──────────────

def test_api_engine_name():
    assert APIEngine.name == "openai"


def test_api_engine_supported_tones_superset_of_mock():
    for tone in MockEngine.supported_tones:
        assert tone in APIEngine.supported_tones


def test_api_engine_cost_positive():
    assert APIEngine.cost_per_1k_chars > 0.0


def test_api_engine_tone_instructions_cover_all_tones():
    """Every declared tone must have a non-empty instruction string."""
    for tone in APIEngine.supported_tones:
        assert tone in APIEngine._TONE_INSTRUCTIONS
        assert APIEngine._TONE_INSTRUCTIONS[tone].strip()


def test_api_engine_no_key_raises():
    import os
    orig_vorpal = os.environ.pop("VORPAL_OPENAI_KEY", None)
    orig_openai = os.environ.pop("OPENAI_API_KEY", None)
    try:
        eng = APIEngine()
        with pytest.raises(RuntimeError, match="VORPAL_OPENAI_KEY"):
            eng.synthesize("Hello.")
    finally:
        if orig_vorpal:
            os.environ["VORPAL_OPENAI_KEY"] = orig_vorpal
        if orig_openai:
            os.environ["OPENAI_API_KEY"] = orig_openai


def test_api_engine_resolve_key_prefers_vorpal_key(monkeypatch):
    monkeypatch.setenv("VORPAL_OPENAI_KEY", "vorpal-key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    assert _resolve_openai_key() == "vorpal-key"


def test_api_engine_resolve_key_fallback(monkeypatch):
    monkeypatch.delenv("VORPAL_OPENAI_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    assert _resolve_openai_key() == "openai-key"


def test_api_engine_resolve_key_missing(monkeypatch):
    monkeypatch.delenv("VORPAL_OPENAI_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert _resolve_openai_key() is None


# ── synth cache key uses voice_cache_key on mock engine ──────────────────

def test_cache_key_mock_engine_uses_voice():
    eng = MockEngine(voice="test_voice")
    chunk = Chunk(idx=0, text="Hello.", pause_after_ms=50, tone=None,
                  text_hash="abc123")
    key = _cache_key(chunk, eng)
    assert "test_voice" in key
    assert "mock" in key


def test_cache_key_tone_distinguishes_chunks():
    eng = MockEngine()
    base = Chunk(idx=0, text="Text.", pause_after_ms=50, tone=None,
                 text_hash="xyz")
    toned = Chunk(idx=0, text="Text.", pause_after_ms=50, tone="somber",
                  text_hash="xyz")
    key_neutral = _cache_key(base, eng)
    key_somber = _cache_key(toned, eng)
    assert key_neutral != key_somber


# ── registry contains OpenAI voices ──────────────────────────────────────

def test_registry_has_openai_voices():
    from vorpal.tts.voices import VOICE_REGISTRY
    openai_voices = [v for v in VOICE_REGISTRY.values() if v.engine == "openai"]
    assert len(openai_voices) >= 1


def test_openai_voice_params_have_voice_key():
    from vorpal.tts.voices import VOICE_REGISTRY
    for v in VOICE_REGISTRY.values():
        if v.engine == "openai":
            assert "voice" in v.params


# ── WAV decoder (no network) ──────────────────────────────────────────────

def test_wav_decoder_roundtrip():
    """_wav_bytes_to_array should decode a minimal PCM WAV back to float32."""
    import struct, io
    from vorpal.tts.api_engine import _wav_bytes_to_array

    sample_rate = 24000
    samples = np.array([0.0, 0.5, -0.5, 0.0], dtype="float32")
    pcm = (samples * 32767).astype("<i2").tobytes()

    buf = io.BytesIO()
    fmt_chunk = struct.pack("<4sIHHIIHH",
        b"fmt ", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16)
    data_chunk = struct.pack("<4sI", b"data", len(pcm)) + pcm
    body = fmt_chunk + data_chunk
    buf.write(struct.pack("<4sI4s", b"RIFF", 4 + len(body), b"WAVE"))
    buf.write(body)

    result = _wav_bytes_to_array(buf.getvalue())
    assert result is not None
    assert len(result) == 4
    # Should be close to original (int16 quantisation)
    assert np.allclose(result, samples, atol=5e-5)
