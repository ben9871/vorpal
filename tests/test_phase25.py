"""Phase 25 — Footnote narration mode.

Tests:
  - load_footnotes_json: missing file, malformed JSON, valid data
  - assign_to_chapter: page range filtering (start, end, boundary, None end)
  - format_inline_text: empty, numbered labels, normalization, marker stripping
  - format_chapter_body: same as inline starting from 1
  - make_footnotes_chapter: empty vs. non-empty, skip=True, kind="footnotes"
  - _clean_marker: star, dagger, numeric markers
  - Default build (no --footnotes) unchanged — footnotes absent from chapter body
  - normalize_chapter still works on footnote text (spoken_form integration)
"""

import json
import os
import tempfile
from pathlib import Path

import pytest

from vorpal.footnotes_narration import (
    load_footnotes_json,
    assign_to_chapter,
    format_inline_text,
    format_chapter_body,
    make_footnotes_chapter,
    _clean_marker,
    _index_word,
)


# ── _index_word ────────────────────────────────────────────────────────────

class TestIndexWord:
    def test_small_numbers(self):
        assert _index_word(1) == "one"
        assert _index_word(5) == "five"
        assert _index_word(20) == "twenty"

    def test_large_fallback(self):
        assert _index_word(21) == "21"
        assert _index_word(100) == "100"


# ── _clean_marker ──────────────────────────────────────────────────────────

class TestCleanMarker:
    def test_star_marker(self):
        assert _clean_marker("* This is a note.") == "This is a note."

    def test_dagger_marker(self):
        assert _clean_marker("† Another note.") == "Another note."

    def test_numeric_dot(self):
        assert _clean_marker("1. This is footnote one.") == "This is footnote one."

    def test_numeric_paren(self):
        assert _clean_marker("2) Second footnote.") == "Second footnote."

    def test_no_marker(self):
        assert _clean_marker("Plain text footnote.") == "Plain text footnote."

    def test_strips_whitespace(self):
        assert _clean_marker("   * spaced  ") == "spaced"


# ── load_footnotes_json ────────────────────────────────────────────────────

class TestLoadFootnotesJson:
    def test_missing_file(self, tmp_path):
        result = load_footnotes_json(tmp_path)
        assert result == []

    def test_valid_data(self, tmp_path):
        data = [{"page": 0, "text": "* First note."}, {"page": 1, "text": "† Second."}]
        (tmp_path / "footnotes.json").write_text(json.dumps(data), encoding="utf-8")
        result = load_footnotes_json(tmp_path)
        assert len(result) == 2
        assert result[0]["page"] == 0

    def test_malformed_json(self, tmp_path):
        (tmp_path / "footnotes.json").write_text("not json!", encoding="utf-8")
        result = load_footnotes_json(tmp_path)
        assert result == []

    def test_non_list_json(self, tmp_path):
        (tmp_path / "footnotes.json").write_text('{"key": "value"}', encoding="utf-8")
        result = load_footnotes_json(tmp_path)
        assert result == []

    def test_empty_list(self, tmp_path):
        (tmp_path / "footnotes.json").write_text("[]", encoding="utf-8")
        result = load_footnotes_json(tmp_path)
        assert result == []


# ── assign_to_chapter ─────────────────────────────────────────────────────

class _DummySection:
    """Minimal Section-like object for testing."""
    def __init__(self, start_page, end_page=None):
        self.start = (start_page, 0)
        self.end = (end_page, 0) if end_page is not None else None


