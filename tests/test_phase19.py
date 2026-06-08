"""Phase 19 — Manifest as first-class artifact (vorpal export) tests.

All tests use synthetic fixtures; no TTS/GPU calls needed.
Covers: body retrieval (inline and chapter_texts fallback), TXT export
structure, EPUB zip structure, XML escaping, CLI parser, and a small
end-to-end round-trip through a real TXT build.
"""

import json
import zipfile
from pathlib import Path

import pytest

from vorpal.export import (
    _chapter_xhtml,
    _container_xml,
    _nav_xhtml,
    _package_opf,
    _xml_escape,
    export_epub,
    export_txt,
    get_chapter_body,
    load_footnotes,
)
from vorpal.cli import build_parser


# ── fixtures ──────────────────────────────────────────────────────────────────


class _FakeSection:
    def __init__(self, id, title, include=True, body=""):
        self.id = id
        self.title = title
        self.include = include
        self.body = body


def _safe_fn(title: str) -> str:
    """Minimal safe_filename stand-in for tests."""
    import re
    return re.sub(r"[^\w\-]", "_", title)[:40].strip("_")


# ── get_chapter_body ──────────────────────────────────────────────────────────


def test_get_body_returns_inline_body(tmp_path):
    s = _FakeSection(1, "Chapter One", body="Inline body text.")
    assert get_chapter_body(s, tmp_path, _safe_fn) == "Inline body text."


def test_get_body_reads_chapter_texts_dir(tmp_path):
    ct = tmp_path / "chapter_texts"
    ct.mkdir()
    (ct / "01_Chapter_One.txt").write_text("From disk.", encoding="utf-8")
    s = _FakeSection(1, "Chapter One", body="")
    result = get_chapter_body(s, tmp_path, _safe_fn)
    assert result == "From disk."


def test_get_body_returns_empty_when_missing(tmp_path):
    s = _FakeSection(1, "Missing Chapter", body="")
    assert get_chapter_body(s, tmp_path, _safe_fn) == ""


def test_get_body_prefers_inline_over_disk(tmp_path):
    ct = tmp_path / "chapter_texts"
    ct.mkdir()
    (ct / "01_Inline.txt").write_text("From disk.", encoding="utf-8")
    s = _FakeSection(1, "Inline", body="Inline wins.")
    assert get_chapter_body(s, tmp_path, _safe_fn) == "Inline wins."


# ── load_footnotes ────────────────────────────────────────────────────────────


def test_load_footnotes_present(tmp_path):
    (tmp_path / "footnotes.json").write_text(
        json.dumps(["Footnote one.", "Footnote two."]), encoding="utf-8"
    )
    assert load_footnotes(tmp_path) == ["Footnote one.", "Footnote two."]


def test_load_footnotes_missing(tmp_path):
    assert load_footnotes(tmp_path) == []


def test_load_footnotes_empty_list(tmp_path):
    (tmp_path / "footnotes.json").write_text("[]", encoding="utf-8")
    assert load_footnotes(tmp_path) == []


# ── export_txt ────────────────────────────────────────────────────────────────


def test_export_txt_contains_chapter_titles(tmp_path):
    sections = [
        _FakeSection(1, "Chapter One",   body="Content one."),
        _FakeSection(2, "Chapter Two",   body="Content two."),
    ]
    out = tmp_path / "book.txt"
    export_txt(sections, tmp_path, out, _safe_fn)
    content = out.read_text()
    assert "# Chapter One" in content
    assert "# Chapter Two" in content
    assert "Content one." in content


def test_export_txt_skips_excluded_sections(tmp_path):
    sections = [
        _FakeSection(1, "Include Me",  include=True,  body="Yes."),
        _FakeSection(2, "Skip Me",     include=False, body="No."),
    ]
    out = tmp_path / "book.txt"
    export_txt(sections, tmp_path, out, _safe_fn)
    content = out.read_text()
    assert "Include Me" in content
    assert "Skip Me" not in content


