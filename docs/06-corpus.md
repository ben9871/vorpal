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

**Gutenberg (EPUB/TXT — Phase 5 multi-format input landed):** direct,
robot-friendly URLs per book id `N`:
`https://www.gutenberg.org/cache/epub/N/pg-N.images.epub` (or `pgN.epub`),
`https://www.gutenberg.org/cache/epub/N/pgN.txt` — find ids via
`https://gutendex.com/books?search=<title>` (JSON API). Validate like PDFs:
size sanity, opens (zipfile for EPUB), title match.

## Corpus

| id | Title / source | Why chosen | Species | Pipeline result |
|---|---|---|---|---|
| `bwb_S0-CQT-657` | *Treasure Island* (1930 printing), archive.org | Recipe-validation probe; true scan (≈0 text layer), 256 pp, 10 MB | scanned PDF | not yet run (not in corpus dir) |
| `callofwild1915lond` | *The Call of the Wild* (1915, BYU/Americana), archive.org — `callofwild1915lond.pdf` | Scanned, 212 pp, 15 MB; different publisher/era from Firestone | scanned PDF | ✅ `--stop-after segment`: 6 chapters via **toc** path, 174 headers removed, no crash |
| `meditationsofmar00marc_0` | *Meditations of Marcus Aurelius* tr. George Long (1910), archive.org — `meditationsofmar00marc_0.pdf` | Scanned, 230 pp, 8.2 MB; non-narrative numbered paragraphs — different structure from novels | scanned PDF | ✅ `--stop-after segment`: **heuristic** path, 256 headers removed, no crash; needs review (expected) |
| `gutenberg-120` | *Treasure Island*, R.L. Stevenson, Gutenberg id 120 — `treasure_island_pg120.epub` | EPUB multi-format; 38 spine items; classic adventure | EPUB | ✅ 37 ch detected; TOC structural quirk in this Gutenberg EPUB (many spine items share title "TREASURE ISLAND") — pauses for review (correct); no crash |
| `gutenberg-120-txt` | *Treasure Island*, R.L. Stevenson, Gutenberg id 120 — `treasure_island_pg120.txt` | TXT multi-format; 400 KB, ~71 K words | TXT | ✅ 13 sections detected (PART + roman numeral chapters); dot-leader TOC entries correctly skipped; some short-body flags (PART headers) — pauses for review (correct); no crash |
| `gutenberg-201` | *Flatland*, Edwin A. Abbott, Gutenberg id 201 — `flatland_pg201.epub` | Short EPUB (150 KB, 5 spine items); 2-part structure | EPUB | ✅ 3 ch / 1 front / 1 back; **auto-approves** (spine source, no flags); no crash |
| `gutenberg-1342` | *Pride and Prejudice*, Jane Austen, Gutenberg id 1342 — `pride_and_prejudice_pg1342.epub` | EPUB; 16 spine items; dialogue-heavy; most-downloaded Gutenberg text | EPUB | ✅ 15 ch / 1 front; TOC labels in this EPUB contain chapter excerpts (Gutenberg format quirk) — pauses for review (correct); no crash |
| `gutenberg-1342-txt` | *Pride and Prejudice*, Jane Austen, Gutenberg id 1342 — `pride_and_prejudice_pg1342.txt` | TXT; 772 KB, ~130 K words; same book as EPUB — format parity | TXT | ✅ 61 chapters detected, all substantial word counts; heuristic source → review pause; ≤ 2 edits needed (ch1 title has stray `]`); no crash |
| `gutenberg-1661` | *The Adventures of Sherlock Holmes*, A. Conan Doyle, Gutenberg id 1661 — `sherlock_holmes_pg1661.epub` | EPUB; 15 spine items; short-story collection | EPUB | ✅ 13 ch / 1 front / 1 back (PG license); **auto-approves**; titles clean (I. A Scandal in Bohemia, etc.); no crash |

## Synthetic hostile-case fixtures (Phase 20 — `tests/test_phase20_corpus.py`)

Generated in-process with PyMuPDF. Not stored in `corpus/` — regenerated from test code.
All run through `--stop-after segment`.

| id | Description | Why chosen | Species | Pipeline result |
|---|---|---|---|---|
| `all_caps_headings` | ALL-CAPS chapter titles, printed TOC, 4 chapters | Normalization + TOC parse with uppercased input | synthetic digital PDF | ✅ toc path; titles found; heading text not in body |
| `heavy_footnotes` | 3 chapters with ¹–⁴ footnote markers + footnote block at page bottom | Footnote-separator path; body integrity | synthetic digital PDF | ✅ no crash; footnotes_separated ≥ 0 |
| `non_ascii_titles` | French chapter titles (accented characters), printed TOC | Encoding safety; NFKC normalization path | synthetic digital PDF | ✅ no crash; non-empty bodies; TOC path |
| `many_short_chapters` | 20 single-paragraph chapters, embedded outline | Many sections; short-body flag path | synthetic digital PDF | ✅ ≥ 10 chapter sections found via outline; no crash |
| `no_toc_no_outline` | 4 "Part N" chapters, no outline, no printed TOC | Pure heuristic heading detection (font-size outlier) | synthetic digital PDF | ✅ heuristic path; 4 chapters found; no crash |
| `long_chapter_titles` | Titles > 80 chars, printed TOC | `safe_filename()` and downstream title handling | synthetic digital PDF | ✅ no crash; all sections have str titles; TOC path |
| `blank_pages` | Blank pages interspersed between 4 chapters, embedded outline | Empty-page tolerance; blank pages not treated as content | synthetic digital PDF | ✅ ≥ 2 included chapters; no crash; outline path |
| `nested_headings` | 3-level outline (ch → section → subsection), printed TOC | Level-filtering; subsections treated as content not chapters | synthetic digital PDF | ✅ ≥ 1 included chapter; no crash; level-1 only |

### Bug found and fixed (Phase 20)

**`vorpal/segment/boilerplate.py`** — `MAX_BOILER_FONTSIZE = 13` guard:
Numbered chapter headings ("Chapter 1", "Chapter 2", …) normalized to
the same string ("Chapter #") and were clustered as boilerplate when 4+
appeared in the top band. Added a font-size guard: blocks > 13pt are
excluded from band candidates entirely. Chapter headings have large fonts
(typically ≥ 16pt); running headers have small fonts (≤ 10pt). Digital only
(scanned blocks have `font_size=None`).
