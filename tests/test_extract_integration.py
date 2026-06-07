"""Integration test: rasterize + OCR one page of the Firestone excerpt.

Requires the Tesseract binary; skipped when unavailable. Assertions are loose
(expected words, not exact text) so they hold across Tesseract versions.
"""

import pytest

from audiobooker.binaries import find_tesseract
from audiobooker.extract import ocr_images, pdf_to_images

pytestmark = pytest.mark.skipif(
    find_tesseract() is None, reason="Tesseract not installed"
)


def test_ocr_first_excerpt_page(firestone_excerpt, tmp_path):
    images = pdf_to_images(firestone_excerpt, tmp_path, dpi=200, end_page=1)
    assert len(images) == 1
    assert images[0].exists()

    text = ocr_images(images)
    assert len(text) > 200
    # Page 15 of the scan is body text from the W.R.M. history chapter
    assert "feminist" in text.lower()
