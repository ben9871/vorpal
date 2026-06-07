# vorpal — PDF / EPUB / TXT → Audiobook

Converts book-shaped text into navigable `.m4b` audiobooks with TTS voice
models.  One two, one two, and through and through: the jabberwocky in
question is running headers, OCR noise, fake chapters, and screen-reader
monotone that a naïve PDF→TTS pipe narrates at you.

> **Status: Phases 0–5 complete** (0.x personal tooling — no release).
> The full pipeline: PDF / EPUB / TXT input → manifest-driven build with
> hash-based resume → per-page digital/OCR extraction → outline → printed-TOC →
> heuristic chapter detection → `vorpal review` checkpoint → prosody-aware
> normalization → cached TTS synthesis → loudness-normalized M4B with chapter
> markers.  Next: Arc 2 — voice suite & expressive narration.
> Plan lives in [`docs/`](docs/):
>
> 1. [Audit of v0](docs/01-audit.md) — what was wrong, with evidence
> 2. [Product vision](docs/02-product-vision.md) — what we're building (voice cloning: dropped)
> 3. [Architecture](docs/03-architecture.md) — the manifest-driven 8-stage design
> 4. [Roadmap](docs/04-roadmap.md) — phases with acceptance criteria
> 5. [**Status & handoff**](docs/05-status.md) — where we are, what's next
> 6. [Ideation: expressive narration](docs/07-ideation.md) — voices, tone system, north star

---

## Installation

