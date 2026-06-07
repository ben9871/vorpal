# Status & Handoff

*Last updated: 2026-06-07 (Phase 5 complete).* Read this first when picking the project back up.
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
| Phase 4 — mastering & packaging | ✅ done | commit Phase 4 |
| **Phase 5 — multi-format input & end-to-end hardening** | ✅ done | this commit |
| Arc 2: Phase 6 — voice suite v1 (registry, blends, audition) | queued | roadmap |
| Arc 2: Phase 7 — first tone-capable engine (API, cost-guarded) | queued | roadmap |
| Arc 2: Phase 8 — tone tagging + effectiveness gates (`--expressive`) | queued | roadmap |
| Arc 2: Phase 9 — in-house voices (spike-gated) | queued | roadmap |

## Phase 5 acceptance results

- **205 tests green** (156 before Phase 5). 49 new tests across:
  `test_epub.py` (29 tests — EPUB extraction, HTML-to-text, TOC mapping, title
  classification, roundtrip), `test_txt.py` (14 tests — heading detection,
  Gutenberg stripping, section splitting, TXT extraction), `test_master_phase5.py`
  (9 tests — mastering cache hit/miss/roundtrip, SHA determinism),
  `test_segment.py` +2 (Section body field roundtrip, empty body not stored).

- **EPUB builds end-to-end with zero review edits:** ✅ verified on
  `flatland_pg201.epub` (auto-approved, 3 chapters from spine) and
  `sherlock_holmes_pg1661.epub` (auto-approved, 13 chapters, clean titles).

- **TXT builds with ≤ 2 review edits:** ✅ verified on
  `pride_and_prejudice_pg1342.txt` — 61 chapters detected, all substantial,
  only 1 edit needed (stray `]` in chapter 1 title). Pauses at review
  (heuristic source, expected); actionable review table.

- **Corpus sweep (9 books across 3 formats):** every book either builds clean
  (auto-approve) or pauses at review with an honest, actionable table —
  never garbage output, never a crash. See `docs/06-corpus.md` for per-book
  results.

- **Mastering staleness cache:** ✅ — per-chapter M4A keyed by
  `(sha256(wav), target_lufs, aac_bitrate)` stored as `.cache.json` sidecar.
  A re-run after synth-only change re-masters only changed chapters.
  Unit tests cover hit, miss (sha change, LUFS change, bitrate change),
  roundtrip, and corrupt-sidecar resilience.

- **Duration-sanity and marker-count gate:** ✅ — `_check_m4b_chapters()` uses
  ffprobe to verify chapter count in the assembled M4B matches expected; alerts
  on chapters shorter than 60 s. Gate result printed to stdout and written to
  `report.md`.

- **README rewrite:** ✅ — full rewrite covering multi-format input, install,
  quickstart, build workflow, stage summary, manifest reference, flags,
  command reference, project layout.

- **`--allow-gaps` propagation:** ✅ — beep markers are baked into chapter
  WAVs during synthesis; they propagate through loudnorm + M4B assembly
  unchanged. No extra code needed in mastering.

### (human) acceptance items

- **(human)** Full-book EPUB/TXT end-to-end build with TTS + mastering (container
  GPU build) has not been run — the pipeline is verified through
  `--stop-after segment` and by inspecting extracted bodies.
- **(blocked)** Full regression set end-to-end: the Phase 4 Firestone M4B
  acceptance remains the standing proof; no new full-book M4B run was done in
  this phase (TTS/mastering unchanged, only new input-format path added).

## What Phase 5 built

### `extract/epub.py` (new)

- `extract_epub(epub_path)` — parses EPUB via stdlib (`zipfile` + `xml.etree`):
  - `META-INF/container.xml` → OPF path
  - OPF manifest + spine (ordered list of content items)
  - EPUB3 NAV or EPUB2 NCX → `{spine_index: title}` map
  - Per-item HTML → clean text via `_TextExtractor` (skips nav/script/style)
  - Merges untitled spine items into the preceding titled section
  - Returns section dicts with `source="spine"`, `confidence=1.0`, body inline
- Title classification: chapter / frontmatter / backmatter + Project Gutenberg
  license detection
- `qa` dict: `spine_items`, `toc_entries`, `sections_produced`
- No dependency on segment (avoids import cycle); avoids ebooklib (AGPL)

### `extract/text.py` (new)

- `extract_txt(txt_path)` — plain-text chapter heuristics:
  - Strips Project Gutenberg header/footer boilerplate
  - Extracts title/author from Gutenberg metadata block
  - `_is_heading_line()`: matches `CHAPTER N`, `PART N`, `BOOK N`, roman numeral `I.`
    patterns; rejects dot-leader TOC entries (`. . .` / `...` filter)
  - Splits text on heading positions surrounded by blank lines
  - Falls back to single section (`source="manual"`) when no headings found
  - Returns section dicts with `source="heuristic"`, `confidence=0.7`, body inline

### `ingest.py` (updated)

- `detect_format(path)` — `.pdf`/`.epub`/`.txt` → `"pdf"`/`"epub"`/`"txt"`
- `ingest()` dispatches on format: PDF → `_ingest_pdf()` (existing behavior);
  EPUB/TXT → lightweight manifest population (hash + format, no page analysis)
- `manifest.source["format"]` records the input format for downstream dispatch
- Ingest version bumped to `"ingest-v2"` (includes format in input hash)

