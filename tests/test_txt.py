"""Tests for plain-text input extraction (extract/text.py)."""

import pytest

from vorpal.extract.text import (
    extract_txt,
    _is_heading_line,
    _strip_gutenberg_wrapper,
    _extract_gutenberg_meta,
    _split_into_sections,
    _classify_title,
)


# ── heading detection ────────────────────────────────────────────────────

def test_heading_chapter_number():
    assert _is_heading_line("CHAPTER I")
    assert _is_heading_line("CHAPTER 5")
    assert _is_heading_line("Chapter One")
    assert _is_heading_line("Chapter XII")


def test_heading_part():
    assert _is_heading_line("PART ONE")
    assert _is_heading_line("PART I")
    assert _is_heading_line("BOOK II")


def test_heading_roman():
    assert _is_heading_line("I.")
    assert _is_heading_line("IV.")
    assert _is_heading_line("XII.")


def test_heading_too_long():
    assert not _is_heading_line("This is a very long sentence that goes on and on " * 3)


def test_heading_normal_sentence():
    assert not _is_heading_line("The hero walked into the room.")
    assert not _is_heading_line("Once upon a time, there was a king.")


# ── Gutenberg wrapper stripping ──────────────────────────────────────────

def test_strip_gutenberg_header():
    text = """\
Title: Treasure Island
Author: Robert Louis Stevenson

*** START OF THE PROJECT GUTENBERG EBOOK TREASURE ISLAND ***

Produced by someone.

CHAPTER I

Body text here.

*** END OF THE PROJECT GUTENBERG EBOOK ***

More PG footer stuff.
"""
    result = _strip_gutenberg_wrapper(text)
    assert "CHAPTER I" in result
    assert "Body text here" in result
    assert "START OF THE PROJECT GUTENBERG" not in result
    assert "END OF THE PROJECT GUTENBERG" not in result
    assert "More PG footer" not in result


def test_strip_gutenberg_noop_on_plain_text():
    plain = "CHAPTER I\n\nSome body text here.\n\nCHAPTER II\n\nMore text."
    result = _strip_gutenberg_wrapper(plain)
    assert "CHAPTER I" in result
    assert "CHAPTER II" in result


# ── Gutenberg metadata extraction ────────────────────────────────────────

def test_extract_gutenberg_meta():
    text = "Title: Treasure Island\nAuthor: Robert Louis Stevenson\n\nBody."
    title, author = _extract_gutenberg_meta(text)
    assert title == "Treasure Island"
    assert author == "Robert Louis Stevenson"


def test_extract_gutenberg_meta_missing():
    text = "Some content without metadata."
    title, author = _extract_gutenberg_meta(text)
    assert title == ""
    assert author == ""


# ── section splitting ────────────────────────────────────────────────────

def test_split_chapters():
    text = """\

CHAPTER I

This is the first chapter body. It has some text.

CHAPTER II

This is the second chapter body.

CHAPTER III

Third chapter.
"""
    sections = _split_into_sections(text)
    assert len(sections) == 3
    assert sections[0][0] == "CHAPTER I"
    assert "first chapter body" in sections[0][1]
    assert sections[1][0] == "CHAPTER II"
    assert sections[2][0] == "CHAPTER III"


def test_split_no_headings():
    text = "Just some text without any chapter headings at all."
    sections = _split_into_sections(text)
    assert len(sections) == 1
    assert sections[0][0] is None
    assert "Just some text" in sections[0][1]


def test_split_roman_numerals():
    text = "\nI.\n\nFirst section body.\n\nII.\n\nSecond section body.\n"
    sections = _split_into_sections(text)
    assert len(sections) == 2


# ── extract_txt integration ──────────────────────────────────────────────

def test_extract_txt_basic(tmp_path):
    txt = tmp_path / "book.txt"
    ch1 = "This is the first chapter. " * 20
    ch2 = "This is the second chapter. " * 20
    txt.write_text(
        f"CHAPTER I\n\n{ch1}\n\nCHAPTER II\n\n{ch2}",
        encoding="utf-8",
    )
    result = extract_txt(txt)
    assert result["format"] == "txt"
    sections = result["sections"]
    assert len(sections) == 2
    assert sections[0]["title"] == "CHAPTER I"
    assert sections[0]["source"] == "heuristic"
    assert sections[0]["include"] is True
    assert "first chapter" in sections[0]["body"]


def test_extract_txt_single_section(tmp_path):
    txt = tmp_path / "book.txt"
    txt.write_text(
        "Just a plain text book with no chapter headings. " * 50,
        encoding="utf-8",
    )
    result = extract_txt(txt)
    sections = result["sections"]
    assert len(sections) == 1
    assert sections[0]["source"] == "manual"
    assert "no-structure-found" in sections[0]["flags"]


def test_extract_txt_gutenberg_metadata(tmp_path):
    txt = tmp_path / "book.txt"
    txt.write_text(
        "Title: My Novel\nAuthor: Jane Smith\n\n"
        "*** START OF THE PROJECT GUTENBERG EBOOK MY NOVEL ***\n\n"
        "CHAPTER I\n\n" + "Body text. " * 20 + "\n\n"
        "*** END OF THE PROJECT GUTENBERG EBOOK ***\n",
        encoding="utf-8",
    )
    result = extract_txt(txt)
    assert result["title"] == "My Novel"
    assert result["author"] == "Jane Smith"
    assert len(result["sections"]) >= 1
    assert "START OF" not in result["sections"][0]["body"]


def test_extract_txt_word_count(tmp_path):
    txt = tmp_path / "book.txt"
    txt.write_text(
        "CHAPTER I\n\n" + "word " * 300,
        encoding="utf-8",
    )
    result = extract_txt(txt)
    assert result["sections"][0]["words"] >= 100


def test_extract_txt_body_stored(tmp_path):
    txt = tmp_path / "book.txt"
    content = "CHAPTER I\n\n" + "Unique content phrase. " * 20
    txt.write_text(content, encoding="utf-8")
    result = extract_txt(txt)
    assert "Unique content phrase" in result["sections"][0]["body"]


def test_extract_txt_qa_fields(tmp_path):
    txt = tmp_path / "book.txt"
    txt.write_text("CHAPTER I\n\n" + "body. " * 20, encoding="utf-8")
    result = extract_txt(txt)
    qa = result["qa"]
    assert "heuristic_used" in qa
    assert "sections_produced" in qa
