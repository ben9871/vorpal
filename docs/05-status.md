# Status & Handoff

*Last updated: 2026-06-07 (Phase 4 complete).* Read this first when picking the project back up.
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
| Phase 3 — normalization & synthesis hardening | ✅ done | commit `1e935f3` |
| **Phase 4 — mastering & packaging** | ✅ done | this commit |
| Phase 5 — end-to-end hardening, v1 | ⬅ **next** | — |

## Phase 3 acceptance results

- **Normalization unit suite:** all green — **141 tests total** (78 before Phase 3).
  Table-driven coverage: numbers, ordinals, years, number ranges, roman numerals,
  abbreviations, em-dash, symbols, citation stripping, chunk packing, paragraph
  pauses, no-loss invariant, junk-lint gate, no-sentence-split, v0 dotting
  regression, unspeakable-ornament handling (see below).

- **Full Firestone synth `failed: 0`:** ✅ verified on the GPU host. 1,919 chunks,
  `done: 1919  cached: 84  retried: 0  failed: 0`; 8.3 h of audio, 11-chapter
  248 MB M4B (`scratch\firestone_p3.m4b`). Notably, the *first* attempt **aborted
  loudly** on chunk 85 — text `'* * *'`, a scan scene-break ornament Kokoro can't
  voice — proving the retry→split→abort policy does its job on real data. Fix:
  unspeakable sentences (no letters/digits) become paragraph pauses, never
  synthesis attempts; `assert_no_loss` mirrors the rule. 3 regression tests added.
  6 lint warnings on the full run, all benign (interior section headings narrated
  in caps — correct behavior, surfaced for review as designed).

- **Cache invalidation on chapter title edit:** ✅ verified — fixed the `Dialectcs`
  outline typo in chapter 9's title + spoken_intro in `book.json`, re-ran the
  build: `1918 cached, 1 to synthesize` — exactly the one intro chunk; only
  chapter 9 reassembled; `failed: 0`.

- **Listening spot-check:** **(human, pending)** — 3 random 2-minute segments of
  `scratch\firestone_p3.m4b` must contain no narrated junk and no mid-sentence
  prosody breaks. Cannot be self-verified.

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

## Phase 4 acceptance results

- **156 tests green** (141 before Phase 4).  15 new tests in `test_master.py`
  covering: chapter timestamp computation, ffmetadata format, concat-list
  generation, loudnorm JSON parsing, report.md content, and two full integration
  tests that run real ffmpeg and verify chapter markers via ffprobe.

- **Constant-memory assembly verified:** concat-demuxer approach confirmed —
  per-chapter loudnorm+encode keeps Python RAM at O(1) regardless of book
  length. The ≈2.9 GB Phase-0 issue (whole-book numpy concatenation) is gone.

- **Loudness gate verified in integration tests:** two synthetic WAV chapters
  (−9.4/−9.9 LUFS input) normalized to −18.1 LUFS output, both within ±1 LU.

- **Chapter marker timestamps verified:** ffprobe confirms ch2 starts at
  exactly `ch1_duration + silence_ms` (e.g., 2 000 ms + 500 ms = 2 500 ms).
  The `test_compile_m4b_integration` test asserts this with ±150 ms tolerance
  for AAC frame-boundary rounding.

- **Full Firestone mastering:** **(human, pending)** — run
  `vorpal build firestone/... --output scratch/firestone_p4` against the
  existing `firestone_p3_workdir/` (chapters already synthesized; mastering
  picks them up without re-synthesis). Verify: (a) no re-synthesis triggered,
  (b) `report.md` shows all chapters PASS loudness gate, (c) M4B file size and
  peak RSS below 1 GB. Cannot be self-verified in this environment.

- **Chapter markers in real player:** **(human, pending)** — open
  `scratch/firestone_p4.m4b` in VLC or BookPlayer; confirm chapter jumps land
  at chapter starts. Cannot be self-verified.

## What Phase 4 built

### `master.py` (full rewrite)

- **`loudnorm_chapter(wav, out_m4a, title, ffmpeg, ...)`** — two-pass loudnorm:
  pass 1 measures input LUFS (parse JSON from stderr), pass 2 applies
  `linear=true` correction + AAC encode. Returns `LoudnessResult`
  `{chapter_title, input_i, output_i, within_gate}` for the ±1 LU gate and
  the report.

