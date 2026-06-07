"""Tests for EPUB input extraction (extract/epub.py)."""

import io
import zipfile

import pytest

from vorpal.extract.epub import (
    extract_epub,
    _html_to_text,
    _classify_title,
    _strip_enum_prefix,
    _toc_to_spine_map,
    _href_base,
)


# ── HTML → text ──────────────────────────────────────────────────────────

def test_html_to_text_basic():
    html = b"<html><body><p>Hello world.</p><p>Second paragraph.</p></body></html>"
    text = _html_to_text(html)
    assert "Hello world." in text
    assert "Second paragraph." in text


def test_html_to_text_strips_tags():
    html = b"<p>Before <b>bold</b> after.</p>"
    text = _html_to_text(html)
    assert "Before bold after." in text
    assert "<" not in text


def test_html_to_text_skips_nav():
    html = b"<body><nav><a>TOC link</a></nav><p>Real content.</p></body>"
    text = _html_to_text(html)
    assert "Real content." in text
    assert "TOC link" not in text


def test_html_to_text_paragraph_breaks():
    html = b"<p>Para one.</p><p>Para two.</p>"
    text = _html_to_text(html)
    assert "\n\n" in text


def test_html_to_text_entities():
    html = b"<p>Fish &amp; chips &mdash; nice.</p>"
    text = _html_to_text(html)
    assert "&amp;" not in text
    assert "Fish" in text
    assert "chips" in text


# ── title classification ─────────────────────────────────────────────────

def test_classify_chapter():
    assert _classify_title("Chapter One") == "chapter"
    assert _classify_title("CHAPTER IV") == "chapter"
    assert _classify_title("The Adventure Begins") == "chapter"


def test_classify_frontmatter():
    assert _classify_title("Preface") == "frontmatter"
    assert _classify_title("Foreword") == "frontmatter"
    assert _classify_title("Introduction") == "frontmatter"
    assert _classify_title("Acknowledgements") == "frontmatter"


def test_classify_backmatter():
    assert _classify_title("Index") == "backmatter"
    assert _classify_title("Bibliography") == "backmatter"
    assert _classify_title("Appendix A") == "backmatter"


def test_strip_enum_prefix():
    # When enumeration covers the whole title, original is returned (same as segment module)
    assert _strip_enum_prefix("Chapter I") == "Chapter I"
    assert _strip_enum_prefix("CHAPTER 5. The Storm") == "The Storm"
    assert _strip_enum_prefix("Just a title") == "Just a title"


# ── TOC → spine mapping ──────────────────────────────────────────────────

def test_href_base_strips_fragment():
    assert _href_base("chapter01.xhtml#start") == "chapter01.xhtml"
    assert _href_base("chapter01.xhtml") == "chapter01.xhtml"


def test_toc_to_spine_map():
    spine = ["OEBPS/chapter01.xhtml", "OEBPS/chapter02.xhtml", "OEBPS/chapter03.xhtml"]
    toc = [("Chapter One", "OEBPS/chapter01.xhtml#c1"),
           ("Chapter Two", "OEBPS/chapter02.xhtml"),
           ("Chapter Three", "OEBPS/chapter03.xhtml")]
    result = _toc_to_spine_map(spine, toc)
    assert result == {0: "Chapter One", 1: "Chapter Two", 2: "Chapter Three"}


def test_toc_to_spine_map_partial_path():
    spine = ["OEBPS/text/ch01.xhtml", "OEBPS/text/ch02.xhtml"]
    toc = [("First", "text/ch01.xhtml"), ("Second", "text/ch02.xhtml")]
    result = _toc_to_spine_map(spine, toc)
    assert 0 in result or 1 in result   # at least one match via suffix


# ── minimal valid EPUB builder ───────────────────────────────────────────

def _make_epub(
    chapters: list,       # [(title, html_body), ...]
    title: str = "Test Book",
    author: str = "Test Author",
    epub3: bool = True,
) -> bytes:
    """Build a minimal but valid EPUB in memory for testing."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", "application/epub+zip")

        # Container
        zf.writestr("META-INF/container.xml", """\
<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:schemas:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>""")

        # Write chapter XHTML files
        spine_items = []
        for i, (ch_title, ch_body) in enumerate(chapters):
            fname = f"OEBPS/ch{i+1:02d}.xhtml"
            spine_items.append((f"ch{i+1:02d}", fname, ch_title))
            zf.writestr(fname, f"""\
