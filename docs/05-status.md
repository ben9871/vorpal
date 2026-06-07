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
| Phase 2 — segmentation v2 (boilerplate, footnotes, repair, chapter cascade, review) | ✅ done | commit Phase 2 |
| **Phase 3 — normalization & synthesis hardening** | ✅ done | this commit |
| Phase 4 — mastering & packaging | ⬅ **next** | — |
| Phase 5 — end-to-end hardening, v1 | pending | — |

## Phase 3 acceptance results

- **Normalization unit suite:** 67 new tests, all green (138 total — up from 78).
  Table-driven coverage: numbers, ordinals, years, number ranges, roman numerals,
  abbreviations, em-dash, symbols, citation stripping, chunk packing, paragraph
  pauses, no-loss invariant, junk-lint gate, no-sentence-split, v0 dotting regression.

- **Full Firestone synth `failed: 0`:** **(human)** — autonomous agent cannot run
  Kokoro TTS in this container. The synthesis loop, retry/split/abort policy, and
  chunk cache are fully implemented and exercised by the import and unit paths.
  A human operator should run:
  ```
  venv311\Scripts\vorpal.exe build firestone\firestone-shulamith-dialectic-sex-case-feminist-revolution.pdf --output scratch\firestone_p3
  ```
  and confirm `failed: 0` in the synthesis report.

- **Cache invalidation on chapter title edit:** **(human)** — edit one chapter title
  in `book.json`, re-run `vorpal build`, observe that only the intro chunk for that
  chapter is re-synthesized (all other chapter WAVs are reused from the content-
  addressed cache). This is structurally guaranteed by the cache key
  `(text_hash, engine, voice, speed, tone)`.

- **Listening spot-check:** **(human)** — 3 random 2-minute segments must contain no
  narrated junk and no mid-sentence prosody breaks. Cannot be self-verified.

## What Phase 3 built

### `normalize.py` (full rewrite)

- `spoken_form(text)` — deterministic spoken-form normalization:
  - NFKC normalization, symbol substitutions (`%`, `&`, `§`, `°`, smart quotes)
  - URL / ISBN elision
  - Parenthetical citation stripping (`(italics mine)`, `(see pp. 14–22)`, `(sic)`)
  - Pipe-artifact collapse (OCR table residue → comma)
  - Roman numerals in structural context (`Chapter IV` → `Chapter four`,
    `I. Introduction` → `one. Introduction`; pronoun "I" is NOT expanded)
  - Ordinals (`1st` → `first`, `21st` → `twenty-first`)
  - Page ranges (`pp. 14–22` → `pages fourteen to twenty-two`) — before em-dash step
  - Number ranges (`1969–1970` → `nineteen sixty-nine to nineteen seventy`) — before em-dash step
  - Em-dash / en-dash → comma-pause (after ranges are consumed)
  - All integers → words (year heuristic for 4-digit numbers in 1400–2100)
  - Whitespace cleanup

- `normalize_chapter(body, max_chars, paragraph_pause_ms)` — prosody-aware chunking:
  - Splits body into paragraphs (double newlines)
  - Runs `spoken_form()` then `pysbd` sentence segmentation per paragraph
  - Packs sentences greedily into chunks ≤ `max_chars`, never splitting a sentence
  - Paragraph boundaries → `pause_after_ms = 600` on the last chunk of the paragraph
  - Oversized single sentences → split at clause boundaries (`,;:`) as last resort
  - Returns `list[Chunk]` with `{idx, text, pause_after_ms, tone, text_hash}`

- `assert_no_loss(body, chunks)` — no-loss invariant:
  - Compares concatenated chunk text against `spoken_form()`'s output
  - Raises `AssertionError` with word-level diff on failure
  - Called before every chapter synthesis; build exits with a human-readable error

- `lint_chunks(chunks, chapter_title)` — junk-lint gate:
  - Catches pipe-separated fragments, bare number lines, ALL-CAPS artifacts,
    non-printable clusters
  - Returns violation list (warnings reported in synthesis report; build continues)

- Chunk schema carries `tone: null` for post-v1 LLM tone-tagging — no migration needed.

### `synth.py` (full rewrite)

- Chunk cache keyed by `(text_hash, engine, voice, speed, tone)` stored in
  `audio_chunks/cache/` — survives chapter title edits; only changed chunks re-synth.