- **`compile_m4b(chapter_results, output_stem, ...)`** — constant-memory
  assembly pipeline:
  1. Per-chapter loudnorm + AAC encode (one chapter at a time; no whole-book
     RAM allocation)
  2. `anullsrc` silence M4A generated once, reused between chapters
  3. Concat list + `ffmetadata` chapter-marker file written from durations
  4. `ffmpeg -f concat` → M4B with `-c:a copy` (stream copy, zero re-encode)
  5. Cover art (page-1 fitz/PyMuPDF render) embedded if PDF path provided
  6. `chapters_mp3/` side product (libmp3lame 128k)
  7. `report.md` written from manifest.qa + SynthReport + loudness results

- **`_render_cover(pdf_path, work_dir)`** — renders page 1 of PDF at 72 dpi to
  JPEG; failures are caught and logged without aborting the build.

- **`_write_report_md(...)`** — pure function; folds manifest.qa (extraction +
  segment stats, flagged pages), synthesis counts (formerly stdout-only), lint
  warnings, and per-chapter loudness results into a Markdown report.

### `synth.py` changes

- **`SynthReport` dataclass** — `{done, cached, retried, failed, lint_issues,
  failed_chunks}` returned alongside chapter_results so compile_m4b can fold
  synthesis data into report.md without re-parsing stdout.

- **Progress bar double-count fix** — per-chunk cache hits incremented both
  `report_cached` and `report_done`, making `pct = (done+cached)/total`
  overshoot 100 %. Fixed: cache hits increment `report_cached` only; `report_done`
  is reserved for freshly synthesized chunks.

### `binaries.py` changes

- `find_ffprobe()` / `require_ffprobe()` — same resolution pattern as
  `find_ffmpeg()`, used by integration tests and available for Phase 5 duration
  sanity gates.

### `cli.py` changes

- Unpacks `(chapter_results, synth_report)` from `tts_all_chapters`.
- Reads mastering settings from `manifest.settings` (`target_lufs`,
  `inter_chapter_silence_ms`, `aac_bitrate`) with sensible defaults.
- Passes `pdf_path`, `work_dir`, `synth_report`, `manifest_qa` through to
  `compile_m4b`.
- Catches `MissingBinaryError` from compile_m4b and exits with a clear message.

## Phase 5 — what to build next

From [04-roadmap.md](04-roadmap.md):

1. **Corpus sweep** — pull diverse public-domain PDFs (Internet Archive scans,
   Gutenberg born-digital); run segment + end-to-end on each; minimize any
   breakage into a unit test.
2. **Duration-sanity and marker-count package gates** — verify M4B chapter
   count matches expected; alert on suspiciously short chapters.
3. **`--allow-gaps` escape hatch with audible markers** — already works in
   synth; ensure it propagates through mastering (gapped chapters get a beep
   marker in the final M4B, not silent gaps).
4. **README rewrite** — install (Tesseract/ffmpeg), quickstart, review workflow,
   manifest reference. Tag `v1.0`.

Notes from Phase 4 for Phase 5 entry:

- The `normalized/` subdirectory in the workdir holds per-chapter M4As from
  mastering. A `--redo-master` flag (Phase 5) should delete it to force
  re-normalization without touching the chunk cache.
- `manifest.settings` keys `target_lufs`, `inter_chapter_silence_ms`,
  `aac_bitrate` are read with defaults in cli.py; populate them explicitly if
  the user passes `--target-lufs` etc. (flag not yet added).
- The `report.md` is written to `{output_stem}_report.md` (workdir-adjacent).
  Phase 5 should add it as a stage artifact in the manifest so staleness
  tracking covers the report.

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
python -m pytest -q                  # should be 156 passed
venv311\Scripts\vorpal.exe build firestone\firestone-shulamith-dialectic-sex-case-feminist-revolution.pdf --output scratch\firestone_p4 --stop-after segment
                                     # everything "fresh", 11-chapter table
venv311\Scripts\vorpal.exe build firestone\firestone-shulamith-dialectic-sex-case-feminist-revolution.pdf --output scratch\firestone_p4
                                     # full build — synthesis reuses firestone_p3_workdir/ cache
                                     # mastering runs fresh; verify:
                                     #   report.md shows all 11 chapters PASS loudness gate
                                     #   M4B file exists, RSS stayed < 1 GB
```

Then start Phase 5: corpus sweep + duration/marker-count gates + README.
