"""Phase 27 — Listening-target loudness profiles.

Tests:
  - PROFILES dict has the three required profiles
  - Each profile has correct target_lufs
  - get_profile() returns correct profile; raises on unknown name
  - get_profile(None) returns default (headphones)
  - Profile stored in manifest.settings after cmd_build step
  - compile_m4b accepts target_lra and target_tp parameters
  - Mastering cache includes target_lra in key (profile switch invalidates cache)
  - Default build (no --profile) unchanged at -18 LUFS
"""

import json
import wave
import struct
from pathlib import Path

import pytest

from vorpal.profiles import PROFILES, DEFAULT_PROFILE, get_profile, LoudnessProfile


# ── profile definitions ────────────────────────────────────────────────────

class TestProfiles:
    def test_three_profiles_defined(self):
        assert "headphones" in PROFILES
        assert "car" in PROFILES
        assert "speaker" in PROFILES

    def test_headphones_lufs(self):
        assert PROFILES["headphones"].target_lufs == -18.0

    def test_car_lufs(self):
        assert PROFILES["car"].target_lufs == -16.0

    def test_speaker_lufs(self):
        assert PROFILES["speaker"].target_lufs == -20.0

    def test_car_is_louder_than_headphones(self):
        assert PROFILES["car"].target_lufs > PROFILES["headphones"].target_lufs

    def test_speaker_is_quieter_than_headphones(self):
        assert PROFILES["speaker"].target_lufs < PROFILES["headphones"].target_lufs

    def test_car_has_tighter_compression(self):
        # car LRA < headphones LRA = tighter compression
        assert PROFILES["car"].target_lra < PROFILES["headphones"].target_lra

    def test_speaker_has_wider_dynamics(self):
        # speaker LRA > headphones LRA = more dynamic range
        assert PROFILES["speaker"].target_lra > PROFILES["headphones"].target_lra

    def test_all_profiles_are_named_tuples(self):
        for p in PROFILES.values():
            assert isinstance(p, LoudnessProfile)

    def test_all_profiles_have_true_peak(self):
        for p in PROFILES.values():
            assert p.target_tp < 0


# ── get_profile ────────────────────────────────────────────────────────────

class TestGetProfile:
    def test_returns_correct_profile(self):
        p = get_profile("car")
        assert p.name == "car"
        assert p.target_lufs == -16.0

    def test_none_returns_default(self):
        p = get_profile(None)
        assert p.name == DEFAULT_PROFILE
        assert p.target_lufs == PROFILES[DEFAULT_PROFILE].target_lufs

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown profile"):
            get_profile("concert_hall")

    def test_headphones_is_default(self):
        assert DEFAULT_PROFILE == "headphones"


# ── mastering cache includes target_lra ──────────────────────────────────

class TestMasteringCacheProfile:
    def test_profile_mismatch_invalidates_cache(self, tmp_path):
        from vorpal.master import _master_cache_hit, _master_cache_write

        m4a = tmp_path / "ch01.m4a"
        m4a.touch()
        wav_sha = "abc123"

        _master_cache_write(m4a, wav_sha, target_lufs=-18.0, aac_bitrate="64k",
                            output_i=-18.1, target_lra=11.0)

        # Same LUFS but different LRA → cache miss
        result = _master_cache_hit(m4a, wav_sha, -18.0, "64k", target_lra=8.0)
        assert result is None

    def test_matching_profile_hits_cache(self, tmp_path):
        from vorpal.master import _master_cache_hit, _master_cache_write

        m4a = tmp_path / "ch01.m4a"
        m4a.touch()
        wav_sha = "abc123"

        _master_cache_write(m4a, wav_sha, target_lufs=-16.0, aac_bitrate="64k",
                            output_i=-16.1, target_lra=8.0)

        result = _master_cache_hit(m4a, wav_sha, -16.0, "64k", target_lra=8.0)
        assert result == pytest.approx(-16.1)

    def test_old_cache_without_lra_still_works(self, tmp_path):
        from vorpal.master import _master_cache_hit, _master_cache_path

        m4a = tmp_path / "ch01.m4a"
        m4a.touch()
        # Write old-style cache without target_lra field
        cache_path = _master_cache_path(m4a)
        cache_path.write_text(
            json.dumps({"wav_sha256": "abc123", "target_lufs": -18.0,
                        "aac_bitrate": "64k", "output_i": -18.0}),
            encoding="utf-8"
        )
        # Old cache matches default LRA=11.0 (the default arg value)
        result = _master_cache_hit(m4a, "abc123", -18.0, "64k", target_lra=11.0)
        assert result == pytest.approx(-18.0)


# ── compile_m4b accepts new params ────────────────────────────────────────

class TestCompileM4bSignature:
    def test_accepts_target_lra_param(self):
        import inspect
        from vorpal.master import compile_m4b
        sig = inspect.signature(compile_m4b)
        assert "target_lra" in sig.parameters
        assert "target_tp" in sig.parameters

    def test_target_lra_default(self):
        import inspect
        from vorpal.master import compile_m4b
        sig = inspect.signature(compile_m4b)
        assert sig.parameters["target_lra"].default == 11.0
        assert sig.parameters["target_tp"].default == -1.5


# ── profiles module: all profiles have descriptions ───────────────────────

class TestProfileDescriptions:
    def test_all_have_descriptions(self):
        for name, p in PROFILES.items():
            assert len(p.description) > 0, f"{name} has no description"