### `cli.py` (updated)

- `build` and `review` subcommands: argument `pdf` → `input` (accepts all formats)
- `cmd_build()` dispatches: PDF → `_build_pdf_stages()` (extract + segment);
  EPUB/TXT → `_build_format_parse()` (single "parse" stage, hash-cached)
- `needs_review()`: `"spine"` added to trusted sources (EPUB auto-approves
  when no flags; TXT heuristic always pauses for review)
- `_build_format_parse()`: calls `extract_epub()` or `extract_txt()`, populates
  manifest sections, stores bodies inline, stage-caches with `"parse-v1"` hash

### `segment/chapters.py` (updated)

- `Section.body: str = ""` — EPUB/TXT bodies stored inline; PDF sections leave
  it empty (bodies reconstructed from page-block refs)
- `Section.to_dict()`: only emits `"body"` key when non-empty (avoids bloating
  PDF manifests)
- `Section.from_dict()`: reads `body` field with default `""`
- `section_body(section, pages)`: checks `section.body` first; falls through
  to page-block lookup for PDFs

### `master.py` (updated)

- **Mastering cache**: `_wav_sha256()`, `_master_cache_hit()`,
  `_master_cache_write()` — per-chapter `.cache.json` sidecar keyed by
  `(wav_sha256, target_lufs, aac_bitrate)`. `compile_m4b()` skips loudnorm+encode
  when the cache hits; writes/updates the sidecar on fresh encodes.

- **Chapter gate**: `_check_m4b_chapters(m4b_path, expected_count)` — runs
  ffprobe on the finished M4B; verifies chapter count matches expected; flags
  chapters shorter than `SHORT_CHAPTER_THRESHOLD_S = 60` s. Result printed to
  stdout and included in `report.md`.

- `_write_report_md()`: gains `chapter_gate` parameter; `## Chapter Gate`
  section in the report.

## Phase 5 corpus sweep summary

From `docs/06-corpus.md`:
- **archive.org PDF scans** (2 books): *Call of the Wild* (toc path, 6 ch, ✅),
  *Meditations of Marcus Aurelius* (heuristic, needs review, ✅ no crash)
- **Gutenberg EPUBs** (4 books): *Flatland* (auto-approved, 3 ch, ✅),
  *Sherlock Holmes* (auto-approved, 13 ch, ✅), *P&P* (review-paused, 15 ch
  — TOC label quirk in this Gutenberg EPUB, ✅ no crash), *Treasure Island*
  (review-paused, structural EPUB quirk, ✅ no crash)
- **Gutenberg TXTs** (2 books): *P&P* (61 ch, ≤ 2 edits, ✅), *Treasure Island*
  (13 sections including PART headers, review-paused, ✅ no crash)

Generalization verdict: every book either builds cleanly or pauses with an
honest, actionable table. No crashes, no garbage output.

## What Phase 4 built (summary — see previous status doc for full details)

- Per-chapter loudness normalization (two-pass loudnorm), ffmpeg concat-demuxer
  M4B assembly, chapter markers, cover art, MP3 side product, `report.md`.
- Constant-memory (65.9 MB peak RSS on Firestone). Full Firestone mastering:
  11/11 chapters PASS ±1 LU gate.

## What Phase 3 built (summary)

- `normalize.py`: `spoken_form()`, prosody-aware `normalize_chapter()`,
  `assert_no_loss()`, `lint_chunks()`. Chunk schema carries `tone: null`.
- `synth.py`: retry→split→abort policy, chunk cache, `SynthReport`.
- Full Firestone synth: `done: 1919, failed: 0`.

## What to build next (Phase 6)

From [04-roadmap.md](04-roadmap.md) Arc 2:

1. **`tts/voices.py`** — voice registry with curated entries `{id, display_name,
   engine, params, description}`; v1: Kokoro single voices + curated blends
   (Kokoro embeddings are tensors → weighted mix = new voice for free)
2. **`vorpal voices`** subcommand — list the suite; `--sample [--text "…"]`
   renders short audition WAVs into `voices_preview/`
3. **`--voice <id>`** resolves through the registry; manifest stores id + resolved
   params; chunk-cache key uses resolved params (blend recipe change invalidates)
4. README gains a "Voices" section with the suite table

Accept when: ≥ 6 curated voices including ≥ 2 blends; full build runs with a
blend voice; changing blend weights re-synthesizes; **(human)** audition pass
picks favorites.

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
- `scratch/` is gitignored experiment space.
- The v0 script is preserved at `miscellaneous/pipeline_v0_reference.py`.
- The Firestone scan is **two-page spreads** (one PDF page = two printed pages,
  landscape ~593×510). Anything page-geometry-related must think per *column*.

## Quick re-entry checklist

```
python -m pytest -q                  # should be 205 passed
vorpal build firestone\firestone-shulamith-dialectic-sex-case-feminist-revolution.pdf \
    --output scratch\firestone_p5 --stop-after segment
                                     # everything fresh, 11-chapter table
vorpal build corpus\flatland_pg201.epub --output scratch\flatland_test --stop-after segment
                                     # EPUB path: 3 chapters, auto-approved
vorpal build corpus\pride_and_prejudice_pg1342.txt --output scratch\pp_txt_test --stop-after segment
                                     # TXT path: 61 chapters, review pause (expected)
```

Then start Phase 6: voice registry, blends, `vorpal voices` audition command.
