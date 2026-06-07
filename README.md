# audiobooker — PDF → Audiobook

Converts book PDFs into navigable `.m4b` audiobooks using TTS voice models.

> **Status: Phase 1 complete** — extraction v2 is in: manifest-driven builds with
> hash-based resume, per-page digital-vs-scanned detection (born-digital PDFs skip
> OCR entirely), OpenCV preprocessing + Tesseract block OCR with per-page confidence
> scoring, retry ladder, and flagging. Segmentation is still v0-level; the rebuild
> plan lives in [`docs/`](docs/):
>
> 1. [Audit of the v0 implementation](docs/01-audit.md) — what's wrong, with evidence
> 2. [Product vision & scope](docs/02-product-vision.md) — what we're building (voice cloning is dropped)
> 3. [Target architecture](docs/03-architecture.md) — the 8-stage, manifest-driven design
> 4. [Implementation roadmap](docs/04-roadmap.md) — 6 phases with acceptance criteria
> 5. [**Status & handoff**](docs/05-status.md) — where we are, what's next (Phase 2), environment notes

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
audiobook build book.pdf --title "Book Title" --author "Author Name"
audiobook build book.pdf --voice bm_george          # pick a Kokoro voice
audiobook build book.pdf --end-page 20 --output test_run   # quick test slice
```

Voices: `af_heart` (default), `af_nova`, `af_sky`, `am_echo`, `am_michael`,
`am_fenrir`, `bf_emma`, `bm_george`.

The build writes a `<output>_workdir/` next to where you run it (OCR text,
`chapters.json`, per-chapter WAVs) and resumes from it on re-runs. Edit
`chapters.json` to fix titles or `skip` flags, then re-run with `--redo-tts`.

## Layout

- `audiobooker/` — the package: `cli.py`, `manifest.py` (book.json, hash-based
  staleness), `ingest.py` (PDF probe + page classification), `binaries.py`
  (Tesseract/ffmpeg discovery), `extract/` (digital text-layer + preprocessed OCR
  paths → `pages.jsonl` with per-block geometry and confidence), `segment/`
  (cleanup + chapter split), `normalize.py` (TTS chunking), `tts/` (engine
  interface + Kokoro), `synth.py`, `master.py` (M4B assembly).
- `tests/` — pytest suite + golden assets (10-page Firestone scan excerpt).
- `docs/` — audit, vision, architecture, roadmap.
- `firestone/` — the founding test case: Firestone's *The Dialectic of Sex* scan and
  its `_workdir` from the v0 run.
- `miscellaneous/` — unrelated one-off projects (`merlin/`, `spirit_thug/`), the
  Kokoro ONNX model files they use, and `pipeline_v0_reference.py` (the original
  860-line script, kept for reference — superseded by `audiobooker/`).

## Working on the Firestone book

```
cd firestone
audiobook build firestone-shulamith-dialectic-sex-case-feminist-revolution.pdf --title "The Dialectic of Sex" --author "Shulamith Firestone"
```

Run from inside `firestone/` so the existing `_workdir` is reused.
