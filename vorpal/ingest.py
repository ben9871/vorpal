"""Ingest stage: probe the source file and populate the manifest.

Supports PDF, EPUB, and plain-text input.  For PDFs the full
extract+segment pipeline runs downstream.  For EPUB/TXT a single "parse"
stage replaces both extract and segment.

- Hashes the source file (basis for all stage staleness)
- PDF: reads page count, metadata (title/author), and the embedded outline;
  classifies every page digital-vs-scanned
- EPUB: records format; metadata comes from OPF (populated at parse time)
- TXT: records format; metadata may be in Gutenberg header (parsed later)
"""

from pathlib import Path

from .manifest import Manifest, hash_parts, sha256_file

# A page is "digital" when its embedded text layer is substantial AND reads
# like prose. A bad embedded OCR layer (garbage text) fails the quality test
# and falls back to our own OCR.
MIN_DIGITAL_CHARS = 100
MIN_DIGITAL_QUALITY = 0.5

_SUPPORTED_FORMATS = {".pdf", ".epub", ".txt"}


def detect_format(path: Path) -> str:
    """Return 'pdf', 'epub', or 'txt' based on file extension."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "pdf"
    if suffix == ".epub":
        return "epub"
    if suffix in (".txt", ".text"):
        return "txt"
    raise ValueError(
        f"Unsupported format: {suffix!r}.  Supported: {', '.join(sorted(_SUPPORTED_FORMATS))}"
    )


def classify_page_text(text: str) -> str:
    from .extract.quality import text_quality
    stripped = text.strip()
    if len(stripped) >= MIN_DIGITAL_CHARS and text_quality(stripped) >= MIN_DIGITAL_QUALITY:
        return "digital"
    return "scanned"


def ingest(source_path: Path, manifest: Manifest) -> None:
    """Populate manifest.source. Idempotent via hashing.

    For PDFs also populates manifest.pages (per-page kind list).
    For EPUB/TXT the 'pages' list stays empty; the parse stage fills sections.
    """
    fmt = detect_format(source_path)
    source_hash = sha256_file(source_path)
    input_hash = hash_parts("ingest-v2", source_hash, fmt)

    if manifest.stage_fresh("ingest", input_hash):
        print(f"[1/5] Ingest fresh — format: {manifest.source.get('format', fmt)}")
        return

    print(f"\n[1/5] Probing {fmt.upper()}...")

    if fmt == "pdf":
        _ingest_pdf(source_path, source_hash, manifest)
    elif fmt == "epub":
        _ingest_epub(source_path, source_hash, manifest)
    else:
        _ingest_txt(source_path, source_hash, manifest)

    manifest.stage_done("ingest", input_hash)


def _ingest_pdf(pdf_path: Path, source_hash: str, manifest: Manifest) -> None:
    import fitz

    doc = fitz.open(str(pdf_path))
    meta = doc.metadata or {}
    outline = doc.get_toc(simple=True)

    pages = []
    n_digital = 0
    for i in range(len(doc)):
        kind = classify_page_text(doc[i].get_text())
        if kind == "digital":
            n_digital += 1
        pages.append({"index": i, "kind": kind})

    manifest.data["source"] = {
        "path": str(pdf_path),
        "format": "pdf",
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


def _ingest_epub(epub_path: Path, source_hash: str, manifest: Manifest) -> None:
    manifest.data["source"] = {
        "path": str(epub_path),
        "format": "epub",
        "sha256": source_hash,
        "title": "",
        "author": "",
        "outline": [],
    }
    manifest.data["pages"] = []
    print(f"  EPUB: will parse spine/TOC at next stage")


def _ingest_txt(txt_path: Path, source_hash: str, manifest: Manifest) -> None:
    manifest.data["source"] = {
        "path": str(txt_path),
        "format": "txt",
        "sha256": source_hash,
        "title": "",
        "author": "",
        "outline": [],
    }
    manifest.data["pages"] = []
    print(f"  TXT: will parse chapter headings at next stage")
