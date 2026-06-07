# vorpal — PDF → Audiobook

Converts book PDFs into navigable `.m4b` audiobooks using TTS voice models.
One two, one two, and through and through: the jabberwocky in question is the
running headers, OCR noise, fake chapters, and screen-reader monotone that a
naive PDF→TTS pipe narrates at you.

> **Status: Phase 2 complete** — segmentation v2 is in: cross-page boilerplate
> clustering, footnote separation, text repair, the outline → printed-TOC →
> heuristics chapter cascade, and the `vorpal review` checkpoint. Normalization
> and synthesis are still v0-level; the rebuild plan lives in [`docs/`](docs/):
>
> 1. [Audit of the v0 implementation](docs/01-audit.md) — what's wrong, with evidence
> 2. [Product vision & scope](docs/02-product-vision.md) — what we're building (voice cloning is dropped)
> 3. [Target architecture](docs/03-architecture.md) — the 8-stage, manifest-driven design
> 4. [Implementation roadmap](docs/04-roadmap.md) — 6 phases with acceptance criteria
> 5. [**Status & handoff**](docs/05-status.md) — where we are, what's next (Phase 3), environment notes

## Setup

Requires Python 3.10–3.12 (**not 3.13** — the kokoro TTS engine caps at 3.12),
[Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki), and
[ffmpeg](https://www.gyan.dev/ffmpeg/builds/). Then:

```
setup.bat                 # creates .venv and installs the package (Windows)
# or manually:
pip install -r requirements.txt
```

## Usage

```
vorpal build book.pdf --title "Book Title" --author "Author Name"
vorpal build book.pdf --voice bm_george             # pick a Kokoro voice
vorpal build book.pdf --end-page 20 --output test_run      # quick test slice
vorpal review book.pdf                              # inspect detected chapters
vorpal review book.pdf --approve                    # unlock a paused build
```

(`audiobook` still works as a legacy alias for `vorpal`.)

Voices: `af_heart` (default), `af_nova`, `af_sky`, `am_echo`, `am_michael`,
`am_fenrir`, `bf_emma`, `bm_george`.

The build writes a `<output>_workdir/` next to where you run it (`book.json`
manifest, `pages.jsonl`, chapter texts, per-chapter WAVs) and resumes from it
on re-runs via content hashing. Chapter detection that can't be trusted
automatically (no outline/TOC, or validation flags) pauses the build for
review; edit `chapters` in `book.json`, then `vorpal review --approve`.

## Layout

- `vorpal/` — the package: `cli.py`, `manifest.py` (book.json, hash-based
  staleness), `ingest.py` (PDF probe + page classification), `binaries.py`
  (Tesseract/ffmpeg discovery), `extract/` (digital text-layer + preprocessed OCR
  paths → `pages.jsonl` with per-block geometry and confidence), `segment/`
  (boilerplate/footnotes/repair + chapter cascade + front-matter classification),
  `normalize.py` (TTS chunking), `tts/` (engine interface + Kokoro), `synth.py`,
  `master.py` (M4B assembly).
- `tests/` — pytest suite + golden assets (10-page Firestone scan excerpt,
  generated digital regression books).
- `docs/` — audit, vision, architecture, roadmap, status.
- `firestone/` — the founding test case: Firestone's *The Dialectic of Sex* scan and
  its `_workdir` from the v0 run.
- `miscellaneous/` — unrelated one-off projects (`merlin/`, `spirit_thug/`), the
  Kokoro ONNX model files they use, and `pipeline_v0_reference.py` (the original
  860-line script, kept for reference — superseded by `vorpal/`).

## Working on the Firestone book

```
cd firestone
vorpal build firestone-shulamith-dialectic-sex-case-feminist-revolution.pdf --title "The Dialectic of Sex" --author "Shulamith Firestone"
```

Run from inside `firestone/` so the existing `_workdir` is reused.
