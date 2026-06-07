"""Scanned-PDF extraction: rasterize pages and OCR them with Tesseract.

Phase 0: verbatim port of the v0 behavior (always rasterize + OCR, flat text
joined with PAGE BREAK sentinels). Phase 1 replaces this with per-page block
extraction, preprocessing, confidence scoring, and a digital-PDF fast path —
see docs/03-architecture.md.
"""

from pathlib import Path

from ..binaries import require_tesseract

PAGE_BREAK = "\n\n--- PAGE BREAK ---\n\n"


def pdf_to_images(pdf_path: Path, output_dir: Path, dpi: int = 300,
                  start_page: int = 0, end_page: int = None) -> list:
    import fitz

    print(f"\n[1/5] Converting PDF to images (DPI={dpi})...")
    doc = fitz.open(str(pdf_path))
    end = min(end_page, len(doc)) if end_page else len(doc)
    image_paths = []

    for i in range(start_page, end):
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = doc[i].get_pixmap(matrix=mat, colorspace=fitz.csGRAY)
        img_path = output_dir / f"page_{i:04d}.png"
        pix.save(str(img_path))
        image_paths.append(img_path)
        print(f"  Page {i+1}/{end}   ", end="\r")

    print(f"  {len(image_paths)} pages converted.          ")
    return image_paths


def ocr_images(image_paths: list) -> str:
    import pytesseract
    from PIL import Image

    pytesseract.pytesseract.tesseract_cmd = require_tesseract()

    print(f"\n[2/5] Running OCR on {len(image_paths)} pages...")

    all_text = []
    for i, img_path in enumerate(image_paths):
        text = pytesseract.image_to_string(
            Image.open(img_path), lang="eng", config="--psm 1 --oem 3"
        )
        all_text.append(text)
        print(f"  Page {i+1}/{len(image_paths)}   ", end="\r")

    print(f"  OCR complete.               ")
    return PAGE_BREAK.join(all_text)
