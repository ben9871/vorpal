# Target Architecture

Design for the rebuilt tool. Each section states *what* the stage does, *how* it avoids
the corresponding failure documented in [01-audit.md](01-audit.md), and what artifact it
produces.

## Overview

Eight stages, manifest-driven, each pure with respect to its inputs:

```
ingest → extract → segment → review → normalize → synth → master → package
```

```
vorpal/                           # the package
├── cli.py                        # argparse entry: build / review / status / redo
├── manifest.py                   # book.json schema, load/save, hash-based staleness
├── ingest.py                     # PDF probe: per-page digital-vs-scanned, outline, metadata
├── extract/
│   ├── digital.py                # PyMuPDF text-layer extraction (blocks w/ bbox+font)
│   ├── scanned.py                # image preprocess + Tesseract OCR (blocks w/ bbox+conf)
│   └── pagemodel.py              # shared Page/Block dataclasses
├── segment/
│   ├── boilerplate.py            # running header/footer/page-number removal
│   ├── footnotes.py              # footnote block detection & removal
│   ├── chapters.py               # outline → TOC-parse → heuristics cascade
│   ├── frontmatter.py            # front/back-matter classification
│   └── repair.py                 # de-hyphenation, mojibake, paragraph reflow
├── normalize.py                  # TTS text normalization + sentence segmentation + chunking
├── tone.py                       # (post-v1) optional LLM tone-tagging pass over chunks
├── tts/
│   ├── base.py                   # TTSEngine interface (incl. optional tone support)
│   └── kokoro_engine.py          # default engine
├── master.py                     # loudness norm, chapter encode, streaming concat
├── package.py                    # m4b mux, chapters, metadata, cover
└── qa.py                         # per-stage quality gates + final report
tests/                            # pytest; unit + golden-book regression
```

The 860-line script becomes ~10 modules, each independently testable.

---

## The manifest (`book.json`) — single source of truth

Created by `ingest`, read/updated by every stage. Replaces "does this file exist?" resume
logic with content-addressed staleness.

```jsonc
{
  "source": { "path": "book.pdf", "sha256": "…", "pages": 274 },
  "settings": { "dpi": 300, "voice": "af_heart", "engine": "kokoro", "speed": 1.0,
                 "bitrate": "64k", "loudness_lufs": -18 },
  "stages": {
    "extract":  { "status": "done", "input_hash": "…", "artifact": "pages.jsonl" },
    "segment":  { "status": "done", "input_hash": "…", "artifact": "chapters.json" },
    "review":   { "status": "approved" },
    "normalize":{ "status": "stale" }          // upstream hash changed → must re-run
  },
  "chapters": [
    { "id": 1, "title": "The Dialectic of Sex", "spoken_intro": "Chapter One.",
      "kind": "chapter", "include": true, "pages": [11, 34],
      "source": "toc",                          // outline | toc | heuristic | manual
      "confidence": 0.95 }
  ],
  "qa": { "pages_flagged": [203, 204], "chunks_failed": 0 }
}
```

Rules:

- Every stage records the hash of its inputs (source + settings + upstream artifact). If
  the hash changes, the stage and everything downstream is `stale` — never silently
  reused. (Fixes audit §5: stale-artifact reuse.)
- Human edits happen **only** in `chapters` (titles, `include`, boundaries,
  `spoken_intro`). `vorpal review` presents the table, the user edits, downstream
  stages re-run — and synthesis re-runs **only for changed chapters**, because chunk
  cache keys are `(chapter_text_hash, voice, engine, speed)`, not filenames. (Fixes
  audit §3: `--redo-tts` nuking everything.)

---

## Stage 1 — `ingest`: probe, don't assume

- Hash the PDF; read page count, metadata (title/author), embedded outline/bookmarks,
  and a candidate cover image (page 1 render).
- **Per-page species detection:** extract the text layer for each page; a page is
  `digital` if it yields a reasonable character count with high dictionary-word ratio,
  else `scanned`. Mixed books (scans with an OCR layer of unknown quality) are scored
  the same way — a *bad* embedded text layer falls back to our own OCR.
- Output: `book.json` skeleton.

*Fixes audit §1: unconditional rasterize+OCR of born-digital PDFs.*

## Stage 2 — `extract`: structured pages, not a flat string

Both paths emit the same structure — **per-page lists of text blocks with geometry**:

```jsonc
{ "page": 27, "blocks": [
    { "bbox": [72, 64, 540, 80],  "text": "28 THE DIALECTIC OF SEX", "font_size": 9.1, "conf": 0.91 },
    { "bbox": [72, 96, 540, 640], "text": "Socialist thinkers prior to …", "font_size": 11.4, "conf": 0.97 }
] }
```

- **Digital path:** PyMuPDF `get_text("dict")` → blocks with bbox + font size/flags.
- **Scanned path:** render at configured DPI → preprocess (grayscale, deskew via Hough/
  projection, binarize, despeckle, **crop gutter/margins**) → Tesseract with TSV output
  (`image_to_data`) so we get per-word confidence and block geometry, not a text dump.
