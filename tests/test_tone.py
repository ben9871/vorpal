"""Tests for tone.py — tagger logic, smoothing, cache, histogram."""

import json
import pytest
from pathlib import Path

from vorpal.tone import (
    TONE_VOCAB,
    split_paragraphs,
    _smooth_tones,
    _apply_confidence_gate,
    _parse_llm_response,
    tone_histogram,
    tag_chapter,
    _chapter_cache_key,
    PROMPT_VERSION,
)


# ── split_paragraphs ──────────────────────────────────────────────────────

def test_split_paragraphs_double_newline():
    text = "First paragraph.\n\nSecond paragraph.\n\nThird."
    paras = split_paragraphs(text)
    assert paras == ["First paragraph.", "Second paragraph.", "Third."]


def test_split_paragraphs_strips_whitespace():
    text = "  Hello world.  \n\n  Another one.  "
    paras = split_paragraphs(text)
    assert paras == ["Hello world.", "Another one."]


def test_split_paragraphs_multiple_blank_lines():
    text = "Para one.\n\n\n\nPara two."
    paras = split_paragraphs(text)
    assert paras == ["Para one.", "Para two."]


def test_split_paragraphs_empty_text():
    assert split_paragraphs("") == []
    assert split_paragraphs("   \n\n  ") == []


def test_split_paragraphs_single_paragraph():
    text = "No breaks here, just one paragraph."
    paras = split_paragraphs(text)
    assert paras == [text]


# ── _smooth_tones ──────────────────────────────────────────────────────────

def test_smooth_isolated_spike_damped():
    tones = ["neutral", "somber", "neutral", "neutral"]
    result = _smooth_tones(tones, min_run=2)
    assert result == ["neutral", "neutral", "neutral", "neutral"]


def test_smooth_run_preserved():
    tones = ["neutral", "somber", "somber", "neutral"]
    result = _smooth_tones(tones, min_run=2)
    assert result == ["neutral", "somber", "somber", "neutral"]


def test_smooth_short_run_damped():
    tones = ["tense", "neutral"]  # only 1 tense, min_run=2
    result = _smooth_tones(tones, min_run=2)
    assert result == ["neutral", "neutral"]


def test_smooth_min_run_1_preserves_spikes():
    tones = ["neutral", "warm", "neutral"]
    result = _smooth_tones(tones, min_run=1)
    assert result == ["neutral", "warm", "neutral"]


def test_smooth_empty():
    assert _smooth_tones([], min_run=2) == []


def test_smooth_all_neutral():
    tones = ["neutral", "neutral", "neutral"]
    assert _smooth_tones(tones, min_run=2) == tones


def test_smooth_long_run_preserved():
    tones = ["somber"] * 5
    result = _smooth_tones(tones, min_run=2)
    assert result == ["somber"] * 5


# ── _apply_confidence_gate ────────────────────────────────────────────────

def test_confidence_gate_low_becomes_neutral():
    entries = [{"idx": 0, "tone": "somber", "confidence": 0.5}]
    result = _apply_confidence_gate(entries, threshold=0.7)
    assert result[0]["tone"] == "neutral"


def test_confidence_gate_high_preserved():
    entries = [{"idx": 0, "tone": "tense", "confidence": 0.9}]
    result = _apply_confidence_gate(entries, threshold=0.7)
    assert result[0]["tone"] == "tense"


def test_confidence_gate_at_threshold_preserved():
    entries = [{"idx": 0, "tone": "warm", "confidence": 0.7}]
    result = _apply_confidence_gate(entries, threshold=0.7)
    assert result[0]["tone"] == "warm"


def test_confidence_gate_missing_confidence_passes():
    entries = [{"idx": 0, "tone": "wry"}]  # no confidence key
    result = _apply_confidence_gate(entries, threshold=0.7)
    assert result[0]["tone"] == "wry"


# ── _parse_llm_response ───────────────────────────────────────────────────

def test_parse_llm_response_basic():
    raw = '[{"idx": 0, "tone": "somber", "confidence": 0.9}]'
    result = _parse_llm_response(raw, 1)
    assert len(result) == 1
    assert result[0]["tone"] == "somber"
    assert result[0]["confidence"] == 0.9


def test_parse_llm_response_strips_markdown_fences():
    raw = '```json\n[{"idx": 0, "tone": "neutral", "confidence": 0.95}]\n```'
    result = _parse_llm_response(raw, 1)
    assert result[0]["tone"] == "neutral"


def test_parse_llm_response_unknown_tone_becomes_neutral():
    raw = '[{"idx": 0, "tone": "angry", "confidence": 0.8}]'
    result = _parse_llm_response(raw, 1)
    assert result[0]["tone"] == "neutral"


