"""Extraction stage: per-page digital-vs-scanned dispatch → pages.jsonl."""

import time
from pathlib import Path

from .digital import extract_digital_page
from .pagemodel import Block, Page, read_pages_jsonl, write_pages_jsonl
from .quality import page_score, text_quality
from .scanned import extract_scanned_page

__all__ = [
    "Block", "Page", "read_pages_jsonl", "write_pages_jsonl",
    "extract_digital_page", "extract_scanned_page", "extract_pages",
    "page_score", "text_quality", "PAGE_BREAK", "pages_to_flat_text",
]

PAGE_BREAK = "\n\n--- PAGE BREAK ---\n\n"


def extract_pages(pdf_path: Path, page_kinds: list, dpi: int = 300,
                  start_page: int = 0, end_page: int = None) -> list:
    """Extract every page via its species' path.

    page_kinds: the manifest's pages list from ingest
    ([{"index": i, "kind": "digital"|"scanned"}, ...]).
    """
    import fitz

    doc = fitz.open(str(pdf_path))
    end = min(end_page, len(doc)) if end_page else len(doc)
    selected = [p for p in page_kinds if start_page <= p["index"] < end]
    n_scanned = sum(1 for p in selected if p["kind"] == "scanned")

    print(f"\n[2/5] Extracting {len(selected)} pages "
          f"({len(selected) - n_scanned} digital, {n_scanned} OCR)...")

    pages = []
    t0 = time.time()
    for done, p in enumerate(selected, 1):
        if p["kind"] == "digital":
            page = extract_digital_page(doc, p["index"])
        else:
            page = extract_scanned_page(doc, p["index"], dpi=dpi)
        pages.append(page)

        rate = (time.time() - t0) / done
        eta = int(rate * (len(selected) - done))
        print(f"  Page {done}/{len(selected)}  "
              f"(score {page.score:.2f}{', FLAGGED' if page.flagged else ''})  "
              f"ETA {eta//60}m {eta%60}s        ", end="\r")

    print()
    flagged = [p.index for p in pages if p.flagged]
    scanned_pages = [p for p in pages if p.kind == "scanned" and p.blocks]
    if scanned_pages:
        mean_conf = sum(p.conf for p in scanned_pages) / len(scanned_pages)
        print(f"  Mean OCR confidence: {mean_conf:.3f}  |  "
              f"flagged pages: {len(flagged)}/{len(pages)}")
    if flagged:
        print(f"  Flagged for review: {flagged}")
    return pages


def pages_to_flat_text(pages: list) -> str:
    """Derive the v0-style flat text (PAGE BREAK sentinels) from structured
    pages, so the v0 segmentation stage keeps working until Phase 2."""
    return PAGE_BREAK.join(page.text for page in pages)