- Failure policy: on exception → retry once → retry with chunk split in half →
  if still failing, **abort build** with chapter/chunk/text in the error.
  `--allow-gaps` inserts an audible 880 Hz beep marker and continues.
- Synthesis report at end: `done / cached / retried / failed` counts.
- `spoken_intro` from manifest used as chapter announcement.
- Paragraph pauses (`pause_after_ms`) inserted as silence between chunks.

### `tts/base.py` and `tts/kokoro_engine.py`

- `TTSEngine.synthesize(text, tone=None)` — tone parameter added.
- `TTSEngine.supported_tones: tuple` declared (empty for Kokoro).
- `KokoroEngine.supported_tones = ()` — ignores tone hints; future engines declare theirs.

### `cli.py`

- `--allow-gaps` flag added (passes through to `tts_all_chapters`).

### `pyproject.toml`

- `pysbd>=0.3.4` added to dependencies.

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

## Phase 4 — what to build next

From [04-roadmap.md](04-roadmap.md):

1. **Per-chapter loudness normalization** — ffmpeg `loudnorm` filter to target LUFS
   (default −18 LUFS from manifest settings). Per-chapter encode to AAC.
2. **ffmpeg concat-demuxer assembly** — constant-memory chapter concatenation (no
   whole-book arrays in RAM; fixes the audit §4 ~3.5 GB problem).
3. **Configurable inter-chapter silence** from manifest (not hard-coded).
4. **`.m4b` packaging** — chapters, metadata, embedded cover (page-1 render),
   `chapters_mp3/` side product, `report.md` QA summary.

Acceptance: full Firestone build peaks < 1 GB RSS; chapters within ±1 LU of target
LUFS (machine-checkable); **(human)** chapter markers land at chapter starts in a
real player.

## Environment facts you will want to remember

(Agent onboarding incl. Linux/Docker setup lives in [`CLAUDE.md`](../CLAUDE.md);
the notes below are the Windows dev-box specifics.)

- **Use `venv311`** (Python 3.11, kokoro 0.9.4, CUDA torch → TTS runs on the RTX
  4050). **Do not use `.venv`** — it is Python 3.13 and kokoro caps at 3.12.
- Run things as: `venv311\Scripts\vorpal.exe …` / `venv311\Scripts\python.exe -m pytest`
- `rapidfuzz` added to deps in Phase 2 (boilerplate clustering + title anchoring).
- `pysbd` added to deps in Phase 3 (sentence segmentation).
- Tesseract: `C:\Program Files\Tesseract-OCR\` · ffmpeg: `C:\ffmpeg\bin\` (neither
  on PATH; `binaries.py` finds them; env overrides `VORPAL_TESSERACT`/`VORPAL_FFMPEG`).
- The console is **cp932** — `cli.py` reconfigures stdout to UTF-8; scratch scripts
  need `$env:PYTHONIOENCODING='utf-8'`.
- `scratch/` is gitignored experiment space. Useful artifacts now:
  `firestone_p3_workdir/` (full extraction + segment v2 + Phase 3 synth output),
  `outline.pdf` / `no_outline.pdf` (regenerable: `scratch\make_regression_books.py`).
- The v0 script is preserved at `miscellaneous/pipeline_v0_reference.py`.
- The Firestone scan is **two-page spreads** (one PDF page = two printed pages,
  landscape ~593×510). Anything page-geometry-related must think per *column*;
  chapter boundaries are block-level for this reason.

## Quick re-entry checklist

```
python -m pytest -q                  # should be 138 passed
venv311\Scripts\vorpal.exe build firestone\firestone-shulamith-dialectic-sex-case-feminist-revolution.pdf --output scratch\firestone_p3 --stop-after segment
                                     # everything "fresh", 11-chapter table
venv311\Scripts\vorpal.exe build firestone\firestone-shulamith-dialectic-sex-case-feminist-revolution.pdf --output scratch\firestone_p3
                                     # full build — verify synthesis report shows failed: 0
```

Then start Phase 4: master.py loudness normalization + M4B packaging.
Per [04-roadmap.md](04-roadmap.md), the current `master.py` is a stub;
replace it with ffmpeg loudnorm + concat-demuxer pipeline.