<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>{ch_title}</title></head>
<body><h1>{ch_title}</h1><p>{ch_body}</p></body>
</html>""")

        # NAV (EPUB3) or NCX (EPUB2)
        if epub3:
            nav_xhtml = ('<?xml version="1.0" encoding="utf-8"?>'
                         '<html xmlns="http://www.w3.org/1999/xhtml"'
                         ' xmlns:epub="http://www.idpf.org/2007/ops">'
                         '<body><nav epub:type="toc"><ol>')
            for item_id, fname, ch_title in spine_items:
                nav_xhtml += f'<li><a href="{fname[6:]}">{ch_title}</a></li>'
            nav_xhtml += '</ol></nav></body></html>'
            zf.writestr("OEBPS/nav.xhtml", nav_xhtml)
            nav_item = '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
        else:
            nav_item = '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
            ncx = ('<?xml version="1.0"?><ncx xmlns="http://www.daisy.org/z3986/2005/ncx/">'
                   '<navMap>')
            for i, (item_id, fname, ch_title) in enumerate(spine_items):
                ncx += (f'<navPoint id="np{i}"><navLabel><text>{ch_title}</text></navLabel>'
                        f'<content src="{fname[6:]}"/></navPoint>')
            ncx += '</navMap></ncx>'
            zf.writestr("OEBPS/toc.ncx", ncx)

        # Manifest items for chapters
        manifest_items = "\n".join(
            f'<item id="{item_id}" href="{fname[6:]}" media-type="application/xhtml+xml"/>'
            for item_id, fname, _ in spine_items
        )
        spine_refs = "\n".join(
            f'<itemref idref="{item_id}"/>'
            for item_id, _, _ in spine_items
        )

        opf = f"""\
<?xml version="1.0" encoding="utf-8"?>
<package version="3.0" xmlns="http://www.idpf.org/2007/opf"
         xmlns:dc="http://purl.org/dc/elements/1.1/">
  <metadata>
    <dc:title>{title}</dc:title>
    <dc:creator>{author}</dc:creator>
  </metadata>
  <manifest>
    {nav_item}
    {manifest_items}
  </manifest>
  <spine>
    {spine_refs}
  </spine>
</package>"""
        zf.writestr("OEBPS/content.opf", opf)

    return buf.getvalue()


def _write_epub(tmp_path, chapters, **kwargs):
    data = _make_epub(chapters, **kwargs)
    p = tmp_path / "test.epub"
    p.write_bytes(data)
    return p


# ── extract_epub integration tests ───────────────────────────────────────

def test_extract_epub_basic(tmp_path):
    epub = _write_epub(tmp_path, [
        ("Chapter One", "This is the first chapter. " * 20),
        ("Chapter Two", "This is the second chapter. " * 20),
    ], title="My Book", author="Jane Doe")

    result = extract_epub(epub)
    assert result["title"] == "My Book"
    assert result["author"] == "Jane Doe"
    assert result["format"] == "epub"

    sections = result["sections"]
    assert len(sections) == 2
    assert sections[0]["title"] == "Chapter One"
    assert sections[1]["title"] == "Chapter Two"
    assert sections[0]["source"] == "spine"
    assert sections[0]["confidence"] == 1.0
    assert sections[0]["include"] is True
    assert "first chapter" in sections[0]["body"]


def test_extract_epub_frontmatter_excluded(tmp_path):
    epub = _write_epub(tmp_path, [
        ("Preface", "Some prefatory remarks. " * 5),
        ("Introduction", "The introduction. " * 5),
        ("Chapter One", "Body content. " * 20),
    ])
    result = extract_epub(epub)
    sections = result["sections"]
    kinds = {s["title"]: s["kind"] for s in sections}
    assert kinds["Preface"] == "frontmatter"
    assert kinds["Introduction"] == "frontmatter"
    assert kinds["Chapter One"] == "chapter"
    assert not any(s["include"] for s in sections if s["kind"] == "frontmatter")


def test_extract_epub_body_stored(tmp_path):
    long_body = "The quick brown fox jumps over the lazy dog. " * 50
    epub = _write_epub(tmp_path, [("Chapter One", long_body)])
    result = extract_epub(epub)
    body = result["sections"][0]["body"]
    assert len(body) > 100
    assert "fox" in body


def test_extract_epub_word_count(tmp_path):
    text = "word " * 200
    epub = _write_epub(tmp_path, [("Chapter One", text)])
    result = extract_epub(epub)
    assert result["sections"][0]["words"] >= 100


def test_extract_epub_epub2_ncx(tmp_path):
    epub = _write_epub(tmp_path, [
        ("Part One", "Content here. " * 20),
        ("Part Two", "More content. " * 20),
    ], epub3=False)
    result = extract_epub(epub)
    sections = result["sections"]
    assert len(sections) == 2
    assert sections[0]["title"] == "Part One"


def test_extract_epub_qa_fields(tmp_path):
    epub = _write_epub(tmp_path, [("Chapter One", "Content. " * 20)])
    result = extract_epub(epub)
    qa = result["qa"]
    assert "spine_items" in qa
    assert "sections_produced" in qa
    assert qa["chapter_source"] == "spine"
