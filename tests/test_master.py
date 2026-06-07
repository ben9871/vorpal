"""Unit and integration tests for Phase-4 master.py."""

import json
import math
import struct
import subprocess
import wave
from pathlib import Path

import pytest

from vorpal.master import (
    LoudnessResult,
    _compute_chapter_timestamps,
    _parse_loudnorm_json,
    _write_concat_list,
    _write_ffmetadata,
    _write_report_md,
    compile_m4b,
)
from vorpal.synth import SynthReport
from vorpal.binaries import find_ffmpeg, find_ffprobe

needs_ffmpeg = pytest.mark.skipif(
    find_ffmpeg() is None, reason="ffmpeg not installed"
)


# ── helpers ───────────────────────────────────────────────────────────────

def _make_wav(path: Path, duration_s: float = 1.0,
              freq: int = 440, sample_rate: int = 24000) -> Path:
    """Write a sine-wave mono WAV file at the given sample rate."""
    n_frames = int(sample_rate * duration_s)
    samples = [
        int(16000 * math.sin(2 * math.pi * freq * i / sample_rate))
        for i in range(n_frames)
    ]
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack(f"<{n_frames}h", *samples))
    return path


# ── test_chapter_timestamps ───────────────────────────────────────────────

def test_chapter_timestamps_basic():
    results = [
        {"title": "Ch1", "wav": Path("ch1.wav"), "duration_ms": 60_000},
        {"title": "Ch2", "wav": Path("ch2.wav"), "duration_ms": 90_000},
        {"title": "Ch3", "wav": Path("ch3.wav"), "duration_ms": 45_000},
    ]
    starts = _compute_chapter_timestamps(results, silence_ms=1500)
    assert starts[0] == 0
    assert starts[1] == 60_000 + 1500     # 61500
    assert starts[2] == 61_500 + 90_000 + 1500  # 153000
    assert len(starts) == 3


def test_chapter_timestamps_zero_silence():
    results = [
        {"title": "X", "wav": Path("x.wav"), "duration_ms": 10_000},
        {"title": "Y", "wav": Path("y.wav"), "duration_ms": 20_000},
    ]
    starts = _compute_chapter_timestamps(results, silence_ms=0)
    assert starts == [0, 10_000]


def test_chapter_timestamps_single():
    results = [{"title": "Only", "wav": Path("a.wav"), "duration_ms": 5_000}]
    assert _compute_chapter_timestamps(results, silence_ms=2000) == [0]


# ── test_ffmetadata_generation ────────────────────────────────────────────

def test_ffmetadata_generation(tmp_path):
    results = [
        {"title": "Introduction",  "wav": Path("a.wav"), "duration_ms": 120_000},
        {"title": "Chapter One",   "wav": Path("b.wav"), "duration_ms": 300_000},
    ]
    starts = _compute_chapter_timestamps(results, silence_ms=1500)
    meta = tmp_path / "test.ffmeta"
    _write_ffmetadata(meta, results, starts, title="My Book", author="J. Smith")
    text = meta.read_text(encoding="utf-8")

    assert text.startswith(";FFMETADATA1\n")
    assert "title=My Book\n" in text
    assert "artist=J. Smith\n" in text
    assert "genre=Audiobook\n" in text
    assert "[CHAPTER]\n" in text
    assert "TIMEBASE=1/1000\n" in text
    assert "START=0\n" in text
    # Ch1 end = ch2 start = 120000 + 1500 = 121500
    assert "END=121500\n" in text
    assert "START=121500\n" in text
    assert "title=Introduction\n" in text
    assert "title=Chapter One\n" in text


def test_ffmetadata_last_chapter_end(tmp_path):
    """Last chapter END should be start + duration, not start + duration + silence."""
    results = [
        {"title": "Only", "wav": Path("a.wav"), "duration_ms": 60_000},
    ]
    starts = _compute_chapter_timestamps(results, silence_ms=1500)
    meta = tmp_path / "meta.ffmeta"
    _write_ffmetadata(meta, results, starts, title="", author="")
    text = meta.read_text(encoding="utf-8")
    assert "END=60000\n" in text  # 0 + 60000, no trailing silence


def test_ffmetadata_no_title_author(tmp_path):
    results = [{"title": "Ch", "wav": Path("a.wav"), "duration_ms": 1000}]
    starts = _compute_chapter_timestamps(results, silence_ms=0)
    meta = tmp_path / "meta.ffmeta"
    _write_ffmetadata(meta, results, starts, title="", author="")
    text = meta.read_text(encoding="utf-8")
    assert "title=\n" not in text
    assert "artist=\n" not in text


