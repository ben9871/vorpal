"""Phase 16 — Batched TTS on GPU tests.

All tests are deterministic (MockEngine, no GPU or Kokoro required).
"""

import wave
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from vorpal.tts.mock_engine import MockEngine
from vorpal.tts.base import TTSEngine
from vorpal.tts.kokoro_engine import KokoroEngine
from vorpal.synth import _batch_synth_uncached, _cache_key
from vorpal.normalize import Chunk


# ── TTSEngine interface ───────────────────────────────────────────────────────


def test_ttengine_base_has_supports_batch():
    assert hasattr(TTSEngine, "supports_batch")
    assert TTSEngine.supports_batch is False


def test_ttengine_base_has_synthesize_batch():
    assert callable(getattr(TTSEngine, "synthesize_batch", None))


def test_kokoro_engine_supports_batch():
    assert KokoroEngine.supports_batch is True


def test_mock_engine_supports_batch():
    assert MockEngine.supports_batch is True


def test_ttengine_default_batch_falls_back_to_synthesize():
    """TTSEngine.synthesize_batch() calls synthesize() for each text."""
    engine = MockEngine()
    texts = ["Hello world.", "Goodbye world."]
    results = engine.synthesize_batch(texts)
    assert len(results) == 2
    for r in results:
        assert r is not None
        assert len(r) > 0


def test_mock_engine_synthesize_batch_returns_list():
    engine = MockEngine()
    results = engine.synthesize_batch(["one", "two", "three"])
    assert isinstance(results, list)
    assert len(results) == 3


def test_mock_engine_synthesize_batch_empty():
    engine = MockEngine()
    results = engine.synthesize_batch([])
    assert results == []


def test_mock_engine_synthesize_batch_tone_passed():
    engine = MockEngine()
    results_neutral = engine.synthesize_batch(["test text"], tone=None)
    results_somber = engine.synthesize_batch(["test text"], tone="somber")
    # MockEngine uses tone frequency — different tones yield different audio
    assert not np.allclose(results_neutral[0], results_somber[0])


# ── _batch_synth_uncached ─────────────────────────────────────────────────────


def _make_chunk(idx, text, tone=None):
    from vorpal.normalize import _text_hash
    return Chunk(idx=idx, text=text, pause_after_ms=100, tone=tone,
                 text_hash=_text_hash(text))


def test_batch_synth_writes_uncached_chunks(tmp_path):
    engine = MockEngine()
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    chunks = [_make_chunk(0, "Alpha"), _make_chunk(1, "Beta"), _make_chunk(2, "Gamma")]
    written = _batch_synth_uncached(chunks, engine, cache_dir)
    assert written == {0, 1, 2}
    for c in chunks:
        assert (cache_dir / _cache_key(c, engine)).exists()


def test_batch_synth_skips_existing_cache(tmp_path):
    engine = MockEngine()
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    chunks = [_make_chunk(0, "Alpha"), _make_chunk(1, "Beta")]
    # Pre-populate cache for chunk 0
    pre_cache = cache_dir / _cache_key(chunks[0], engine)
    audio = engine.synthesize("Alpha")
    sf.write(str(pre_cache), audio, engine.sample_rate)
    written = _batch_synth_uncached(chunks, engine, cache_dir)
    # Only chunk 1 was written (chunk 0 was pre-cached)
    assert 0 not in written
    assert 1 in written


def test_batch_synth_empty_chunks(tmp_path):
    engine = MockEngine()
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    written = _batch_synth_uncached([], engine, cache_dir)
    assert written == set()


def test_batch_synth_all_already_cached(tmp_path):
    engine = MockEngine()
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    chunks = [_make_chunk(0, "Already cached")]
    pre_cache = cache_dir / _cache_key(chunks[0], engine)
    audio = engine.synthesize("Already cached")
    sf.write(str(pre_cache), audio, engine.sample_rate)
    written = _batch_synth_uncached(chunks, engine, cache_dir)
    assert written == set()


def test_batch_synth_groups_by_tone(tmp_path):
    """Chunks with different tones are batch-processed separately but all written."""
    engine = MockEngine()
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    chunks = [
        _make_chunk(0, "Neutral text", tone=None),
        _make_chunk(1, "Somber text", tone="somber"),
        _make_chunk(2, "Tense text", tone="tense"),
    ]
    written = _batch_synth_uncached(chunks, engine, cache_dir)
    assert written == {0, 1, 2}
    for c in chunks:
        assert (cache_dir / _cache_key(c, engine)).exists()


def test_batch_synth_cache_files_are_valid_wav(tmp_path):
    engine = MockEngine()
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    chunks = [_make_chunk(0, "Test sentence for audio.")]
    _batch_synth_uncached(chunks, engine, cache_dir)
    cache_path = cache_dir / _cache_key(chunks[0], engine)
    data, sr = sf.read(str(cache_path))
    assert sr == engine.sample_rate
    assert len(data) > 0


def test_batch_synth_per_tone_audio_differs(tmp_path):
    """Batch writes different audio for different tones."""
    engine = MockEngine()
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    text = "Same text, different tone."
    c_neutral = _make_chunk(0, text, tone=None)
    c_somber = _make_chunk(1, text, tone="somber")
    _batch_synth_uncached([c_neutral, c_somber], engine, cache_dir)
    audio_neutral, _ = sf.read(str(cache_dir / _cache_key(c_neutral, engine)))
    audio_somber, _ = sf.read(str(cache_dir / _cache_key(c_somber, engine)))
    assert not np.allclose(audio_neutral, audio_somber[:len(audio_neutral)])
