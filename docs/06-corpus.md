# Test Corpus — provenance & results

PDFs live in `corpus/` (gitignored). This file is the committed record:
where each book came from, why it was chosen, and how the pipeline fared.
Per CLAUDE.md: lawful sources only; diversity over volume; a book that breaks
the pipeline gets minimized into a test, not committed.

## Validated fetch recipe (probed from inside vorpal-box, 2026-06-07)

Discovery and download both work from the container via the archive.org APIs.
The traps are real, so follow the recipe:

1. **Search** `https://archive.org/advancedsearch.php` with `output=json`.
   Query pattern that works:
   `title:("<known public-domain title>") AND mediatype:texts AND
   -collection:(inlibrary OR printdisabled) AND format:("Text PDF")`
   — the `-collection:(inlibrary OR printdisabled)` exclusion is **required**:
   lending-library items are not downloadable and must not be attempted.
2. **Pick files via the metadata API** (`https://archive.org/metadata/<id>`),
   filtering to `.pdf` files with **size > 1 MB** — items routinely carry
   tiny stub/derived PDFs (a 172-byte "PDF" passed a naive probe).
3. **Download** `https://archive.org/download/<id>/<urlencoded name>` with
   `curl -sL` (redirects are normal).
4. **Validate before accepting**: actual file size > 1 MB, opens in pymupdf,
   plausible page count; record text-layer density (low ⇒ scanned ⇒ OCR path,
   which is the more valuable test). Title-match the result — generic queries
   surface garbage (movies, journals, reviews).
5. Prefer **known classics by exact title** (pre-1931 ⇒ US public domain)
   over broad searches. Gutenberg is mostly EPUB/TXT — not a PDF source.

## Corpus

| id | Title / source | Why chosen | Species | Pipeline result |
|---|---|---|---|---|
| `bwb_S0-CQT-657` | *Treasure Island* (1930 printing), archive.org | Recipe-validation probe; true scan (≈0 text layer), 256 pp, 10 MB | scanned | not yet run |

*(Phase 5 agent: extend this table — one row per book, update the result
column after each run.)*
