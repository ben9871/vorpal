# Status & Handoff

*Last updated: 2026-06-07.* Read this first when picking the project back up.
The full plan lives in [04-roadmap.md](04-roadmap.md); this file is where we are on it.

## Where we are

| Phase | State | Evidence |
|---|---|---|
| Phase 0 — package restructure, drop voice cloning | ✅ done | commit `d31ee89` |
| Phase 1 — extraction v2 (manifest, page classification, block OCR + QA) | ✅ done | commit `b103f23` |
| **Phase 2 — segmentation v2** | ⬅ **next** | — |
| Phase 3 — normalization & synthesis hardening | pending | — |
| Phase 4 — mastering & packaging | pending | — |
| Phase 5 — end-to-end hardening, v1 | pending | — |

Working state: `audiobook build book.pdf` runs end-to-end (ingest → extract v2 →
**v0 segmentation** → Kokoro TTS → M4B). Extraction is good; chapter detection is
still the known-bad v0 regex logic — that is exactly what Phase 2 replaces.

## Phase 1 acceptance results (for reference)

- Firestone scan: mean OCR confidence **0.932** (target ≥ 0.90), **1/130 pages
  flagged (0.8%)** — the flagged page is the dialectic chart diagram, correctly caught.
- Born-digital PDFs skip OCR entirely (verified by CLI run + unit test).
- 38 tests green; hash-based resume verified (second build reuses every stage).

## Phase 2 — what to build next

From [04-roadmap.md](04-roadmap.md) and [03-architecture.md](03-architecture.md) stage 3:

1. `segment/boilerplate.py` — running header/footer/page-number removal by
   cross-page positional + fuzzy-text clustering over `pages.jsonl` blocks
   (kills the 21 surviving `THE DIALECTIC OF SE'` headers and their fake chapters).
2. `segment/footnotes.py` — bottom-of-page footnote blocks → side channel;
   superscript markers stripped from body.
3. Text repair — de-hyphenation, mojibake normalization, paragraph reflow from
   block geometry.
4. `segment/chapters.py` rewrite — cascade: **PDF outline → printed-TOC parse →
   layout heuristics**, with validation. Key asset: **the Firestone PDF has a
   12-entry embedded outline** (see `manifest.source.outline` after ingest) —
   rung 1 of the cascade should nail it.
5. `segment/frontmatter.py` — front/back-matter classification (visible, not
   silently dropped).
6. `audiobook review` subcommand — chapter table + manifest editing + selective
   re-synthesis.

**Acceptance:** Firestone yields exactly the book's TOC chapters (11 incl.
conclusion), zero running headers in chapter bodies, diagram pages excluded,
≤ 2 review edits. Plus a born-digital book (outline) and an outline-less digital
book (TOC-parse/heuristics) — see roadmap Phase 2.

## Environment facts you will want to remember

- **Use `venv311`** (Python 3.11, kokoro 0.9.4, CUDA torch → TTS runs on the RTX
  4050). **Do not use `.venv`** — it is Python 3.13 and kokoro caps at 3.12; it can
  be deleted once PyCharm's interpreter is switched to `venv311`.
- Run things as: `venv311\Scripts\audiobook.exe …` / `venv311\Scripts\python.exe -m pytest`
- Tesseract: `C:\Program Files\Tesseract-OCR\` · ffmpeg: `C:\ffmpeg\bin\` (neither
  on PATH; `binaries.py` finds them; env overrides `AUDIOBOOKER_TESSERACT`/`AUDIOBOOKER_FFMPEG`).
- The console is **cp932** — `cli.py` reconfigures stdout to UTF-8; keep that in mind
  for any new entry points.
- `scratch/` is gitignored experiment space. Useful artifacts there now:
  `firestone_p1_workdir/pages.jsonl` (full 130-page extraction v2 output —
  Phase 2's input for prototyping) and `digital_test.pdf` (born-digital test book).
- The v0 script is preserved at `miscellaneous/pipeline_v0_reference.py`.

## Quick re-entry checklist

```
venv311\Scripts\python.exe -m pytest -q          # should be 38 passed
git log --oneline                                 # d31ee89 Phase 0, b103f23 Phase 1
```

Then start Phase 2 with `segment/boilerplate.py`, prototyping against
`scratch/firestone_p1_workdir/pages.jsonl`.