- **Per-page QA score** = mean OCR confidence × dictionary-word ratio. Pages below
  threshold are automatically retried (higher DPI, alternate PSM); still-bad pages are
  flagged in the manifest for the review step instead of poisoning the book.
- Artifact: `pages.jsonl` (one JSON object per page). Page provenance is preserved
  through every later stage.

*Fixes audit §1: no preprocessing, no confidence data, lost page mapping, blockquote text
loss going unnoticed.*

## Stage 3 — `segment`: document understanding, not regex roulette

Runs on structured pages, in this order:

1. **Boilerplate removal** (`boilerplate.py`): cluster blocks by page-relative position
   (top/bottom band) and fuzzy text similarity **across pages**. A block repeating on
   many pages at the same height with ~constant text-modulo-digits is a running
   header/footer — removed everywhere, robust to OCR noise (`SE¥s` ≈ `SEX` under
   Levenshtein). Standalone page numbers likewise. This is categorical removal, not a
   per-line regex guess. *(Kills the 21 surviving headers and their fake chapters.)*
2. **Footnote separation** (`footnotes.py`): bottom-of-page blocks in smaller font
   (digital) or below a horizontal-rule/large-gap with leading numeric markers (scanned)
   → moved to a `footnotes` side-channel (not narrated; optionally appended per-chapter
   later). Superscript markers in body text stripped.
3. **Text repair**: de-hyphenation across line/page breaks (dictionary-checked), Unicode
   NFKC + mojibake/confusable fixes (`’`→`'` class normalization, `SE¥`→ flagged),
   paragraph reflow from block geometry (indent/gap → paragraph break).
4. **Chapter detection** (`chapters.py`) — a cascade, taking the first source that
   validates, recording `source` + `confidence` in the manifest:
   - **a. PDF outline/bookmarks** — ground truth when present (most born-digital books).
   - **b. Printed TOC parsing** — detect TOC pages (dot leaders / trailing page numbers —
     the current code *finds* these pages, then throws them away), parse
     `title → page number` pairs, map printed page numbers to PDF pages via offset
     inference, and **anchor each chapter at a heading-like block near the top of its
     target page**. The TOC tells us exactly how many chapters to expect — a structural
     checksum heuristics can't provide. *(For Firestone this alone yields the correct
     11 chapters instead of 58 guesses.)*
   - **c. Layout heuristics** (only if a and b fail): heading = block with font-size
     outlier (digital) or top-of-page isolated short line following a mostly-blank page
     (scans). Never "any ALL-CAPS line"; a lone `I` is never a heading.
   - **Validation regardless of source:** monotonic page order, plausible chapter count
     for the page count, no chapter under a minimum body length without explicit
     `include` decision, title sanity (dictionary-word ratio — gibberish like
     `ROUVOINWHOD TSAR LHVLSHI` fails and the block is treated as a figure, not a title).
