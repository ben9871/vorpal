# vorpal — agent onboarding

PDF → audiobook converter, being rebuilt in phases. **Start by reading
`docs/05-status.md`** — it is the live handoff doc: current phase, acceptance
evidence, environment facts, and exactly what to build next. The full context
chain is `docs/01-audit.md` (why) → `02-product-vision.md` (what, incl. the two
narration contracts) → `03-architecture.md` (how) → `04-roadmap.md` (phases +
acceptance criteria) → `05-status.md` (now).

## Environment

- **Windows (primary dev box):** use `venv311` (Python 3.11, CUDA torch, kokoro).
  Never `.venv` (Python 3.13 — kokoro caps at 3.12). Run as
  `venv311\Scripts\vorpal.exe …` / `venv311\Scripts\python.exe -m pytest -q`.
  Tesseract at `C:\Program Files\Tesseract-OCR\`, ffmpeg at `C:\ffmpeg\bin\`
  (found by `vorpal/binaries.py`). Console is cp932 — set
  `$env:PYTHONIOENCODING='utf-8'` for ad-hoc scripts.
- **Linux / Docker:** `apt-get install -y tesseract-ocr ffmpeg`, then
  `python3.11 -m venv venv && pip install -r requirements.txt` (installs CPU
  torch + `-e .[dev]`). Python must be 3.10–3.12. `binaries.py` finds both
  tools on PATH; override with `VORPAL_TESSERACT`/`VORPAL_FFMPEG` if needed.
- First TTS run downloads the Kokoro model (~300 MB) from HuggingFace — needs
  network. On CPU, a full-book synth takes **hours** (GPU: ~25 min for the
  Firestone book); for synth-touching work, smoke-test on
  `scratch/outline.pdf`-sized books or `--end-page` slices, and treat the
  full-book run as the final acceptance step.
- `scratch/` and `*_workdir/` are gitignored — artifacts mentioned in the
  status doc are regenerated, not cloned. Regenerate the digital regression
  books with `python scratch/make_regression_books.py` (or copy the generator
  from `tests/test_regression_digital.py` if scratch is empty); regenerate the
  Firestone workdir with the build command in the status doc's re-entry
  checklist (~4 min of OCR).

## Commands

```
python -m pytest -q                  # full suite; must be green before commit
vorpal build <pdf> [--stop-after extract|segment] [--end-page N] [--output stem]
vorpal review <pdf> [--output stem] [--approve]
```

## Working conventions

- **One phase at a time**, in roadmap order; a phase is done only when its
  acceptance criteria in `docs/04-roadmap.md` pass on the regression set
  (Firestone scan + the two generated digital books).
- Acceptance items marked **(human)** in the roadmap (listening spot-checks,
  real-player chapter-marker checks) cannot be self-verified: do everything
  machine-checkable, then list the pending human checks explicitly in
  `docs/05-status.md` — never claim them done.
- **Prototype against real data before writing the module**: load
  `pages.jsonl` from a workdir in a `scratch/` script, look at actual block
  geometry, then implement. Phase 2's design survived contact with the data
  only because of this (two-page spreads, fused header lines were discovered
  that way, not designed for).
- Every behavior gets a unit test; every phase updates `docs/05-status.md`
  (state table, acceptance evidence, "what to build next", environment facts)
  and ends in **one commit** titled `Phase N: …` with evidence in the body.
- Hard product rules: body text is never silently dropped (fail loud or flag
  for review); no voice cloning, ever; LLM passes are optional edges, the
  deterministic pipeline must build books without them.
