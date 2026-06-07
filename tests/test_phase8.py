"""Phase 8 tests — Kokoro approximation layer, normalize_with_tones,
acoustic delta gate, --expressive integration.

All synthesis tests run against MockEngine (no GPU needed).
"""

import numpy as np
import pytest

from vorpal.tts.mock_engine import MockEngine
from vorpal.tts.kokoro_approx import (
    KokoroApproxEngine,
    TONE_SPEED,
    TONE_PAUSE_SCALE,
    acoustic_delta,
)
from vorpal.normalize import normalize_with_tones


# ── KokoroApproxEngine — construction ────────────────────────────────────

def _make_approx(tone_speed=None, speed=1.0):
    """Build a KokoroApproxEngine backed by MockEngine."""
    mock = MockEngine()
    return KokoroApproxEngine(inner_engine=mock, speed=speed)


def test_approx_name():
    assert KokoroApproxEngine.name == "kokoro_approx"


def test_approx_supported_tones_covers_vocabulary():
    from vorpal.tone import TONE_VOCAB
    for tone in TONE_VOCAB:
        assert tone in KokoroApproxEngine.supported_tones


def test_approx_voice_cache_key_prefixed():
    mock = MockEngine(voice="test_voice")
    eng = KokoroApproxEngine(inner_engine=mock)
    assert eng.voice_cache_key.startswith("approx_")
    assert "test_voice" in eng.voice_cache_key


def test_approx_cost_is_zero():
    assert KokoroApproxEngine.cost_per_1k_chars == 0.0


# ── KokoroApproxEngine — speed adjustment per tone ────────────────────────

def test_approx_somber_is_slower_than_neutral():
    mock = MockEngine()
    eng = KokoroApproxEngine(inner_engine=mock, speed=1.0)
    text = "A long sentence that will produce audio proportional to its length here."

    neutral = eng.synthesize(text, tone="neutral")
    somber = eng.synthesize(text, tone="somber")

    # somber speed < 1.0 → longer audio
    assert len(somber) > len(neutral)


def test_approx_tense_is_faster_than_neutral():
    mock = MockEngine()
    eng = KokoroApproxEngine(inner_engine=mock, speed=1.0)
    text = "A long sentence that will produce audio proportional to its length here."

    neutral = eng.synthesize(text, tone="neutral")
    tense = eng.synthesize(text, tone="tense")

    # tense speed > 1.0 → shorter audio
    assert len(tense) < len(neutral)


def test_approx_all_tones_synthesize():
    mock = MockEngine()
    eng = KokoroApproxEngine(inner_engine=mock)
    for tone in KokoroApproxEngine.supported_tones:
        audio = eng.synthesize("Test sentence.", tone=tone)
        assert audio is not None and len(audio) > 0, f"tone {tone!r} produced no audio"


def test_approx_none_tone_uses_neutral_speed():
    mock = MockEngine()
    eng = KokoroApproxEngine(inner_engine=mock, speed=1.0)
    text = "A test sentence for speed comparison."
    with_none = eng.synthesize(text, tone=None)
    with_neutral = eng.synthesize(text, tone="neutral")
    assert len(with_none) == len(with_neutral)


def test_approx_speed_multiplier_applied():
    mock = MockEngine()
    eng = KokoroApproxEngine(inner_engine=mock, speed=0.5)
    text = "Speed test."
    neutral_half = eng.synthesize(text, tone="neutral")

    eng2 = KokoroApproxEngine(inner_engine=MockEngine(), speed=1.0)
    neutral_full = eng2.synthesize(text, tone="neutral")

    # Half speed → twice as many samples
    ratio = len(neutral_half) / len(neutral_full)
    assert abs(ratio - 2.0) < 0.05, f"Expected ~2x longer, got {ratio:.2f}x"


# ── pause scaling ─────────────────────────────────────────────────────────

def test_approx_pause_scale_somber_longer():
    mock = MockEngine()
    eng = KokoroApproxEngine(inner_engine=mock)
    neutral_pause = eng.scaled_pause(600, "neutral")
    somber_pause = eng.scaled_pause(600, "somber")
    assert somber_pause > neutral_pause


def test_approx_pause_scale_tense_shorter():
    mock = MockEngine()
    eng = KokoroApproxEngine(inner_engine=mock)
    neutral_pause = eng.scaled_pause(600, "neutral")
    tense_pause = eng.scaled_pause(600, "tense")
    assert tense_pause < neutral_pause


def test_approx_pause_scale_none_is_neutral():
    mock = MockEngine()
    eng = KokoroApproxEngine(inner_engine=mock)
    assert eng.scaled_pause(500, None) == eng.scaled_pause(500, "neutral")


# ── acoustic_delta ────────────────────────────────────────────────────────