5. **Front/back-matter classification** (`frontmatter.py`): copyright page, printing
   history, dedication, index, "about the author" → labeled `kind: frontmatter|backmatter`,
   default `include: false` but *visible* in review — classified, never silently dropped
   (audit §2's <80-words silent skip).

Artifact: `chapters.json` (embedded in manifest) + `chapters/{id}.txt` body files.

## Stage 4 — `review`: the human checkpoint, made cheap

`vorpal review book.pdf` prints the chapter table (id, kind, title, pages, words,
source, confidence, include) plus any flagged pages, and opens `book.json` for editing.
`vorpal build` proceeds automatically when overall confidence is high (outline/TOC
source, no flags) and pauses for review otherwise. The Firestone run needed manual triage
of 58 junk rows; the target is **approve-or-tweak 11 rows in under a minute**.

## Stage 5 — `normalize`: make text *narratable*

Per chapter, deterministic and unit-tested:

- **Spoken-form normalization:** numbers → words (context-aware: years, ranges,
  ordinals), Roman numerals in headings, abbreviations (`Mr.`, `e.g.`, `pp. 24–26` →
  "pages twenty-four to twenty-six"), `%`/`&`/`§`/`°`, em-dash → comma-pause, quote
  normalization, parenthetical citation stripping (`(Italics mine)` policy-configurable),
  URL/ISBN elision.
- **Sentence segmentation** with a real segmenter (`pysbd` — handles abbreviations,
  initials, ellipses; replaces the hand-rolled regex splitter).
- **Chunking for prosodic coherence:** sentences packed toward the engine's declared
  context size (~400 chars for Kokoro), never splitting a sentence across chunks,
  **preferring paragraph-aligned chunk boundaries** — prosody resets at every chunk
  boundary, so fewer, paragraph-shaped chunks are what make the narration sound like
  one reader rather than a slideshow. Paragraph boundaries are recorded as
  `pause_after_ms` so synthesis inserts the longer beat a human reader would.
- **Tone slot (carried now, filled post-v1):** every chunk has a `tone` field,
  `null`/`"neutral"` by default. The post-v1 `tone.py` pass (an optional LLM call per
  paragraph / n-sentence run — deterministic core, model-assisted edges) fills it with
  a small controlled vocabulary (`neutral`, `somber`, `tense`, `wry`, `excited`, …);
  tone-capable engines act on it, others ignore it. Shipping the field in the v1
  schema means expressiveness arrives later without a chunk-format migration or
  cache invalidation surprise.
- **The no-loss invariant (contract from the vision doc):** every body sentence maps to
  exactly one chunk; the stage asserts `concat(chunks) ≈ chapter_text` (modulo
  normalization) and fails the build otherwise.

Artifact: `chunks/{chapter}.jsonl` — `{ idx, text, pause_after_ms, tone, text_hash }`.

## Stage 6 — `synth`: never silently drop a sentence

- `TTSEngine` interface: `synthesize(text, tone=None) -> (samples, sample_rate)`;
  `kokoro_engine.py` is the default (CPU/GPU auto). Engines declare max chunk length
  (the normalizer packs to it) and `supported_tones` (empty for Kokoro — it ignores
  the hint; future expressive/character-voice engines act on it). *(No voice
  cloning — out of scope per the vision doc; character narrators are an engine
  concern.)*
- **Failure policy** (replaces audit §3's warn-and-skip): on exception → retry once →
  retry with the chunk split in half → if still failing, **abort the build** with a
  report naming chapter, chunk index, and exact text. A `--allow-gaps` escape hatch
  exists but inserts an audible marker tone and lists every gap in the final report —
  silence is never the failure mode.
- **Cache:** chunk WAVs keyed by `(text_hash, engine, voice, speed, tone)` — edits
  invalidate precisely the chunks whose text (or tone tag) changed.
- Chapter intro line uses the manifest's `spoken_intro` (so "Conclusion." not
  "Chapter Eleven." — audit §2).
- Progress: per-chapter bar, rolling ETA, and a final synthesis report (chunks done /
  cached / retried / failed).

## Stage 7 — `master`: real audio mastering, constant memory

- Per chapter: concat chunk WAVs (inserting per-chunk `pause_after_ms`) → **loudness
  normalize to the manifest target (default −18 LUFS, ffmpeg `loudnorm`)** → encode AAC.
- Inter-chapter silence configured in the manifest, not hard-coded.
- All concatenation via **ffmpeg concat demuxer over files** — no whole-book arrays in
  RAM (audit §4's ~3.5 GB problem).

## Stage 8 — `package`: the deliverable

- Mux chapter AACs into `.m4b` with ffmetadata chapter markers, title/author/year/genre
  metadata, and embedded cover (extracted page-1 render, overridable with `--cover`).
- Side products: `chapters_mp3/` per-chapter MP3s; `report.html`/`report.md` — the QA
  summary (pages flagged, chapters and their sources, normalization stats, synthesis
  retries, loudness numbers). The report is what makes the tool trustworthy.

---

## QA gates (cross-cutting, in `qa.py`)

| Stage | Gate | On failure |
|---|---|---|
| extract | page confidence × dictionary ratio ≥ threshold | auto re-OCR → flag page |
| segment | chapter count plausible; titles pass sanity; TOC count matches when TOC parsed | drop to review |
| normalize | no-loss invariant; residual junk lint (`\|` lines, bare numbers, header-like lines) | fail build, name lines |
| synth | zero unrecovered chunk failures | fail build (or marked gaps with `--allow-gaps`) |
| master | per-chapter loudness within ±1 LU of target | re-normalize / fail |
| package | chapter marker count == included chapters; duration sanity vs word count (~150 wpm ±40%) | fail build |

Optional (post-v1): ASR round-trip spot-check — transcribe a random 1% of chunks with a
small Whisper model and alert on word-error-rate outliers. Cheap, catches engine
mispronunciation/derailment classes nothing else catches.

## Dependencies & platform

- Python ≥ 3.10. Core: `pymupdf`, `pytesseract`, `pillow`, `opencv-python-headless`
  (preprocess), `numpy`, `soundfile`, `pysbd`, `rapidfuzz` (boilerplate clustering),
  `kokoro` + `torch` (CPU wheel by default). Dev: `pytest`.
- Binaries: Tesseract, ffmpeg — discovered via `PATH`/`shutil.which` with clear install
  guidance on miss; known Windows locations as fallback, never as the only path
  (audit §5). `imageio-ffmpeg` wheel as a zero-install ffmpeg fallback.
- Packaging: `pyproject.toml` with console-script entry point `audiobook`; pinned
  versions; `setup.bat` reduced to `pip install -e .` against one venv.

## What deliberately stays simple (v1)

- No parallel OCR / batched TTS — correctness first; both are stage-local optimizations
  the architecture already isolates (post-v1 in the roadmap).
- No EPUB input, no config file beyond the manifest, no plugin discovery — the interfaces
  exist, the features don't, until the regression set is green.
