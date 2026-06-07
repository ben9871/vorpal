"""Phase 14 — Draft-mode build tests.

All tests are deterministic (no TTS/Whisper/LLM) and use small WAV fixtures.
"""

import struct
import wave
from pathlib import Path

import numpy as np
import pytest

from vorpal.cli import _compile_draft_wav, build_parser


# ── WAV fixture helpers ───────────────────────────────────────────────────────


def _write_sine_wav(path: Path, freq: float = 440.0, duration_s: float = 0.5,
                    sample_rate: int = 24000) -> Path:
    """Write a short sine-wave WAV to path and return it."""
    n = int(sample_rate * duration_s)
    t = np.linspace(0, duration_s, n, endpoint=False)
    samples = (np.sin(2 * np.pi * freq * t) * 32767 * 0.5).astype("int16")
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(samples.tobytes())
    return path


def _wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as wf:
        return wf.getnframes() / wf.getframerate()


# ── _compile_draft_wav ────────────────────────────────────────────────────────


def test_draft_wav_creates_file(tmp_path):
    wav1 = _write_sine_wav(tmp_path / "ch1.wav", duration_s=0.5)
    chapter_results = [{"title": "Ch1", "wav": str(wav1)}]
    out = _compile_draft_wav(chapter_results, str(tmp_path / "book"), silence_ms=0)
    assert out.exists()
    assert out.suffix == ".wav"
    assert out.name == "book_draft.wav"


def test_draft_wav_duration_sum(tmp_path):
    wav1 = _write_sine_wav(tmp_path / "ch1.wav", duration_s=0.5)
    wav2 = _write_sine_wav(tmp_path / "ch2.wav", duration_s=0.5)
    chapter_results = [
        {"title": "Ch1", "wav": str(wav1)},
        {"title": "Ch2", "wav": str(wav2)},
    ]
    out = _compile_draft_wav(chapter_results, str(tmp_path / "book"), silence_ms=0)
    # Two 0.5s chapters, no silence → ~1.0s
    assert _wav_duration(out) == pytest.approx(1.0, abs=0.05)


def test_draft_wav_silence_padding(tmp_path):
    wav1 = _write_sine_wav(tmp_path / "ch1.wav", duration_s=0.5)
    wav2 = _write_sine_wav(tmp_path / "ch2.wav", duration_s=0.5)
    chapter_results = [
        {"title": "Ch1", "wav": str(wav1)},
        {"title": "Ch2", "wav": str(wav2)},
    ]
    out = _compile_draft_wav(chapter_results, str(tmp_path / "book"), silence_ms=500)
    # 0.5 + 0.5s silence (between chapters) + 0.5 = 1.5s
    assert _wav_duration(out) == pytest.approx(1.5, abs=0.05)


def test_draft_wav_skips_missing_wav(tmp_path):
    wav1 = _write_sine_wav(tmp_path / "ch1.wav", duration_s=0.5)
    chapter_results = [
        {"title": "Ch1", "wav": str(wav1)},
        {"title": "Ch2", "wav": str(tmp_path / "nonexistent.wav")},
    ]
    out = _compile_draft_wav(chapter_results, str(tmp_path / "book"), silence_ms=0)
    assert out.exists()
    # Only ch1 audio — ~0.5s
    assert _wav_duration(out) == pytest.approx(0.5, abs=0.05)


def test_draft_wav_is_readable_wav(tmp_path):
    wav1 = _write_sine_wav(tmp_path / "ch1.wav", duration_s=0.3)
    chapter_results = [{"title": "Ch1", "wav": str(wav1)}]
    out = _compile_draft_wav(chapter_results, str(tmp_path / "book"), silence_ms=0)
    with wave.open(str(out), "rb") as wf:
        assert wf.getnframes() > 0
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2


def test_draft_wav_preserves_sample_rate(tmp_path):
    wav1 = _write_sine_wav(tmp_path / "ch1.wav", duration_s=0.3, sample_rate=22050)
    chapter_results = [{"title": "Ch1", "wav": str(wav1)}]
    out = _compile_draft_wav(chapter_results, str(tmp_path / "book"), silence_ms=0)
    with wave.open(str(out), "rb") as wf:
        assert wf.getframerate() == 22050


def test_draft_wav_single_chapter_no_silence(tmp_path):
    wav1 = _write_sine_wav(tmp_path / "ch1.wav", duration_s=0.4)
    chapter_results = [{"title": "Ch1", "wav": str(wav1)}]
    out = _compile_draft_wav(chapter_results, str(tmp_path / "book"), silence_ms=1000)
    # Single chapter: no silence between chapters (silence only between chapters)
    assert _wav_duration(out) == pytest.approx(0.4, abs=0.05)


def test_draft_wav_empty_chapters(tmp_path):
    out = _compile_draft_wav([], str(tmp_path / "book"), silence_ms=0)
    assert out.exists()
    # Empty WAV: getnframes == 0
    with wave.open(str(out), "rb") as wf:
        assert wf.getnframes() == 0


# ── CLI --draft flag ──────────────────────────────────────────────────────────


def test_build_parser_has_draft_flag():
    parser = build_parser()
    args = parser.parse_args(["build", "book.pdf", "--draft"])
    assert args.draft is True


def test_build_parser_draft_default_false():
    parser = build_parser()
    args = parser.parse_args(["build", "book.pdf"])
    assert args.draft is False


def test_build_parser_draft_compatible_with_other_flags():
    parser = build_parser()
    args = parser.parse_args([
        "build", "book.pdf", "--draft",
        "--expressive", "--lexicon", "--voice", "af_heart",
    ])
    assert args.draft is True
    assert args.expressive is True
    assert args.lexicon is True
    assert args.voice == "af_heart"