**Requires Python 3.10–3.12** (not 3.13 — the Kokoro TTS engine caps at 3.12),
[Tesseract OCR](https://tesseract-ocr.github.io/tessdoc/Installation.html),
and [ffmpeg](https://www.gyan.dev/ffmpeg/builds/).

```sh
pip install -e .                    # editable install (adds `vorpal` to PATH)
# or with the LLM extras (tone tagging, Phase 8):
pip install -e ".[llm]"
```

**Docker / vorpal-box** (the canonical autonomous setup — everything pre-installed):
```sh
docker/run.ps1                      # Windows PowerShell
```
See `CLAUDE.md` for the full environment matrix (Windows dev box, container, plain Linux).

---

## Quick start

```sh
# PDF → M4B (full build)
vorpal build book.pdf

# EPUB → M4B (no OCR needed — structure ships intact)
vorpal build book.epub

# Plain text → M4B (Gutenberg TXT, etc.)
vorpal build book.txt --title "My Book" --author "Author Name"

# Quick slice for testing
vorpal build book.pdf --end-page 20 --output test_run

# Different voice
vorpal build book.pdf --voice bm_george
```

**Voices** (Kokoro): `af_heart` *(default)*, `af_nova`, `af_sky`, `am_echo`,
`am_michael`, `am_fenrir`, `bf_emma`, `bm_george`.

---

## Build workflow

```
vorpal build book.pdf            # runs all 5 stages; resumes from workdir
vorpal build book.pdf --stop-after extract    # stops after OCR (inspect pages.jsonl)
vorpal build book.pdf --stop-after segment    # stops after chapter detection (inspect chapter_texts/)

vorpal review book.pdf           # print chapter table
vorpal review book.pdf --approve # unlock a paused build
```

The build writes `<output>_workdir/` containing the `book.json` manifest,
`pages.jsonl`, chapter texts, per-chapter WAVs, and mastering artefacts.
Every stage is content-addressed — re-running resumes from the last clean
stage.  When chapter detection is uncertain (heuristic source, validation
flags) the build **pauses** and asks for `vorpal review --approve`; edit
`chapters` in `book.json` first if needed.

### Stage summary

| Stage | Input | Output | Triggers |
|---|---|---|---|
| Ingest | PDF / EPUB / TXT | `book.json` source + page list | file hash |
| Extract (PDF only) | PDF pages | `pages.jsonl` (geometry + OCR) | file hash + settings |
| Parse (EPUB / TXT) | EPUB spine or TXT headings | chapter list with bodies | file hash |
| Segment (PDF only) | `pages.jsonl` | chapter list (boilerplate removed) | extract hash |
| Review gate | chapter list | approval in `book.json` | always on heuristic/flagged results |
| TTS | chapter texts | per-chapter WAVs | text hash + voice/speed |
| Mastering | chapter WAVs | `.m4b` + `chapters_mp3/` + `report.md` | WAV hash + LUFS/bitrate |

---

## Input formats

### PDF
Full pipeline: rasterize → OCR (Tesseract) → boilerplate removal → footnote
separation → chapter detection cascade (outline → printed-TOC → layout
heuristics).  Two-page-spread scans, multi-column layouts, and born-digital
PDFs all handled.

### EPUB
Parses the OPF spine + NAV/NCX table of contents directly — no OCR, no
geometry.  Chapter structure is ground truth (`source: spine`); auto-approves
for clean EPUBs.  Recommended for Project Gutenberg and modern ebooks.

### Plain text (TXT)
Detects chapter headings via pattern matching (`CHAPTER I`, `CHAPTER 5`,
`PART ONE`, roman numeral + period, etc.).  Strips Project Gutenberg
boilerplate.  Falls back to a single section if no structure is found.
Source is `heuristic`; will pause for review.

---

## Corpus (lawful sources)

Test books live in `corpus/` (gitignored — PDFs/EPUBs stay out of git).
Provenance and results recorded in [`docs/06-corpus.md`](docs/06-corpus.md).
Pull from:
- **[Internet Archive](https://archive.org)** — scanned PDFs, pre-1931 public domain
- **[Project Gutenberg](https://gutenberg.org)** — EPUB / TXT, nearly everything

The validated fetch recipe (including lending-library traps) is in `docs/06-corpus.md`.

---

## Manifest reference (`book.json`)

```jsonc
{
  "source": {
    "path": "book.pdf",
    "format": "pdf",          // "pdf" | "epub" | "txt"
    "sha256": "...",
    "title": "Book Title",    // from metadata or --title flag
    "author": "Author Name",
    "outline": [...]           // PDF only: embedded TOC
  },
  "settings": {
    "target_lufs": -18.0,
    "inter_chapter_silence_ms": 1500,
    "aac_bitrate": "64k"
  },
  "chapters": [
    {
      "id": 1,
      "title": "Chapter One",
      "kind": "chapter",        // "chapter" | "frontmatter" | "backmatter" | "figure"
      "include": true,
      "spoken_intro": "Chapter one. The Beginning.",
      "source": "outline",      // "outline" | "toc" | "heuristic" | "spine" | "manual"
      "confidence": 0.95,
      "words": 4231,
      "flags": [],
      // PDF: "start" / "end" are [page_index, block_index] references
      // EPUB/TXT: "body" holds the text inline
    }
  ]
}
```

Edit `chapters` entries — especially `title`, `include`, `spoken_intro` — then
run `vorpal review --approve` to continue.

---

## Flags explained

| Flag | Meaning |
|---|---|
| `short-body` | Chapter body is < 100 words — check for mis-detected headings |
| `no-structure-found` | Whole book as one section; structural detection found nothing |
| `title-sanity` | Chapter title fails word-likeness check — may be a figure caption |

---

## Command reference

```
vorpal build INPUT [options]
  INPUT               PDF, EPUB, or TXT file
  --title TEXT        Audiobook title (overrides metadata)
  --author TEXT       Author (overrides metadata)
  --voice VOICE       Kokoro voice (default: af_heart)
  --speed N           Narration speed multiplier (default: 1.0)
  --output STEM       Output stem (default: input filename without extension)
  --dpi N             OCR rasterisation DPI (default: 300, PDF only)
  --start-page N      Skip to page N (PDF only, 0-indexed)
  --end-page N        Stop at page N exclusive (PDF only)
  --redo-extract      Re-run extraction / OCR even if cached
  --redo-segment      Re-run segmentation / format parse
  --redo-tts          Delete existing WAVs and re-synthesise
  --allow-gaps        Insert audible beep markers for failed chunks (default: abort)
  --stop-after STAGE  Stop after "extract" or "segment" (inspection)
  --keep-temp         Do not delete intermediate WAV files after mastering

vorpal review INPUT [--output STEM] [--approve]
```

---

## Project layout

```
vorpal/
  cli.py              Entry point, argument parsing, pipeline driver
  manifest.py         book.json — content-addressed staleness tracking
  ingest.py           Probe source file, detect format, hash
  binaries.py         Tesseract / ffmpeg / ffprobe discovery
  extract/
    digital.py        PyMuPDF text-layer extraction
    scanned.py        OpenCV preprocess → Tesseract OCR
    epub.py           EPUB spine + NAV/NCX → sections with body text
    text.py           Plain-text chapter heuristics → sections
    pagemodel.py      Block / Page data model + pages.jsonl I/O
    quality.py        OCR quality scoring
  segment/
    boilerplate.py    Cross-page running-header removal
    footnotes.py      Footnote separation
    repair.py         De-hyphenation, mojibake fix, paragraph reflow
    chapters.py       Chapter detection cascade (Section model)
    frontmatter.py    Front/back-matter classification
  normalize.py        Spoken-form normalisation + prosody-aware chunking
  tts/
    base.py           TTSEngine interface
    kokoro_engine.py  Kokoro TTS adapter
  synth.py            Per-chapter synthesis, chunk cache, retry policy
  master.py           Loudnorm, M4B assembly, mastering cache, chapter gate
tests/               pytest suite + fixture assets
docs/                Architecture, roadmap, status, corpus table
```

---

## Developing

```sh
python -m pytest -q                  # must be green before every commit
vorpal build scratch/outline.pdf --stop-after segment  # quick smoke-test

# Full regression (no TTS — just structure):
vorpal build tests/assets/firestone_excerpt_p15-24.pdf --stop-after segment
python -m pytest tests/test_regression_digital.py -v
```

The test suite runs on small fixtures (seconds, deterministic).  Full-book runs
are acceptance/corpus activities whose results are recorded in `docs/05-status.md`,
never asserted in pytest.
