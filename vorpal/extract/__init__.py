"""Extraction stage: per-page digital-vs-scanned dispatch → pages.jsonl."""

import os
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
    "_extract_page_worker", "_run_ordered",
]

PAGE_BREAK = "\n\n--- PAGE BREAK ---\n\n"


# ─────────────────────────────────────────────
# Parallel helpers (module-level for pickling)
# ─────────────────────────────────────────────

def _extract_page_worker(packed_args):
    """Worker for ProcessPoolExecutor: opens its own fitz doc, extracts one page."""
    pdf_path_str, page_dict, dpi = packed_args
    import fitz
    doc = fitz.open(pdf_path_str)
    try:
        idx = page_dict["index"]
        if page_dict["kind"] == "digital":
            return extract_digital_page(doc, idx)
        else:
            return extract_scanned_page(doc, idx, dpi=dpi)
    finally:
        doc.close()


def _run_ordered(tasks, worker_fn, executor_cls, n_workers):
    """Submit tasks to executor_cls, return results in task-submission order.

    Accepts any executor class (ProcessPoolExecutor in production,
    ThreadPoolExecutor in tests).
    """
    from concurrent.futures import as_completed
    n = len(tasks)
    if n == 0:
        return []
    results = [None] * n
    with executor_cls(max_workers=n_workers) as ex:
        futures = {ex.submit(worker_fn, task): i for i, task in enumerate(tasks)}
        for future in as_completed(futures):
            results[futures[future]] = future.result()
    return results


# ─────────────────────────────────────────────
# Main extraction entry point
# ─────────────────────────────────────────────

def extract_pages(pdf_path: Path, page_kinds: list, dpi: int = 300,
                  start_page: int = 0, end_page: int = None,
                  workers: int = None) -> list:
    """Extract every page via its species' path.

    page_kinds: the manifest's pages list from ingest
    ([{"index": i, "kind": "digital"|"scanned"}, ...]).

    workers: process pool size; defaults to max(1, cpu_count - 1).
             Pass workers=1 to force serial execution.
    """
    import fitz
    from concurrent.futures import ProcessPoolExecutor

    doc = fitz.open(str(pdf_path))
    n_total = len(doc)
    doc.close()

    end = min(end_page, n_total) if end_page else n_total
    selected = [p for p in page_kinds if start_page <= p["index"] < end]
    n_scanned = sum(1 for p in selected if p["kind"] == "scanned")

    if workers is None:
        cpu = os.cpu_count() or 1
        workers = max(1, cpu - 1)

    parallel = workers > 1 and len(selected) > 1
    worker_label = f"workers={workers}" if parallel else "serial"
    print(f"\n[2/5] Extracting {len(selected)} pages "
          f"({len(selected) - n_scanned} digital, {n_scanned} OCR) "
          f"[{worker_label}]...")

    task_args = [(str(pdf_path), p, dpi) for p in selected]
    t0 = time.time()

    if parallel:
        done_counter = [0]

        def _progress_wrapper(args):
            result = _extract_page_worker(args)
            return result

        pages = _run_ordered(task_args, _extract_page_worker, ProcessPoolExecutor, workers)
        # Print a final progress line
        elapsed = time.time() - t0
        print(f"  {len(pages)}/{len(selected)} pages  "
              f"(parallel, {elapsed:.1f}s total)            ")
    else:
        pages = []
        for done, args in enumerate(task_args, 1):
            page = _extract_page_worker(args)
            pages.append(page)
            rate = (time.time() - t0) / done
            eta = int(rate * (len(task_args) - done))
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