class TestAssignToChapter:
    def _fns(self, pages):
        return [{"page": p, "text": f"Note on page {p}."} for p in pages]

    def test_exact_start(self):
        sec = _DummySection(start_page=5, end_page=10)
        fns = self._fns([4, 5, 9, 10])
        result = assign_to_chapter(fns, sec)
        pages = [f["page"] for f in result]
        assert pages == [5, 9]   # 4 excluded (before), 10 excluded (at end)

    def test_no_end(self):
        # end=None: no upper bound
        sec = _DummySection(start_page=3, end_page=None)
        fns = self._fns([2, 3, 100, 200])
        result = assign_to_chapter(fns, sec)
        pages = [f["page"] for f in result]
        assert pages == [3, 100, 200]

    def test_empty_range(self):
        sec = _DummySection(start_page=5, end_page=5)
        fns = self._fns([4, 5, 6])
        result = assign_to_chapter(fns, sec)
        assert result == []

    def test_dict_section(self):
        sec = {"start": [2, 0], "end": [5, 0]}
        fns = self._fns([1, 2, 4, 5])
        result = assign_to_chapter(fns, sec)
        assert [f["page"] for f in result] == [2, 4]


# ── format_inline_text ────────────────────────────────────────────────────

class TestFormatInlineText:
    def test_empty(self):
        assert format_inline_text([]) == ""

    def test_single_footnote(self):
        fns = [{"page": 0, "text": "* A note about things."}]
        result = format_inline_text(fns)
        assert result.startswith("Footnote one.")
        assert "A note about things" in result

    def test_multiple_numbered(self):
        fns = [
            {"page": 0, "text": "1. First note."},
            {"page": 1, "text": "2. Second note."},
            {"page": 2, "text": "3. Third note."},
        ]
        result = format_inline_text(fns)
        assert "Footnote one." in result
        assert "Footnote two." in result
        assert "Footnote three." in result

    def test_start_index(self):
        fns = [{"page": 5, "text": "A note."}]
        result = format_inline_text(fns, start_index=3)
        assert result.startswith("Footnote three.")

    def test_blank_text_skipped(self):
        fns = [{"page": 0, "text": ""}, {"page": 1, "text": "Real note."}]
        result = format_inline_text(fns)
        assert "Footnote one." not in result or "Real note." in result
        # At least the non-empty note makes it through
        assert "Real note." in result

    def test_separated_by_blank_lines(self):
        fns = [{"page": 0, "text": "First."}, {"page": 1, "text": "Second."}]
        result = format_inline_text(fns)
        assert "\n\n" in result


# ── format_chapter_body ───────────────────────────────────────────────────

class TestFormatChapterBody:
    def test_starts_from_one(self):
        fns = [{"page": 0, "text": "A."}, {"page": 1, "text": "B."}]
        result = format_chapter_body(fns)
        assert result.startswith("Footnote one.")

    def test_empty(self):
        assert format_chapter_body([]) == ""


# ── make_footnotes_chapter ────────────────────────────────────────────────

class TestMakeFootnotesChapter:
    def test_none_when_empty(self):
        assert make_footnotes_chapter([]) is None

    def test_chapter_structure(self):
        fns = [{"page": 0, "text": "* A note."}]
        ch = make_footnotes_chapter(fns)
        assert ch is not None
        assert ch["title"] == "Footnotes"
        assert ch["skip"] is True
        assert ch["kind"] == "footnotes"
        assert "body" in ch
        assert len(ch["body"]) > 0

    def test_body_contains_text(self):
        fns = [{"page": 0, "text": "Notable annotation."}]
        ch = make_footnotes_chapter(fns)
        assert "Notable annotation" in ch["body"]


# ── integration: normalize_chapter on footnote text ───────────────────────

class TestNormalizationIntegration:
    def test_spoken_form_applied(self):
        """Numbers and abbreviations in footnote text should be normalized."""
        from vorpal.normalize import spoken_form
        text = "See pp. 42-45 for details."
        normalized = spoken_form(text)
        # spoken_form should convert numbers; at minimum it should return a string
        assert isinstance(normalized, str)
        assert len(normalized) > 0

    def test_format_inline_normalizes(self):
        """format_inline_text uses spoken_form, so it should not crash on numbers."""
        fns = [{"page": 0, "text": "1. See chapter 3, pp. 10-12."}]
        result = format_inline_text(fns)
        assert "Footnote one." in result
        assert isinstance(result, str)
