"""Digital extraction path — must work without Tesseract installed."""

import pytest

fitz = pytest.importorskip("fitz")

from audiobooker.extract import extract_pages
from audiobooker.extract.digital import extract_digital_page

BODY = (
    "Socialist thinkers prior to Marx and Engels had been able to do no more "
    "than moralize about existing social inequalities, positing an ideal world "
    "where class privilege and exploitation should not exist. "
) * 4


@pytest.fixture
def book_pdf(tmp_path):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_textbox(fitz.Rect(72, 72, 540, 110), "CHAPTER ONE", fontsize=22)
    page.insert_textbox(fitz.Rect(72, 130, 540, 720), BODY, fontsize=11)
    pdf = tmp_path / "book.pdf"
    doc.save(str(pdf))
    return pdf


def test_digital_page_blocks_with_geometry_and_fonts(book_pdf):
    doc = fitz.open(str(book_pdf))
    page = extract_digital_page(doc, 0)

    assert page.kind == "digital"
    assert page.conf == 1.0
    assert page.quality > 0.6
    assert len(page.blocks) >= 2
    assert "CHAPTER ONE" in page.text
    assert "Socialist thinkers" in page.text

    heading = next(b for b in page.blocks if "CHAPTER ONE" in b.text)
    body = next(b for b in page.blocks if "Socialist" in b.text)
    # Font sizes captured, heading larger than body
    assert heading.font_size > body.font_size
    # Geometry sane: heading above body, boxes inside the page
    assert heading.bbox[1] < body.bbox[1]
    assert all(0 <= v <= max(page.width, page.height) for v in heading.bbox)


def test_extract_pages_digital_path_skips_ocr(book_pdf, monkeypatch):
    """Digital pages must never touch the scanned/OCR path."""
    import audiobooker.extract as extract_mod

    def boom(*a, **k):
        raise AssertionError("scanned path called for a digital page")

    monkeypatch.setattr(extract_mod, "extract_scanned_page", boom)
    pages = extract_pages(book_pdf, [{"index": 0, "kind": "digital"}])
    assert len(pages) == 1
    assert pages[0].kind == "digital"