def test_export_txt_appends_footnotes(tmp_path):
    (tmp_path / "footnotes.json").write_text('["Footnote text."]', encoding="utf-8")
    sections = [_FakeSection(1, "Chapter", body="Body.")]
    out = tmp_path / "book.txt"
    export_txt(sections, tmp_path, out, _safe_fn)
    content = out.read_text()
    assert "Footnotes" in content
    assert "[1] Footnote text." in content


def test_export_txt_no_footnotes_no_section(tmp_path):
    sections = [_FakeSection(1, "Chapter", body="Body.")]
    out = tmp_path / "book.txt"
    export_txt(sections, tmp_path, out, _safe_fn)
    assert "Footnotes" not in out.read_text()


def test_export_txt_skips_empty_bodies(tmp_path):
    sections = [
        _FakeSection(1, "Empty", body=""),
        _FakeSection(2, "Full",  body="Real content."),
    ]
    out = tmp_path / "book.txt"
    export_txt(sections, tmp_path, out, _safe_fn)
    content = out.read_text()
    assert "Empty" not in content
    assert "Full" in content


# ── export_epub ────────────────────────────────────────────────────────────────


def test_export_epub_creates_zip(tmp_path):
    sections = [_FakeSection(1, "Ch1", body="Text.")]
    out = tmp_path / "book.epub"
    export_epub(sections, tmp_path, out, "Title", "Author", _safe_fn)
    assert out.exists()
    assert zipfile.is_zipfile(str(out))


def test_export_epub_has_required_files(tmp_path):
    sections = [_FakeSection(1, "Ch1", body="Text.")]
    out = tmp_path / "book.epub"
    export_epub(sections, tmp_path, out, "Title", "Author", _safe_fn)
    with zipfile.ZipFile(str(out)) as zf:
        names = zf.namelist()
    assert "mimetype" in names
    assert "META-INF/container.xml" in names
    assert "OEBPS/package.opf" in names
    assert "OEBPS/nav.xhtml" in names
    assert "OEBPS/chapter_001.xhtml" in names


def test_export_epub_mimetype_is_correct(tmp_path):
    sections = [_FakeSection(1, "Ch1", body="Text.")]
    out = tmp_path / "book.epub"
    export_epub(sections, tmp_path, out, "Title", "Author", _safe_fn)
    with zipfile.ZipFile(str(out)) as zf:
        assert zf.read("mimetype") == b"application/epub+zip"


def test_export_epub_mimetype_stored_uncompressed(tmp_path):
    sections = [_FakeSection(1, "Ch1", body="Text.")]
    out = tmp_path / "book.epub"
    export_epub(sections, tmp_path, out, "Title", "Author", _safe_fn)
    with zipfile.ZipFile(str(out)) as zf:
        info = zf.getinfo("mimetype")
        assert info.compress_type == zipfile.ZIP_STORED


def test_export_epub_chapter_count_matches(tmp_path):
    sections = [
        _FakeSection(1, "Ch1", body="One."),
        _FakeSection(2, "Ch2", body="Two."),
        _FakeSection(3, "Excluded", include=False, body="No."),
    ]
    out = tmp_path / "book.epub"
    export_epub(sections, tmp_path, out, "Title", "Author", _safe_fn)
    with zipfile.ZipFile(str(out)) as zf:
        xhtml = [n for n in zf.namelist() if n.startswith("OEBPS/chapter_")]
    assert len(xhtml) == 2


def test_export_epub_nav_contains_chapter_links(tmp_path):
    sections = [
        _FakeSection(1, "First Chapter", body="Text."),
        _FakeSection(2, "Second Chapter", body="More."),
    ]
    out = tmp_path / "book.epub"
    export_epub(sections, tmp_path, out, "My Book", "An Author", _safe_fn)
    with zipfile.ZipFile(str(out)) as zf:
        nav = zf.read("OEBPS/nav.xhtml").decode()
    assert "First Chapter" in nav
    assert "Second Chapter" in nav


