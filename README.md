# vorpal — PDF / EPUB / TXT → Audiobook

**vorpal** converts book-shaped text into navigable `.m4b` audiobooks using
local, open-weight TTS models. Point it at a scanned paperback, a Gutenberg
EPUB, or a born-digital academic PDF and get back a clean audiobook with
correct chapters, a consistent high-quality voice, and nothing spurious read
aloud — no running headers, no page numbers, no OCR debris.

The name: it's the blade for the jabberwocky of OCR noise, fake chapters,
and screen-reader monotone.

> **Current state (June 2026):** 43 phases complete. The full pipeline is
> production-ready — extract, segment, normalize, synthesize, master.
> EPUBs, PDFs, and plain text all build cleanly. 11 curated voices including
> blended narrators. Theatrical play mode complete — Shakespeare and Beckett
> with per-character voice casting. In production: Trotsky's *Military
> Writings* Vol. 1 (19h 16m, 38 chapters). Coming next: expressive narration
> via LLM tone tagging and API TTS engines.

---

## New here? Start with the notebooks

| Notebook | What it covers |
|---|---|
| [`notebooks/01_first_audiobook.ipynb`](notebooks/01_first_audiobook.ipynb) | Build your first audiobook end to end |
| [`notebooks/02_voices.ipynb`](notebooks/02_voices.ipynb) | Explore the voice suite and blend recipes |
| [`notebooks/03_manifest_and_pipeline.ipynb`](notebooks/03_manifest_and_pipeline.ipynb) | Understand the pipeline internals |

For the big picture, read the docs in order:
1. [What we're building and where it's going](docs/upcoming.md) — goals, what's done, what's next
2. [Product vision](docs/02-product-vision.md) — the two design contracts
3. [Architecture](docs/03-architecture.md) — the manifest-driven 8-stage design
4. [Roadmap](docs/04-roadmap.md) — every phase with acceptance criteria
5. [Current status](docs/05-status.md) — live state, what's next
6. [Ideation: expressive narration](docs/07-ideation.md) — voices, tone system, north star

---

## What it does

- **Any book-shaped PDF** — scanned or born-digital, two-page spreads, multi-column,
  footnote-heavy. OCR with quality scoring, running-header removal, chapter detection
  that reads the embedded outline before falling back to heuristics.
- **EPUB and plain text** — no OCR needed; structure ships intact. Recommended for
  Project Gutenberg and modern ebooks.
- **Theatrical plays** — per-character voice casting. Feed it *Hamlet* or *Waiting
  for Godot* and each character gets their own narrator voice.
- **11 curated voices** — 8 single voices + 3 blended narrators. Run
  `vorpal voices --sample` to audition them all before committing to a build.
- **Proper mastering** — two-pass loudness normalization (EBU R128), chapter markers,
  cover art, `.m4b` with full navigation, per-chapter MP3 side product.
- **Resumable, reproducible** — content-addressed manifest. Re-running resumes from
  the last clean stage; every stage is independently re-runnable.

### Real-world example

Trotsky's *Military Writings Vol. 1* (EPUB, 38 chapters, ~120,000 words):

```sh
vorpal build trotsky/military-writings-trotsky-v1.epub \
  --voice blend_deep_steady \
  --output trotsky_v1
```

→ `trotsky_v1.m4b` — 19 hours 16 minutes, 38 chapter markers, 569 MB.
Voice: Fenrir 55% + Michael 45% (deep, authoritative, steady).

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

**Voices**: run `vorpal voices` to see the full suite (8 single voices + 3 blends).
Default: `af_heart` (Heart — warm American female).
Blend voices mix two voice embeddings for a new narrator with no training required.

---

## Voices

```sh
vorpal voices                         # list the suite
vorpal voices --sample                # render audition clips → voices_preview/
vorpal voices --sample --text "…"     # custom audition text
```

| ID | Name | Type | Description |
|---|---|---|---|
| `af_heart` | Heart | single | Warm, expressive American female — default |
| `af_nova` | Nova | single | Clear, bright American female |
| `af_sky` | Sky | single | Lighter, airier American female |
| `am_echo` | Echo | single | Resonant American male |
| `am_michael` | Michael | single | Steady, neutral American male |
| `am_fenrir` | Fenrir | single | Deep, commanding American male |
| `bf_emma` | Emma | single | Clear, measured British female |
| `bm_george` | George | single | Distinguished British male |
| `blend_warm_bright` | Warm-Bright | blend | Heart 65% + Nova 35% — warmth with clarity |
| `blend_deep_steady` | Deep-Steady | blend | Fenrir 55% + Michael 45% — depth with steadiness |
| `blend_transatlantic` | Transatlantic | blend | Heart 50% + Emma 50% — American + British |

Blend voices are weighted mixes of Kokoro voice embeddings computed at build time.
Changing a blend recipe in the registry invalidates only that voice's cached audio chunks.

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
vorpal voices [--sample [--text "..."]]
  --sample            Render audition WAV for each voice (requires Kokoro / GPU)
  --text TEXT         Custom audition text for --sample

vorpal build INPUT [options]
  INPUT               PDF, EPUB, or TXT file
  --title TEXT        Audiobook title (overrides metadata)
  --author TEXT       Author (overrides metadata)
  --voice ID          Voice from registry, e.g. blend_warm_bright (default: af_heart)
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
    kokoro_engine.py  Kokoro TTS adapter (single voices + blend tensor support)
    voices.py         Voice registry — curated narrators incl. blend recipes
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