def test_parse_llm_response_fills_gaps():
    raw = '[{"idx": 0, "tone": "tense", "confidence": 0.85}]'
    result = _parse_llm_response(raw, 3)
    assert len(result) == 3
    assert result[1]["tone"] == "neutral"
    assert result[2]["tone"] == "neutral"


def test_parse_llm_response_truncates_excess():
    raw = ('[{"idx": 0, "tone": "neutral", "confidence": 0.9},'
           '{"idx": 1, "tone": "warm", "confidence": 0.8}]')
    result = _parse_llm_response(raw, 1)
    assert len(result) == 1


# ── tone_histogram ────────────────────────────────────────────────────────

def test_tone_histogram_empty():
    hist = tone_histogram([])
    assert hist["total"] == 0
    assert hist["neutral_fraction"] == 1.0  # trivially neutral when no paragraphs


def test_tone_histogram_counts():
    tones_per_chapter = [
        ["neutral", "neutral", "somber"],
        ["tense", "neutral"],
    ]
    hist = tone_histogram(tones_per_chapter)
    assert hist["counts"]["neutral"] == 3
    assert hist["counts"]["somber"] == 1
    assert hist["counts"]["tense"] == 1
    assert hist["total"] == 5
    assert abs(hist["neutral_fraction"] - 3 / 5) < 1e-9


def test_tone_histogram_neutral_fraction():
    all_neutral = [["neutral"] * 10]
    hist = tone_histogram(all_neutral)
    assert hist["neutral_fraction"] == 1.0


# ── tag_chapter — cache hit on second call ────────────────────────────────

def test_tag_chapter_cache_roundtrip(tmp_path):
    """tag_chapter reads from cache on second call without needing the key."""
    cache_dir = tmp_path / "tone_cache"
    body = "Para one.\n\nPara two.\n\nPara three."
    title = "Test Chapter"

    # Pre-populate the cache manually
    from vorpal.tone import _chapter_cache_key, DEFAULT_MODEL
    ck = _chapter_cache_key(body, DEFAULT_MODEL)
    cache_file = cache_dir / f"tone_{ck}.json"
    cache_dir.mkdir()
    cached_data = {
        "chapter_title": title,
        "model": DEFAULT_MODEL,
        "prompt_version": PROMPT_VERSION,
        "tones": ["neutral", "somber", "neutral"],
        "paragraphs": [
            {"idx": 0, "tone": "neutral", "confidence": 0.95, "text_preview": "Para one."},
            {"idx": 1, "tone": "somber",  "confidence": 0.88, "text_preview": "Para two."},
            {"idx": 2, "tone": "neutral", "confidence": 0.93, "text_preview": "Para three."},
        ],
    }
    cache_file.write_text(json.dumps(cached_data))

    result = tag_chapter(body, title, cache_dir)
    assert result["cache_hit"] is True
    assert result["tones"] == ["neutral", "somber", "neutral"]


def test_tag_chapter_no_key_raises(tmp_path, monkeypatch):
    """tag_chapter raises RuntimeError when no API key is set."""
    monkeypatch.delenv("VORPAL_ANTHROPIC_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    cache_dir = tmp_path / "tone_cache"
    with pytest.raises(RuntimeError, match="VORPAL_ANTHROPIC_KEY"):
        tag_chapter("A single paragraph.", "Chapter One", cache_dir)


def test_tag_chapter_empty_body(tmp_path):
    """tag_chapter returns empty result for empty body without calling the API."""
    result = tag_chapter("", "Empty Chapter", tmp_path / "cache")
    assert result["tones"] == []
    assert result["paragraphs"] == []


def test_chapter_cache_key_deterministic():
    a = _chapter_cache_key("same text", "claude-haiku-4-5")
    b = _chapter_cache_key("same text", "claude-haiku-4-5")
    assert a == b


def test_chapter_cache_key_changes_on_text_change():
    a = _chapter_cache_key("text a", "claude-haiku-4-5")
    b = _chapter_cache_key("text b", "claude-haiku-4-5")
    assert a != b


def test_chapter_cache_key_changes_on_model_change():
    a = _chapter_cache_key("text", "claude-haiku-4-5")
    b = _chapter_cache_key("text", "claude-sonnet-4-6")
    assert a != b


# ── tone vocabulary coverage ──────────────────────────────────────────────

def test_tone_vocab_size():
    assert len(TONE_VOCAB) == 8


def test_tone_vocab_contains_neutral():
    assert "neutral" in TONE_VOCAB


def test_tone_vocab_contains_all_expected():
    expected = {"neutral", "somber", "tense", "warm", "wry",
                "excited", "urgent", "reflective"}
    assert TONE_VOCAB == expected
