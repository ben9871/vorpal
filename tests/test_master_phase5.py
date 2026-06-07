"""Phase 5 additions to mastering: cache and chapter-count gate."""

import json
import wave
from pathlib import Path

import pytest

from vorpal.master import (
    _wav_sha256,
    _master_cache_hit,
    _master_cache_write,
    _master_cache_path,
    _check_m4b_chapters,
    SHORT_CHAPTER_THRESHOLD_S,
)


# ── mastering cache ──────────────────────────────────────────────────────

def _make_wav(path: Path, duration_s: float = 0.1, sample_rate: int = 24000):
    n = int(sample_rate * duration_s)
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * n)


def test_wav_sha256_deterministic(tmp_path):
    wav = tmp_path / "test.wav"
    _make_wav(wav)
    h1 = _wav_sha256(wav)
    h2 = _wav_sha256(wav)
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex


def test_master_cache_miss_no_m4a(tmp_path):
    wav = tmp_path / "ch.wav"
    _make_wav(wav)
    m4a = tmp_path / "ch.m4a"  # does not exist
    sha = _wav_sha256(wav)
    assert _master_cache_hit(m4a, sha, -18.0, "64k") is None


def test_master_cache_miss_no_sidecar(tmp_path):
    wav = tmp_path / "ch.wav"
    m4a = tmp_path / "ch.m4a"
    _make_wav(wav)
    m4a.write_bytes(b"fake m4a data")
    sha = _wav_sha256(wav)
    # No .cache.json written yet
    assert _master_cache_hit(m4a, sha, -18.0, "64k") is None


def test_master_cache_write_and_hit(tmp_path):
    wav = tmp_path / "ch.wav"
    m4a = tmp_path / "ch.m4a"
    _make_wav(wav)
    m4a.write_bytes(b"fake m4a data")
    sha = _wav_sha256(wav)

    _master_cache_write(m4a, sha, -18.0, "64k", -18.1)
    result = _master_cache_hit(m4a, sha, -18.0, "64k")
    assert result is not None
    assert abs(result - (-18.1)) < 0.01


def test_master_cache_miss_different_sha(tmp_path):
    wav = tmp_path / "ch.wav"
    m4a = tmp_path / "ch.m4a"
    _make_wav(wav)
    m4a.write_bytes(b"fake m4a data")
    sha = _wav_sha256(wav)
    _master_cache_write(m4a, sha, -18.0, "64k", -18.1)

    # Different WAV → different sha
    assert _master_cache_hit(m4a, "deadbeef" * 8, -18.0, "64k") is None


def test_master_cache_miss_different_lufs(tmp_path):
    wav = tmp_path / "ch.wav"
    m4a = tmp_path / "ch.m4a"
    _make_wav(wav)
    m4a.write_bytes(b"fake m4a data")
    sha = _wav_sha256(wav)
    _master_cache_write(m4a, sha, -18.0, "64k", -18.1)

    # Different target LUFS
    assert _master_cache_hit(m4a, sha, -23.0, "64k") is None


def test_master_cache_miss_different_bitrate(tmp_path):
    wav = tmp_path / "ch.wav"
    m4a = tmp_path / "ch.m4a"
    _make_wav(wav)
    m4a.write_bytes(b"fake m4a data")
    sha = _wav_sha256(wav)
    _master_cache_write(m4a, sha, -18.0, "64k", -18.1)

    assert _master_cache_hit(m4a, sha, -18.0, "128k") is None


def test_master_cache_path(tmp_path):
    m4a = tmp_path / "ch01_Intro.m4a"
    assert _master_cache_path(m4a) == tmp_path / "ch01_Intro.cache.json"


def test_master_cache_corrupt_json(tmp_path):
    wav = tmp_path / "ch.wav"
    m4a = tmp_path / "ch.m4a"
    _make_wav(wav)
    m4a.write_bytes(b"fake m4a data")
    sha = _wav_sha256(wav)
    _master_cache_path(m4a).write_text("NOT VALID JSON", encoding="utf-8")
    # Should return None gracefully, not raise
    assert _master_cache_hit(m4a, sha, -18.0, "64k") is None


# ── chapter gate (unit-level, no real M4B) ───────────────────────────────

def test_check_m4b_chapters_ffprobe_missing(tmp_path):
    fake = tmp_path / "fake.m4b"
    fake.write_bytes(b"not real m4b")
    result = _check_m4b_chapters(fake, 3)
    # Either returns None-ok (ffprobe not found) or an error string
    assert result.get("ok") is None or result.get("ok") is False or "error" in result


def test_short_chapter_threshold():
    assert SHORT_CHAPTER_THRESHOLD_S == 60
