# Status & Handoff

*Last updated: 2026-06-07.* Read this first when picking the project back up.
The full plan lives in [04-roadmap.md](04-roadmap.md); this file is where we are on it.

> **Renamed:** the package/CLI is now **`vorpal`** (we're combatting jabberwocky).
> `audiobook` remains a legacy alias console script. Env overrides are now
> `VORPAL_TESSERACT`/`VORPAL_FFMPEG`. Product goals grew two narration-side
> contracts — prosody-coherent TTS chunking (Phase 3) and per-paragraph `tone`
> tags via an optional LLM pass (post-v1, schema carried from Phase 3) — see the
> updated [02-product-vision.md](02-product-vision.md) §"second contract".

## Where we are

| Phase | State | Evidence |
|---|---|---|
| Phase 0 — package restructure, drop voice cloning | ✅ done | commit `d31ee89` |
| Phase 1 — extraction v2 (manifest, page classification, block OCR + QA) | ✅ done | commit `b103f23` |
| Phase 2 — segmentation v2 (boilerplate, footnotes, repair, chapter cascade, review) | ✅ done | this commit |
| **Phase 3 — normalization & synthesis hardening** | ⬅ **next** | — |
| Phase 4 — mastering & packaging | pending | — |
| Phase 5 — end-to-end hardening, v1 | pending | — |

Working state: `vorpal build book.pdf` runs end-to-end (ingest → extract v2 →
**segment v2** → review gate → Kokoro TTS → M4B). `vorpal review` prints the
chapter table and `--approve` unlocks a paused build. Synthesis is still the
Phase-0 warn-and-skip loop — that is exactly what Phase 3 replaces.

## Phase 2 acceptance results (for reference)

Regression set, all via `vorpal build … --stop-after segment`:

- **Firestone scan** → cascade rung **outline**, exactly **11 narrated chapters**
  (10 + conclusion), `Contents`/front matter/back matter classified & excluded,
  **zero residual running headers** (was 21 in v0; 227 header lines + 23 page-number
  lines removed by clustering), 30 `*`-footnotes to the side channel, the flagged
  dialectic-chart page (idx 127) excluded as a figure. Review edits needed: **2**
  (typos inherited from the PDF's own outline: "Dialectcs", ch. 5 subtitle) — within
  the ≤ 2 budget. Auto-approved (trusted source, no flags).
- **Born-digital with outline** (generated, `tests/test_regression_digital.py`) →
  rung outline, conf 0.95, zero edits.
- **Outline-less digital with printed TOC** → rung **toc** (global anchor search —
  no constant page offset assumed, which spread scans would break), zero edits.

78 tests green (38 before Phase 2). Hash-based resume verified across all stages.

## How segment v2 hangs together

- `segment/boilerplate.py` — cross-page top/bottom-band clustering (rapidfuzz),
  line-level removal (headers are often OCR-fused as a body block's first line).
- `segment/footnotes.py` — `*`/`†` markers always; numeric markers **digital-only**
  (small-font signal) because scans can't tell `1)` footnotes from numbered body
  lists; ALL-CAPS and near-letterless blocks rejected (TOC lines, `* * *`).
- `segment/repair.py` — wordlike-checked de-hyphenation, NFKC + quote classes
  (mojibake *counted*, never guessed), block reflow + `join_blocks()` cross-page
  paragraph stitching.
- `segment/chapters.py` — outline → printed-TOC → font-outlier heuristics cascade
  with validation gates; every section carries `source`/`confidence`/`flags`.
  Heuristics on scans intentionally produce nothing (that guessing is what
  exploded v0); a structureless book becomes one reviewable section.
- `segment/frontmatter.py` — title-based front/back-matter classification,
  figure-page detection (`flagged && score < 0.5`), back-matter capping.
- Boundaries are **(page, block) refs into `pages_segmented.jsonl`** — bodies
  regenerate from manifest + that artifact every build, so hand-edits to
  `book.json` chapters take effect without re-segmenting.
- Review gate: build auto-approves only when every narrated section is from
  outline/TOC with no flags; otherwise it prints the table and exits until
  `vorpal review … --approve`.

## Phase 3 — what to build next

From [04-roadmap.md](04-roadmap.md) and [03-architecture.md](03-architecture.md) stages 5–6:

1. `normalize.py` rewrite — spoken-form normalization (numbers, romans,
   abbreviations, citations, dashes), `pysbd` sentence segmentation (add dep),
   **prosody-aware chunk packing** (sentence-safe, paragraph-aligned, packed
   toward the engine's context size, pause metadata), **no-loss invariant**,
   junk-lint gate (catches the `For that rare diagram freak | 3-D REVOLUTION`
   tail residue on Firestone p126 and OCR junk like `cven`/`¢.g.`).
2. Chunk schema carries a `tone` field (default null) from day one — the post-v1
   LLM tone-tagging pass fills it, expressive engines act on it, no migration later.
3. `synth.py` rewrite — retry → split → abort policy (replace warn-and-skip),
   chunk cache keyed `(text_hash, engine, voice, speed, tone)` (today chunk reuse
   is index-based — **stale after any review edit**, the known gap), synthesis
   report. `TTSEngine.synthesize(text, tone=None)`; Kokoro ignores the hint.
   `spoken_intro` is already in the manifest and honored by synth.
4. Normalization unit suite is table-driven and can be written first (pure functions).

**Acceptance:** normalization suite green; full Firestone synth `failed: 0`;
editing one chapter title re-synthesizes only that chapter's intro chunk;
3 random 2-minute listening spot-checks find no narrated junk.

## Environment facts you will want to remember

(Agent onboarding incl. Linux/Docker setup lives in [`CLAUDE.md`](../CLAUDE.md);
the notes below are the Windows dev-box specifics.)

- **Use `venv311`** (Python 3.11, kokoro 0.9.4, CUDA torch → TTS runs on the RTX
  4050). **Do not use `.venv`** — it is Python 3.13 and kokoro caps at 3.12.
- Run things as: `venv311\Scripts\vorpal.exe …` / `venv311\Scripts\python.exe -m pytest`
- `rapidfuzz` added to deps in Phase 2 (boilerplate clustering + title anchoring).
- Tesseract: `C:\Program Files\Tesseract-OCR\` · ffmpeg: `C:\ffmpeg\bin\` (neither
  on PATH; `binaries.py` finds them; env overrides `VORPAL_TESSERACT`/`VORPAL_FFMPEG`).
- The console is **cp932** — `cli.py` reconfigures stdout to UTF-8; scratch scripts
  need `$env:PYTHONIOENCODING='utf-8'`.
- `scratch/` is gitignored experiment space. Useful artifacts now:
  `firestone_p2_workdir/` (full extraction + segment v2 output incl.
  `pages_segmented.jsonl`, `chapter_texts/`, `footnotes.json`),
  `outline.pdf` / `no_outline.pdf` (regenerable: `scratch\make_regression_books.py`).
- The v0 script is preserved at `miscellaneous/pipeline_v0_reference.py`.
- The Firestone scan is **two-page spreads** (one PDF page = two printed pages,
  landscape ~593×510). Anything page-geometry-related must think per *column*;
  chapter boundaries are block-level for this reason.

## Quick re-entry checklist

```
venv311\Scripts\python.exe -m pytest -q          # should be 78 passed
venv311\Scripts\vorpal.exe build firestone\firestone-shulamith-dialectic-sex-case-feminist-revolution.pdf --output scratch\firestone_p2 --stop-after segment
                                                  # everything "fresh", 11-chapter table
```

Then start Phase 3 with the table-driven normalization tests (pure functions,
no GPU needed).
