"""Phase 2 regression: born-digital book (outline rung, zero edits) and
outline-less digital book (printed-TOC rung) — docs/04-roadmap.md Phase 2
acceptance. Both PDFs are generated on the fly with PyMuPDF, including the
hostile furniture a real book has: running headers, page numbers, and a
small-font numbered footnote.
"""

import pytest

fitz = pytest.importorskip("fitz")

from vorpal.extract.digital import extract_digital_page
from vorpal.segment import segment_pages

W, H = 595, 842
BODY = (
    "The argument advances by small steps, each one earned from the last, "
    "and the reader is carried along with it through the long middle of the "
    "book where the real work of persuasion is done. "
)
TITLES = ["1. The First Door", "2. A Long Corridor", "3. The Last Room",
          "Conclusion"]


def _add_body_page(doc, printed_no, header):
    page = doc.new_page(width=W, height=H)
    page.insert_text((72, 40), f"{printed_no} {header}", fontsize=8)
    page.insert_textbox(fitz.Rect(72, 130, 523, 700), BODY * 6, fontsize=11)
    page.insert_text((290, 810), str(printed_no), fontsize=8)
    return page


def make_digital_book(with_outline: bool, tmp_path):
    """A 14-page digital book: title page, contents page, four sections of
    three pages each, with running headers and folios throughout."""
    doc = fitz.open()

    title_page = doc.new_page(width=W, height=H)
    title_page.insert_text((180, 300), "THE TEST BOOK", fontsize=24)
    title_page.insert_text((200, 340), "A Regression Fable", fontsize=12)

    contents = doc.new_page(width=W, height=H)
    contents.insert_text((260, 100), "CONTENTS", fontsize=14)
    y = 160
    for i, t in enumerate(TITLES):
        printed_first_page = 3 + i * 3
        contents.insert_text((100, y), f"{t} {'.' * 40} {printed_first_page}",
                             fontsize=11)
        y += 24

    outline, printed_no = [], 3
    for i, t in enumerate(TITLES):
        outline.append([1, t, doc.page_count + 1])
        first = _add_body_page(doc, printed_no, "THE TEST BOOK")
        first.insert_text((72, 100), t.upper().lstrip("0123456789. "), fontsize=18)
        printed_no += 1
        for _ in range(2):
            _add_body_page(doc, printed_no, "THE TEST BOOK")
            printed_no += 1

    # a small-font numbered footnote at the bottom of one mid-book page
    doc[5].insert_text((72, 760), "1. A digital footnote in the small print, "
                                  "set well below the body.", fontsize=8)

    if with_outline:
        doc.set_toc(outline)
    path = tmp_path / ("outline.pdf" if with_outline else "no_outline.pdf")
    doc.save(str(path))
    doc.close()
    return path


def _segment(path):
    doc = fitz.open(str(path))
    pages = [extract_digital_page(doc, i) for i in range(len(doc))]
    outline = [{"level": l, "title": t, "page": p}
               for l, t, p in doc.get_toc(simple=True)]
    doc.close()
    return segment_pages(pages, outline=outline)


def _assert_acceptance(result):
    chapters = [s for s in result.sections if s.include]
    assert [s.title for s in chapters] == TITLES
    assert next(s for s in chapters if s.title == "Conclusion").spoken_intro == \
        "Conclusion."
    # zero running headers / folios in any narrated body
    for s in chapters:
        body = result.bodies[s.id]
        assert "TEST BOOK" not in body, f"running header survived in {s.title!r}"
        assert "A digital footnote" not in body
    # front matter visible, not narrated
    front = [s for s in result.sections if s.kind == "frontmatter"]
    assert front and all(not s.include for s in front)


def test_born_digital_with_outline_zero_edits(tmp_path):
    result = _segment(make_digital_book(True, tmp_path))
    assert result.source == "outline"
    assert all(s.confidence >= 0.95 for s in result.sections if s.include)
    _assert_acceptance(result)


def test_outline_less_digital_via_printed_toc(tmp_path):
    result = _segment(make_digital_book(False, tmp_path))
    assert result.source == "toc"
    _assert_acceptance(result)
    assert result.qa["footnotes_separated"] == 1
