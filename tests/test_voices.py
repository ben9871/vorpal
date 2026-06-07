"""Tests for tts/voices.py — voice registry, blend cache keys, engine params."""

import pytest

from vorpal.tts.voices import (
    VOICE_REGISTRY,
    VoiceEntry,
    _params_cache_key,
    list_voices,
    resolve_voice,
)
from vorpal.tts.kokoro_engine import KokoroEngine


# ── registry shape ────────────────────────────────────────────────────────

def test_registry_has_minimum_count():
    assert len(VOICE_REGISTRY) >= 6


def test_registry_has_minimum_blends():
    blends = [v for v in VOICE_REGISTRY.values() if "blend" in v.params]
    assert len(blends) >= 2


def test_all_entries_have_required_fields():
    for vid, entry in VOICE_REGISTRY.items():
        assert isinstance(entry, VoiceEntry)
        assert entry.id == vid, f"entry.id mismatch for key '{vid}'"
        assert entry.display_name
        assert entry.engine
        assert isinstance(entry.params, dict)
        assert entry.description


def test_single_voice_params_have_voice_key():
    for entry in VOICE_REGISTRY.values():
        if "blend" not in entry.params:
            assert "voice" in entry.params


def test_blend_params_have_at_least_two_voices():
    for entry in VOICE_REGISTRY.values():
        if "blend" in entry.params:
            assert len(entry.params["blend"]) >= 2


def test_all_blend_weights_positive():
    for entry in VOICE_REGISTRY.values():
        if "blend" in entry.params:
            for weight in entry.params["blend"].values():
                assert weight > 0


# ── resolve_voice / list_voices ───────────────────────────────────────────

def test_resolve_voice_known():
    entry = resolve_voice("af_heart")
    assert entry is not None
    assert entry.id == "af_heart"
    assert entry.engine == "kokoro"


def test_resolve_voice_blend():
    entry = resolve_voice("blend_warm_bright")
    assert entry is not None
    assert "blend" in entry.params


def test_resolve_voice_unknown_returns_none():
    assert resolve_voice("not_a_real_voice_xyz") is None


def test_list_voices_returns_all():
    voices = list_voices()
    assert len(voices) == len(VOICE_REGISTRY)
    ids = {v.id for v in voices}
    assert ids == set(VOICE_REGISTRY.keys())


# ── _params_cache_key ─────────────────────────────────────────────────────

def test_cache_key_single_returns_voice_name():
    key = _params_cache_key({"voice": "af_heart"})
    assert key == "af_heart"


def test_cache_key_blend_returns_prefixed_hash():
    params = {"blend": {"af_heart": 0.6, "af_nova": 0.4}}
    key = _params_cache_key(params)
    assert key.startswith("blend_")
    assert len(key) == len("blend_") + 16


def test_cache_key_blend_deterministic():
    params = {"blend": {"af_heart": 0.6, "af_nova": 0.4}}
    assert _params_cache_key(params) == _params_cache_key(params)


def test_cache_key_blend_order_independent():
    a = _params_cache_key({"blend": {"af_heart": 0.6, "af_nova": 0.4}})
    b = _params_cache_key({"blend": {"af_nova": 0.4, "af_heart": 0.6}})
    assert a == b


def test_cache_key_blend_changes_on_weight_edit():
    a = _params_cache_key({"blend": {"af_heart": 0.6, "af_nova": 0.4}})
    b = _params_cache_key({"blend": {"af_heart": 0.7, "af_nova": 0.3}})
    assert a != b


def test_cache_key_blend_ignores_speed():
    a = _params_cache_key({"blend": {"af_heart": 0.6, "af_nova": 0.4}})
    b = _params_cache_key({"blend": {"af_heart": 0.6, "af_nova": 0.4}, "speed": 0.9})
    assert a == b


# ── KokoroEngine — params-based construction (no synthesis) ──────────────

def test_engine_from_single_params():
    eng = KokoroEngine(params={"voice": "af_nova"})
    assert eng.voice == "af_nova"
    assert eng.voice_cache_key == "af_nova"


def test_engine_from_blend_params():
    params = {"blend": {"af_heart": 0.65, "af_nova": 0.35}}
    eng = KokoroEngine(params=params)
    assert eng.voice is None
    key = eng.voice_cache_key
    assert key.startswith("blend_")


def test_engine_legacy_voice_string():
    eng = KokoroEngine(voice="bm_george", speed=0.9)
    assert eng.voice == "bm_george"
    assert eng.speed == 0.9
    assert eng.voice_cache_key == "bm_george"


def test_engine_speed_overrides_params():
    eng = KokoroEngine(params={"voice": "af_sky"}, speed=1.2)
    assert eng.speed == 1.2


def test_engine_blend_params_speed_override():
    params = {"blend": {"af_heart": 0.5, "bf_emma": 0.5}}
    eng = KokoroEngine(params=params, speed=0.85)
    assert eng.speed == 0.85


def test_engine_voice_cache_key_blend_matches_params_key():
    params = {"blend": {"am_fenrir": 0.55, "am_michael": 0.45}}
    eng = KokoroEngine(params=params)
    assert eng.voice_cache_key == _params_cache_key(params)


def test_engine_blend_cache_key_changes_on_recipe_edit():
    params_a = {"blend": {"af_heart": 0.6, "af_nova": 0.4}}
    params_b = {"blend": {"af_heart": 0.7, "af_nova": 0.3}}
    eng_a = KokoroEngine(params=params_a)
    eng_b = KokoroEngine(params=params_b)
    assert eng_a.voice_cache_key != eng_b.voice_cache_key


# ── cache key in synth.py uses voice_cache_key ────────────────────────────

def test_synth_cache_key_uses_blend_hash():
    """_cache_key in synth.py should embed the blend hash, not 'None'."""
    from vorpal.normalize import Chunk
    from vorpal.synth import _cache_key

    params = {"blend": {"af_heart": 0.5, "bf_emma": 0.5}}
    eng = KokoroEngine(params=params)
    chunk = Chunk(idx=0, text="Hello.", pause_after_ms=50, tone=None,
                  text_hash="abc123")
    key = _cache_key(chunk, eng)
    assert "blend_" in key
    assert "None" not in key


def test_synth_cache_key_single_uses_voice_name():
    from vorpal.normalize import Chunk
    from vorpal.synth import _cache_key

    eng = KokoroEngine(voice="bm_george")
    chunk = Chunk(idx=0, text="Hello.", pause_after_ms=50, tone=None,
                  text_hash="abc123")
    key = _cache_key(chunk, eng)
    assert "bm_george" in key
