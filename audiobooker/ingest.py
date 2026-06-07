"""Ingest stage: probe the PDF and populate the manifest.

- Hashes the source PDF (basis for all stage staleness)
- Reads page count, metadata (title/author), and the embedded outline
- Classifies every page digital-vs-scanned from its text layer, so extraction
  can take the lossless fast path wherever one exists
"""

from pathlib import Path

from .extract.quality import text_quality
from .manifest import Manifest, hash_parts, sha256_file

# A page is "digital" when its embedded text layer is substantial AND reads
# like prose. A bad embedded OCR layer (garbage text) fails the quality test
# and falls back to our own OCR.
MIN_DIGITAL_CHARS = 100
MIN_DIGITAL_QUALITY = 0.5


def classify_page_text(text: str) -> str:
    stripped = text.strip()
    if len(stripped) >= MIN_DIGITAL_CHARS and text_quality(stripped) >= MIN_DIGITAL_QUALITY:
        return "digital"
    return "scanned"


def ingest(pdf_path: Path, manifest: Manifest) -> None:
    """Populate manifest.source and manifest.pages. Idempotent via hashing."""
    import fitz

    source_hash = sha256_file(pdf_path)
    input_hash = hash_parts("ingest-v1", source_hash)

    if manifest.stage_fresh("ingest", input_hash):
        print(f"[1/5] Ingest fresh — {len(manifest.data['pages'])} pages probed")
        return

    print(f"\n[1/5] Probing PDF...")
    doc = fitz.open(str(pdf_path))

    meta = doc.metadata or {}
    outline = doc.get_toc(simple=True)  # [[level, title, 1-based page], ...]

    pages = []
    n_digital = 0
    for i in range(len(doc)):
        kind = classify_page_text(doc[i].get_text())
        if kind == "digital":
            n_digital += 1
        pages.append({"index": i, "kind": kind})

    manifest.data["source"] = {
        "path": str(pdf_path),
        "sha256": source_hash,
        "pages": len(doc),
        "title": (meta.get("title") or "").strip(),
        "author": (meta.get("author") or "").strip(),
        "outline": [
            {"level": lvl, "title": title.strip(), "page": page}
            for lvl, title, page in outline
        ],
    }
    manifest.data["pages"] = pages

    n_scanned = len(pages) - n_digital
    print(f"  {len(doc)} pages: {n_digital} digital, {n_scanned} scanned")
    if outline:
        print(f"  Embedded outline: {len(outline)} entries (chapter ground truth)")
    if manifest.source["title"]:
        print(f"  Metadata title: {manifest.source['title']}")

    manifest.stage_done("ingest", input_hash)
