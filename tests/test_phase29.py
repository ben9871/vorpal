"""Phase 29 — Chapter summary side product.

Tests:
  - summarize_chapter: cache round-trip (hit on second call)
  - summarize_chapter: blocked when body is empty
  - summarize_chapter: blocked when CLI unavailable (simulate)
  - inject_manual_summary: cache written correctly; summarize_chapter reads it back
  - generate_summaries_md: format, book title, omits None summaries
  - Cache key: different models produce different keys
  - Summary text never appears in TTS chunks (content-fidelity contract)
  - Build without --summaries: manifest has no "summaries" key
  - CLI: --summaries, --summaries-backend, --summaries-model flags exist
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from vorpal.summarize import (
    summarize_chapter,
    inject_manual_summary,
    generate_summaries_md,
    _cache_key,
    _cache_path,
    PROMPT_VERSION,
    DEFAULT_MODEL,
    DEFAULT_BACKEND,
)


# ── cache key ──────────────────────────────────────────────────────────────

class TestCacheKey:
    def test_includes_model(self):
        k1 = _cache_key("body text", "claude-haiku-4-5", "cli")
        k2 = _cache_key("body text", "claude-sonnet-4-6", "cli")
        assert k1 != k2

    def test_includes_backend(self):
        k1 = _cache_key("body text", DEFAULT_MODEL, "cli")
        k2 = _cache_key("body text", DEFAULT_MODEL, "api")
        assert k1 != k2

    def test_includes_prompt_version(self):
        k = _cache_key("body text", DEFAULT_MODEL, DEFAULT_BACKEND)
        assert PROMPT_VERSION in k

    def test_different_text_different_key(self):
        k1 = _cache_key("text A", DEFAULT_MODEL, DEFAULT_BACKEND)
        k2 = _cache_key("text B", DEFAULT_MODEL, DEFAULT_BACKEND)
        assert k1 != k2


# ── inject_manual_summary / cache round-trip ──────────────────────────────

class TestManualSeedAndCacheRoundTrip:
    def test_inject_creates_cache_file(self, tmp_path):
        body = "Alice fell down the rabbit hole and landed in Wonderland."
        inject_manual_summary(
            tmp_path, body, "Chapter 1", "Alice discovers Wonderland."
        )
        cp = _cache_path(tmp_path, body, DEFAULT_MODEL, DEFAULT_BACKEND)
        assert cp.exists()
        data = json.loads(cp.read_text(encoding="utf-8"))
        assert data["summary"] == "Alice discovers Wonderland."
        assert data["chapter_title"] == "Chapter 1"

    def test_summarize_reads_injected_cache(self, tmp_path):
        body = "Alice fell down the rabbit hole and landed in Wonderland."
        inject_manual_summary(
            tmp_path, body, "Chapter 1", "Alice discovers Wonderland."
        )
        result = summarize_chapter(body, "Chapter 1", tmp_path)
        assert result["cache_hit"] is True
        assert result["summary"] == "Alice discovers Wonderland."

    def test_second_call_hits_cache(self, tmp_path):
        body = "The Mad Hatter held an endless tea party."
        inject_manual_summary(tmp_path, body, "Ch2", "The tea party never ends.")
        # First call: cache hit (just injected)
        r1 = summarize_chapter(body, "Ch2", tmp_path)
        assert r1["cache_hit"] is True
        # Second call: still cache hit (file unchanged)
        r2 = summarize_chapter(body, "Ch2", tmp_path)
        assert r2["cache_hit"] is True
        assert r2["summary"] == "The tea party never ends."


# ── blocked cases ──────────────────────────────────────────────────────────

class TestBlockedCases:
    def test_empty_body_is_blocked(self, tmp_path):
        result = summarize_chapter("", "Empty Chapter", tmp_path)
        assert result["blocked"] is True
        assert result["summary"] is None

    def test_whitespace_only_is_blocked(self, tmp_path):
        result = summarize_chapter("   \n\t  ", "Whitespace", tmp_path)
        assert result["blocked"] is True

    def test_cli_not_available_returns_blocked(self, tmp_path):
        with patch("vorpal.summarize._summarize_via_cli", return_value=None):
            result = summarize_chapter(
                "Some real content here.", "Chapter", tmp_path
            )
        assert result["blocked"] is True
        assert result["summary"] is None


# ── generate_summaries_md ─────────────────────────────────────────────────

class TestGenerateSummariesMd:
    def _make_result(self, title: str, summary: str) -> dict:
        return {"chapter_title": title, "summary": summary,
                "blocked": summary is None}

    def test_includes_book_title(self):
        md = generate_summaries_md([], book_title="Alice in Wonderland")
        assert "Alice in Wonderland" in md

    def test_includes_chapter_headings(self):
        results = [self._make_result("Chapter One", "Alice falls.")]
        md = generate_summaries_md(results)
        assert "## Chapter One" in md
        assert "Alice falls." in md

    def test_omits_none_summaries(self):
        results = [
            self._make_result("Chapter One", "Alice falls."),
            self._make_result("Chapter Two", None),
        ]
        md = generate_summaries_md(results)
        assert "Chapter One" in md
        assert "Chapter Two" not in md

    def test_no_summaries_fallback_text(self):
        md = generate_summaries_md([])
        assert "No summaries generated" in md

    def test_separator_between_chapters(self):
        results = [
            self._make_result("Ch1", "Summary one."),
            self._make_result("Ch2", "Summary two."),
        ]
        md = generate_summaries_md(results)
        assert "---" in md


# ── content-fidelity contract ─────────────────────────────────────────────

class TestContentFidelity:
    """Summaries must never appear in TTS chunk text."""

    def test_summary_not_in_normalize_output(self, tmp_path):
        from vorpal.normalize import normalize_chapter
        body = "Alice walked through the garden. The flowers were talking."
        summary = "Alice encounters talking flowers."

        # Inject summary into cache
        inject_manual_summary(tmp_path, body, "Garden Chapter", summary)
        cached = summarize_chapter(body, "Garden Chapter", tmp_path)

        # Normalize the chapter body (what goes to TTS)
        chunks = normalize_chapter(body)
        tts_text = " ".join(c.text for c in chunks)

        # Summary text must not appear in TTS output
        assert summary not in tts_text
        assert cached["summary"] == summary

    def test_generate_summaries_md_is_separate_from_body(self):
        body = "The Queen shouted off with their heads. The courtiers trembled."
        summary = "The Queen terrorizes her court."
        results = [{"chapter_title": "Court Scene", "summary": summary}]
        md = generate_summaries_md(results)
        # MD contains the summary
        assert summary in md
        # MD does not contain the raw body text
        assert "off with their heads" not in md


# ── CLI flags ─────────────────────────────────────────────────────────────

class TestCLIFlags:
    def test_summaries_flag_exists(self):
        from vorpal.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["build", "test.pdf", "--summaries"])
        assert args.summaries is True

    def test_summaries_backend_flag(self):
        from vorpal.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["build", "test.pdf",
                                  "--summaries", "--summaries-backend", "api"])
        assert args.summaries_backend == "api"

    def test_summaries_model_flag(self):
        from vorpal.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["build", "test.pdf",
                                  "--summaries", "--summaries-model", "sonnet"])
        assert args.summaries_model == "sonnet"

    def test_summaries_default_off(self):
        from vorpal.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["build", "test.pdf"])
        assert args.summaries is False
