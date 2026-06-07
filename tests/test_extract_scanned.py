"""Scanned extraction v2: preprocessing units + live-OCR integration.

OCR tests are skipped when Tesseract is unavailable; preprocessing tests run
everywhere (they only need OpenCV + numpy).
"""

import numpy as np
import pytest

from audiobooker.binaries import find_tesseract
from audiobooker.extract.scanned import (
    deskew,
    extract_scanned_page,
    ink_ratio,
    strip_border_artifacts,
)

needs_tesseract = pytest.mark.skipif(
    find_tesseract() is None, reason="Tesseract not installed"
)


def _blank(h=400, w=300):
    return np.full((h, w), 255, dtype=np.uint8)


def test_strip_border_artifacts_removes_binding_shadow():
    img = _blank()
    img[:, 0:6] = 0          # full-height binding shadow at the left edge
    img[100:104, 50:90] = 0  # a small text-like blob in the body
    cleaned = strip_border_artifacts(img)
    assert (cleaned[:, 0:6] == 255).all(), "border bar should be removed"
    assert (cleaned[100:104, 50:90] == 0).all(), "text blob must survive"


def test_strip_border_artifacts_keeps_text_touching_border():
    img = _blank()
    img[0:4, 10:40] = 0  # small component touching the top edge (not a bar)
    cleaned = strip_border_artifacts(img)
    assert (cleaned[0:4, 10:40] == 0).all()


def test_ink_ratio():
    img = _blank(100, 100)
    assert ink_ratio(img) == 0.0
    img[:50, :] = 0
    assert abs(ink_ratio(img) - 0.5) < 1e-9


def test_deskew_noop_on_straight_image():
    img = _blank()
    for y in range(50, 350, 20):   # horizontal "text lines"
        img[y:y + 6, 30:270] = 0
    out = deskew(img.copy(), img)
    assert out.shape == img.shape
    # A straight image should be (nearly) untouched
    assert (out == img).mean() > 0.99


@needs_tesseract
def test_extract_scanned_page_on_firestone_excerpt(firestone_excerpt):
    import fitz
    doc = fitz.open(str(firestone_excerpt))
    page = extract_scanned_page(doc, 0, dpi=200)

    assert page.kind == "scanned"
    assert page.blocks, "expected OCR blocks"
    assert page.conf > 0.5
    assert "feminist" in page.text.lower()
    # bboxes scaled back to PDF points (inside the page rect)
    for b in page.blocks:
        assert b.bbox[2] <= page.width + 2
        assert b.bbox[3] <= page.height + 2