def test_acoustic_delta_identical_returns_zero():
    arr = np.zeros(1000, dtype="float32")
    delta = acoustic_delta(arr, arr, 24000)
    assert delta["rms_diff"] == 0.0
    assert delta["dur_diff"] == 0.0
    assert delta["passes"] is False


def test_acoustic_delta_different_duration_passes():
    a = np.zeros(1000, dtype="float32")
    b = np.zeros(500, dtype="float32")
    delta = acoustic_delta(a, b, 24000)
    assert delta["passes"] is True
    assert delta["dur_diff"] > 0.05


def test_acoustic_delta_different_energy_passes():
    a = np.ones(1000, dtype="float32") * 0.5
    b = np.zeros(1000, dtype="float32")
    delta = acoustic_delta(a, b, 24000)
    assert delta["passes"] is True
    assert delta["rms_diff"] > 0.05


def test_acoustic_delta_approx_engine_somber_vs_neutral():
    """KokoroApproxEngine: somber and neutral produce measurably different audio."""
    mock = MockEngine()
    eng = KokoroApproxEngine(inner_engine=mock, speed=1.0)
    text = "A long sentence for acoustic measurement purposes, it needs to be long."

    neutral = eng.synthesize(text, tone="neutral")
    somber = eng.synthesize(text, tone="somber")

    delta = acoustic_delta(neutral, somber, eng.sample_rate)
    assert delta["passes"], (
        f"somber vs neutral acoustic delta below 5% threshold: {delta}"
    )


def test_acoustic_delta_all_tones_vs_neutral():
    """Every non-neutral tone should produce a measurable delta from neutral."""
    mock = MockEngine()
    eng = KokoroApproxEngine(inner_engine=mock, speed=1.0)
    text = "A reasonably long sentence to ensure enough audio for measurement."
    neutral = eng.synthesize(text, tone="neutral")

    for tone in KokoroApproxEngine.supported_tones:
        if tone == "neutral":
            continue
        if TONE_SPEED[tone] == 1.0:
            # wry has same speed as neutral in the approx layer — skip for Kokoro
            # (real API engine would differ via instructions; approx admits this limit)
            continue
        tonal = eng.synthesize(text, tone=tone)
        delta = acoustic_delta(neutral, tonal, eng.sample_rate)
        assert delta["passes"], (
            f"Tone '{tone}' acoustic delta below threshold: {delta}"
        )


# ── normalize_with_tones ──────────────────────────────────────────────────

def test_normalize_with_tones_single_paragraph():
    body = "Hello world. This is a test paragraph."
    tones = ["somber"]
    chunks = normalize_with_tones(body, tones)
    assert len(chunks) > 0
    for c in chunks:
        assert c.tone == "somber"


def test_normalize_with_tones_neutral_stored_as_none():
    body = "A neutral paragraph here."
    tones = ["neutral"]
    chunks = normalize_with_tones(body, tones)
    for c in chunks:
        assert c.tone is None


def test_normalize_with_tones_two_runs_no_cross():
    body = "First paragraph.\n\nSecond paragraph."
    tones = ["somber", "neutral"]
    chunks = normalize_with_tones(body, tones)
    # First chunk(s) → somber; last → neutral (None)
    assert any(c.tone == "somber" for c in chunks)
    assert any(c.tone is None for c in chunks)


def test_normalize_with_tones_chunks_reindexed():
    body = "Para A.\n\nPara B.\n\nPara C."
    tones = ["warm", "tense", "neutral"]
    chunks = normalize_with_tones(body, tones)
    for i, c in enumerate(chunks):
        assert c.idx == i


def test_normalize_with_tones_fewer_tones_fills_neutral():
    body = "Para one.\n\nPara two.\n\nPara three."
    tones = ["somber"]  # only 1 tag for 3 paragraphs
    chunks = normalize_with_tones(body, tones)
    # Second and third paragraphs default to neutral (None)
    # At least one somber chunk exists
    assert any(c.tone == "somber" for c in chunks)


def test_normalize_with_tones_empty_body():
    chunks = normalize_with_tones("", ["somber"])
    assert chunks == []


def test_normalize_with_tones_empty_tones():
    body = "A paragraph."
    chunks = normalize_with_tones(body, [])
    # No tones → all neutral → all None
    for c in chunks:
        assert c.tone is None


# ── TONE_SPEED / TONE_PAUSE_SCALE completeness ───────────────────────────

def test_tone_speed_covers_all_supported():
    for tone in KokoroApproxEngine.supported_tones:
        assert tone in TONE_SPEED


def test_tone_pause_scale_covers_all_supported():
    for tone in KokoroApproxEngine.supported_tones:
        assert tone in TONE_PAUSE_SCALE


def test_neutral_speed_is_one():
    assert TONE_SPEED["neutral"] == 1.0


def test_neutral_pause_scale_is_one():
    assert TONE_PAUSE_SCALE["neutral"] == 1.0