def test_export_epub_title_author_in_opf(tmp_path):
    sections = [_FakeSection(1, "Ch", body="Text.")]
    out = tmp_path / "book.epub"
    export_epub(sections, tmp_path, out, "My Great Book", "Famous Author", _safe_fn)
    with zipfile.ZipFile(str(out)) as zf:
        opf = zf.read("OEBPS/package.opf").decode()
    assert "My Great Book" in opf
    assert "Famous Author" in opf


# ── XML utilities ─────────────────────────────────────────────────────────────


def test_xml_escape_ampersand():
    assert _xml_escape("A & B") == "A &amp; B"


def test_xml_escape_angle_brackets():
    assert _xml_escape("<tag>") == "&lt;tag&gt;"


def test_xml_escape_quotes():
    assert _xml_escape('"hello"') == "&quot;hello&quot;"


def test_xml_escape_plain():
    assert _xml_escape("plain text") == "plain text"


# ── CLI parser ────────────────────────────────────────────────────────────────


def test_parser_has_export_subcommand():
    p = build_parser()
    args = p.parse_args(["export", "book.pdf", "--as", "txt"])
    assert args.command == "export"
    assert args.format == "txt"


def test_parser_export_epub_format():
    p = build_parser()
    args = p.parse_args(["export", "book.epub", "--as", "epub"])
    assert args.format == "epub"


def test_parser_export_output_flag():
    p = build_parser()
    args = p.parse_args(["export", "book.pdf", "--as", "txt", "--output", "out.txt"])
    assert args.output == "out.txt"


def test_parser_export_format_required():
    p = build_parser()
    with pytest.raises(SystemExit):
        p.parse_args(["export", "book.pdf"])


# ── end-to-end: TXT build → export ───────────────────────────────────────────


def _write_simple_txt(path: Path, n_chapters: int = 2) -> None:
    body = "\n\n".join(
        f"# Chapter {i}\n\nText for chapter {i} body." for i in range(1, n_chapters + 1)
    )
    path.write_text(body, encoding="utf-8")


def test_e2e_txt_build_then_export_txt(tmp_path):
    """Build a small TXT book to segment stage, then export to TXT."""
    book = tmp_path / "mybook.txt"
    _write_simple_txt(book, n_chapters=3)

    # Build to segment stage
    from vorpal.cli import _build_one_library_book
    import argparse
    lib_args = argparse.Namespace(
        voice="af_heart", speed=1.0, dpi=300, stop_after="segment", draft=False,
    )
    status, detail = _build_one_library_book(lib_args, book)
    assert status == "success", detail

    # Now export
    from vorpal.cli import cmd_export
    out = tmp_path / "mybook.txt.export.txt"
    exp_args = argparse.Namespace(
        input=str(book),
        format="txt",
        output=str(out),
        workdir_output=str(tmp_path / "mybook"),
    )
    cmd_export(exp_args)

    content = out.read_text()
    assert "Chapter 1" in content
    assert "Chapter 2" in content
    assert "Text for chapter" in content


def test_e2e_txt_build_then_export_epub(tmp_path):
    """Build a small TXT book to segment stage, then export to EPUB."""
    book = tmp_path / "myepub.txt"
    _write_simple_txt(book, n_chapters=2)

    from vorpal.cli import _build_one_library_book
    import argparse
    lib_args = argparse.Namespace(
        voice="af_heart", speed=1.0, dpi=300, stop_after="segment", draft=False,
    )
    status, detail = _build_one_library_book(lib_args, book)
    assert status == "success", detail

    from vorpal.cli import cmd_export
    out = tmp_path / "myepub.epub"
    exp_args = argparse.Namespace(
        input=str(book),
        format="epub",
        output=str(out),
        workdir_output=str(tmp_path / "myepub"),
    )
    cmd_export(exp_args)

    assert out.exists()
    assert zipfile.is_zipfile(str(out))
    with zipfile.ZipFile(str(out)) as zf:
        names = zf.namelist()
    assert "OEBPS/package.opf" in names
    assert any(n.startswith("OEBPS/chapter_") for n in names)
