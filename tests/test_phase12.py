"""Phase 12 — ASR round-trip QA tests.

All tests run without a Whisper model (testing compute_wer, sample_chunks,
format_asr_report, and check_chapters stub logic only).
"""

import wave
import struct
import numpy as np
import pytest

from vorpal.qa.asr import (
    compute_wer,
    sample_chunks,
    format_asr_report,
    ChunkASRResult,
    _tokenize,
)


# ── _tokenize ─────────────────────────────────────────────────────────────────


def test_tokenize_lowercases():
    assert _tokenize("Hello World") == ["hello", "world"]


def test_tokenize_strips_punctuation():
    tokens = _tokenize("Hello, world!")
    assert "hello" in tokens
    assert "world" in tokens
    assert "," not in tokens


def test_tokenize_empty():
    assert _tokenize("") == []


# ── compute_wer ───────────────────────────────────────────────────────────────


def test_compute_wer_identical():
    assert compute_wer("hello world", "hello world") == pytest.approx(0.0)


def test_compute_wer_complete_substitution():
    wer = compute_wer("hello world", "foo bar")
    assert wer == pytest.approx(1.0)


def test_compute_wer_one_deletion():
    # reference: 3 words; hypothesis missing one → 1 deletion / 3 = 0.333...
    wer = compute_wer("one two three", "one two")
    assert wer == pytest.approx(1 / 3)


def test_compute_wer_one_insertion():
    # reference: 2 words; hypothesis has an extra word → 1 insertion / 2 = 0.5
    wer = compute_wer("hello world", "hello beautiful world")
    assert wer == pytest.approx(0.5)


def test_compute_wer_empty_reference():
    assert compute_wer("", "") == pytest.approx(0.0)
    assert compute_wer("", "something") == pytest.approx(1.0)


def test_compute_wer_case_insensitive():
    assert compute_wer("Hello World", "hello world") == pytest.approx(0.0)


def test_compute_wer_punctuation_ignored():
    # Punctuation is stripped; these should be identical after tokenization
    assert compute_wer("Hello, world!", "hello world") == pytest.approx(0.0)


def test_compute_wer_partial_match():
    wer = compute_wer("one two three four", "one two three five")
    assert 0 < wer < 1


# ── sample_chunks ─────────────────────────────────────────────────────────────


def _make_chunks(n: int, text_len: int = 50) -> list:
    return [{"text": "a" * text_len, "idx": i} for i in range(n)]


def test_sample_chunks_returns_at_least_one():
    chunks = _make_chunks(10)
    sample = sample_chunks(chunks, fraction=0.05)
    assert len(sample) >= 1


def test_sample_chunks_fraction_ten_percent():
    chunks = _make_chunks(100)
    sample = sample_chunks(chunks, fraction=0.10)
    assert 8 <= len(sample) <= 12  # roughly 10%, may vary by rounding


def test_sample_chunks_full_fraction():
    chunks = _make_chunks(5)
    sample = sample_chunks(chunks, fraction=1.0)
    assert len(sample) == 5


def test_sample_chunks_skips_short_text():
    chunks = [
        {"text": "hi", "idx": 0},        # too short (< 20 chars)
        {"text": "a" * 50, "idx": 1},
    ]
    sample = sample_chunks(chunks, fraction=1.0)
    assert len(sample) == 1
    assert sample[0][1]["idx"] == 1


def test_sample_chunks_empty():
    assert sample_chunks([], fraction=0.10) == []


def test_sample_chunks_all_short():
    chunks = [{"text": "hi", "idx": i} for i in range(10)]
    assert sample_chunks(chunks, fraction=0.10) == []


def test_sample_chunks_returns_index_tuples():
    chunks = _make_chunks(5)
    sample = sample_chunks(chunks, fraction=1.0)
    for orig_idx, chunk in sample:
        assert isinstance(orig_idx, int)
        assert "text" in chunk


# ── format_asr_report ─────────────────────────────────────────────────────────


def test_format_asr_report_empty():
    report = format_asr_report([], sample_fraction=0.10, model_name="base")
    assert "No chunks sampled" in report


def test_format_asr_report_with_results():
    results = [
        ChunkASRResult(0, "Chapter 1", "source text", 0.05, "transcript", False),
        ChunkASRResult(3, "Chapter 1", "different text", 0.55, "bad transcript", True),
    ]
    report = format_asr_report(results, sample_fraction=0.10, model_name="base")
    assert "Chapter 1" in report
    assert "55%" in report or "0.55" in report or "Outliers" in report


def test_format_asr_report_no_outliers():
    results = [
        ChunkASRResult(0, "Ch1", "text", 0.10, "trans", False),
    ]
    report = format_asr_report(results, sample_fraction=0.10, model_name="base")
    assert "No outliers" in report


# ── CLI --asr-check flag wired up ─────────────────────────────────────────────


def test_build_parser_has_asr_check():
    from vorpal.cli import build_parser
    parser = build_parser()
    # Parse known valid args to confirm --asr-check is registered
    args = parser.parse_args([
        "build", "book.pdf",
        "--asr-check", "--asr-model", "tiny", "--asr-fraction", "0.05",
    ])
    assert args.asr_check is True
    assert args.asr_model == "tiny"
    assert args.asr_fraction == pytest.approx(0.05)


def test_build_parser_asr_defaults():
    from vorpal.cli import build_parser
    parser = build_parser()
    args = parser.parse_args(["build", "book.pdf"])
    assert args.asr_check is False
    assert args.asr_model == "base"
    assert args.asr_fraction == pytest.approx(0.10)