# ── test_concat_list ──────────────────────────────────────────────────────

def test_write_concat_list(tmp_path):
    paths = [
        tmp_path / "chapter_01.m4a",
        tmp_path / "silence.m4a",
        tmp_path / "chapter_02.m4a",
    ]
    out = tmp_path / "concat.txt"
    _write_concat_list(out, paths)
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    for line, p in zip(lines, paths):
        assert line.startswith("file '")
        assert p.name in line


# ── test_loudnorm_stats_parse ─────────────────────────────────────────────

LOUDNORM_STDERR = (
    "size=N/A time=00:00:30.05 bitrate=N/A speed=44.3x\n"
    "[Parsed_loudnorm_0 @ 0x55abc1234000] \n"
    "{\n"
    '\t"input_i" : "-21.75",\n'
    '\t"input_tp" : "-18.06",\n'
    '\t"input_lra" : "0.00",\n'
    '\t"input_thresh" : "-31.75",\n'
    '\t"output_i" : "-17.95",\n'
    '\t"output_tp" : "-14.27",\n'
    '\t"output_lra" : "0.00",\n'
    '\t"output_thresh" : "-27.95",\n'
    '\t"normalization_type" : "dynamic",\n'
    '\t"target_offset" : "-0.05"\n'
    "}\n"
)


def test_loudnorm_stats_parse_pass1():
    stats = _parse_loudnorm_json(LOUDNORM_STDERR)
    assert stats["input_i"] == "-21.75"
    assert stats["output_i"] == "-17.95"
    assert stats["target_offset"] == "-0.05"
    assert stats["input_thresh"] == "-31.75"


def test_loudnorm_stats_parse_no_json_raises():
    with pytest.raises(ValueError, match="No loudnorm JSON"):
        _parse_loudnorm_json("ffmpeg: error: no such file\n")


def test_loudnorm_stats_parse_extracts_last_block():
    """When there are multiple { in stderr, rfind picks the JSON block."""
    stderr = (
        "some {partial thing\n"
        "[loudnorm @ 0xdeadbeef] \n"
        '{\n\t"input_i" : "-20.0",\n\t"output_i" : "-18.0",\n'
        '\t"input_lra" : "1.0",\n\t"input_tp" : "-10.0",\n'
        '\t"input_thresh" : "-30.0",\n\t"target_offset" : "0.0"\n}\n'
    )
    stats = _parse_loudnorm_json(stderr)
    assert stats["input_i"] == "-20.0"


# ── test_report_md_generation ─────────────────────────────────────────────

def test_report_md_generation(tmp_path):
    qa = {
        "pages_flagged": [12, 45],
        "mean_ocr_confidence": 0.93,
        "header_lines_removed": 22,
        "footnotes_separated": 30,
    }
    synth_report = SynthReport(
        done=1919, cached=84, retried=0, failed=0,
        lint_issues=[],
        failed_chunks=[],
    )
    loudness = [
        LoudnessResult("Chapter One", input_i=-21.5, output_i=-18.1, within_gate=True),
        LoudnessResult("Chapter Two", input_i=-20.0, output_i=-17.8, within_gate=True),
    ]
    chapter_results = [
        {"title": "Chapter One", "wav": Path("a.wav"), "duration_ms": 120_000},
        {"title": "Chapter Two", "wav": Path("b.wav"), "duration_ms": 300_000},
    ]
    report_path = tmp_path / "report.md"
    output_path = tmp_path / "book.m4b"
    output_path.touch()

    _write_report_md(
        report_path, qa, synth_report, loudness, output_path, chapter_results,
        target_lufs=-18.0,
    )

    text = report_path.read_text(encoding="utf-8")
    assert "# Audiobook Build Report" in text
    assert "1919" in text
    assert "84" in text
    assert "0.93" in text
    assert "Chapter One" in text
    assert "-18.1" in text
    assert "PASS" in text
    assert "22" in text       # header lines removed
    assert "12" in text       # flagged page
    assert "PASS" in text


def test_report_md_loudness_failure(tmp_path):
    """FAIL chapters are flagged in the report."""
    qa = {}
    synth_report = SynthReport(done=10, cached=0, retried=0, failed=0)
    loudness = [
        LoudnessResult("Ch1", input_i=-25.0, output_i=-16.5, within_gate=False),
    ]
    chapter_results = [{"title": "Ch1", "wav": Path("a.wav"), "duration_ms": 5000}]
    report_path = tmp_path / "report.md"
    output_path = tmp_path / "book.m4b"
    output_path.touch()

    _write_report_md(
        report_path, qa, synth_report, loudness, output_path, chapter_results,
    )
    text = report_path.read_text(encoding="utf-8")
    assert "FAIL" in text


def test_report_md_no_synth_report(tmp_path):
    qa = {}
    report_path = tmp_path / "report.md"
    output_path = tmp_path / "book.m4b"
    output_path.touch()
    _write_report_md(
        report_path, qa, None, [],
        output_path, [{"title": "Ch", "wav": Path("a.wav"), "duration_ms": 1000}],
    )
    text = report_path.read_text(encoding="utf-8")
    assert "not available" in text


# ── integration: compile_m4b with real ffmpeg ─────────────────────────────

@needs_ffmpeg
@pytest.mark.integration
def test_compile_m4b_integration(tmp_path):
    """End-to-end: two synthetic WAVs → compile_m4b → .m4b with chapter markers."""
    chapters_dir = tmp_path / "chapters"
    chapters_dir.mkdir()
    wav1 = _make_wav(chapters_dir / "chapter_01_intro.wav", duration_s=1.0, freq=440)
    wav2 = _make_wav(chapters_dir / "chapter_02_main.wav", duration_s=1.0, freq=880)

    chapter_results = [
        {"title": "Introduction", "wav": wav1, "duration_ms": 1000},
        {"title": "Main Chapter", "wav": wav2, "duration_ms": 1000},
    ]
    output_stem = str(tmp_path / "test_book")
    m4b = compile_m4b(
        chapter_results,
        output_stem,
        title="Test Book",
        author="Test Author",
        inter_chapter_silence_ms=500,
        work_dir=tmp_path / "workdir",
    )

    assert m4b.exists(), "M4B file was not created"
    assert m4b.suffix == ".m4b"
    assert m4b.stat().st_size > 1024

    # Verify report.md was created
    report = Path(f"{output_stem}_report.md")
    assert report.exists()
    report_text = report.read_text(encoding="utf-8")
    assert "# Audiobook Build Report" in report_text
    assert "Introduction" in report_text

    # Verify MP3 side product
    mp3_dir = Path(f"{output_stem}_chapters_mp3")
    assert mp3_dir.exists()
    mp3_files = list(mp3_dir.glob("*.mp3"))
    assert len(mp3_files) == 2

    # Verify chapter markers via ffprobe (if available)
    ffprobe = find_ffprobe()
    if ffprobe is None:
        pytest.skip("ffprobe not available for chapter-marker verification")

    result = subprocess.run(
        [ffprobe, "-v", "quiet", "-print_format", "json",
         "-show_chapters", str(m4b)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"ffprobe failed: {result.stderr}"

    chapters_data = json.loads(result.stdout).get("chapters", [])
    assert len(chapters_data) == 2, f"Expected 2 chapters, got {len(chapters_data)}"
    assert chapters_data[0]["tags"]["title"] == "Introduction"
    assert chapters_data[1]["tags"]["title"] == "Main Chapter"

    # Ch1 starts at 0
    ch1_start_ms = int(float(chapters_data[0]["start_time"]) * 1000)
    assert ch1_start_ms == 0

    # Ch2 should start at ~1000 + 500 = 1500 ms (±150 ms for AAC frame rounding)
    ch2_start_ms = int(float(chapters_data[1]["start_time"]) * 1000)
    assert abs(ch2_start_ms - 1500) < 150, (
        f"Ch2 marker at {ch2_start_ms} ms, expected ~1500 ms"
    )


@needs_ffmpeg
@pytest.mark.integration
def test_compile_m4b_loudness_gate(tmp_path):
    """Chapters should be within ±1 LU of target after normalization."""
    wav = _make_wav(tmp_path / "ch.wav", duration_s=2.0, freq=440)
    chapter_results = [{"title": "Only Chapter", "wav": wav, "duration_ms": 2000}]
    m4b = compile_m4b(
        chapter_results,
        str(tmp_path / "gate_test"),
        target_lufs=-18.0,
        inter_chapter_silence_ms=0,
        work_dir=tmp_path / "workdir",
    )
    assert m4b.exists()
    report_text = Path(str(tmp_path / "gate_test") + "_report.md").read_text()
    assert "PASS" in report_text
