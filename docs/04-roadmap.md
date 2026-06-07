# Implementation Roadmap

Phased plan to get from the current `pipeline.py` to the tool described in
[03-architecture.md](03-architecture.md). Each phase ends in a working state with
explicit acceptance criteria — no big-bang rewrite. The Firestone scan is the standing
regression book throughout; a born-digital PDF (with outline) and an outline-less digital
PDF join the regression set in Phase 2.

---

## Phase 0 — Foundation & triage *(small)*

Restructure without changing behavior, and delete what's already decided against.

- Create the `audiobooker/` package skeleton + `pyproject.toml` + `tests/`; move
  `pipeline.py`'s working logic into modules verbatim (extract/segment/normalize/synth/
  master boundaries), wire the existing CLI flags through `cli.py`.
- **Remove the F5-TTS / voice-clone path entirely** (`--voice-ref`, `--ref-text`,
  whisper dependency, dead `synthesise_chunks()` and the corrupted sanitizers —
  audit §3). Kokoro becomes the only engine, behind the `TTSEngine` interface.
- Binary discovery via `shutil.which` + fallbacks; pinned `requirements.txt` /
  `pyproject` deps; collapse to one venv; delete `setup.bat`'s venv-creation drift.
- Seed `tests/` with the first golden assets: a 10-page excerpt of the Firestone scan +
  its expected extraction output.

**Accept when:** `audiobook build firestone.pdf --end-page 20` reproduces today's
behavior (bugs and all) through the new package layout; `pytest` runs; no F5/whisper code
or deps remain.

## Phase 1 — Extraction v2 *(the quality foundation)*

- `ingest`: PDF hashing, outline/metadata read, per-page digital-vs-scanned detection;
  `book.json` manifest with hash-based staleness (replaces file-existence resume).
- Digital path: PyMuPDF block extraction with geometry + font data.
- Scanned path: OpenCV preprocess (deskew, binarize, despeckle, margin crop) →
  Tesseract TSV → blocks with confidence; per-page QA score + auto re-OCR retry ladder.
- Artifact: `pages.jsonl`; page provenance preserved end-to-end.

**Accept when:** on the Firestone scan, mean page confidence ≥ 0.90 and flagged pages
≤ 5%; a born-digital PDF skips rasterization entirely; unit tests cover species
detection and the QA score.

## Phase 2 — Segmentation v2 *(where the 58-chapter explosion dies)*

- Boilerplate removal by cross-page positional + fuzzy-text clustering; footnote
  separation; de-hyphenation; mojibake normalization; paragraph reflow.
- Chapter cascade: outline → printed-TOC parse (with page-offset inference) → layout
  heuristics; validation gates; front/back-matter classification.
- `audiobook review`: chapter table + manifest editing + selective downstream
  invalidation.

**Accept when (regression set):**
- Firestone: exactly the book's TOC chapters detected (11 incl. conclusion), zero
  running headers in any chapter body (lint), diagram pages excluded as figures,
  front matter classified — review step is approve-only or ≤ 2 edits.
- Born-digital book: chapters from outline, zero review edits.
- Outline-less digital book: chapters via TOC-parse or heuristics, ≤ 2 review edits.

## Phase 3 — Normalization & synthesis hardening *(where coherence is won)*

- `normalize.py`: spoken-form normalization, `pysbd` segmentation, chunk packing with
  pause metadata, **no-loss invariant** assertion, junk-lint gate.
- `synth`: retry → split → abort failure policy (no silent drops), chunk cache keyed by
  `(text_hash, engine, voice, speed)`, `spoken_intro` chapter announcements, synthesis
  report.

**Accept when:** normalization unit suite green (numbers, romans, abbreviations,
citations, dashes — table-driven tests); a full Firestone synth run reports
`failed: 0`; editing one chapter title re-synthesizes only that chapter's intro chunk;
listening spot-check of 3 random 2-minute segments finds no narrated junk.

## Phase 4 — Mastering & packaging *(sounds like a product)*

- Per-chapter loudness normalization to target LUFS; ffmpeg concat-demuxer assembly
  (constant memory); configurable inter-chapter silence.
- `.m4b` with chapters, metadata, embedded cover; `chapters_mp3/` side product;
  `report.md` QA summary.

**Accept when:** full-length Firestone build peaks < 1 GB RSS; chapters within ±1 LU;
markers land at chapter starts in a real player (VLC/BookPlayer); report lists every
gate's result.

## Phase 5 — End-to-end hardening & release *(v1)*

- Run the full regression set end-to-end; fix what surfaces.
- Duration-sanity and marker-count package gates; `--allow-gaps` escape hatch with
  audible markers.
- README rewrite: install (Tesseract/ffmpeg), quickstart, review workflow, manifest
  reference. Tag `v1.0`.

**Accept when:** fresh clone → `pip install -e .` → `audiobook build` succeeds on all
three regression books on Windows, meeting every product-level criterion in
[02-product-vision.md](02-product-vision.md).

---

## Post-v1 candidates (explicitly deferred)

In rough value order:

1. **ASR round-trip QA** — Whisper spot-check of sampled chunks, WER alerts.
2. **Performance** — parallel page OCR (process pool), batched TTS on GPU.
3. **More engines** — Piper (speed), API engines (quality) behind `TTSEngine`.
4. **EPUB input** — second `extract` backend; segmentation gets structure for free.
5. **LLM-assisted repair** — optional pass for OCR-damaged passages and smarter
   front-matter classification on weird books (kept optional: deterministic core,
   model-assisted edges).
6. Pronunciation lexicon (per-book overrides for names/terms).

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Printed-TOC parsing is fragile on odd layouts | It's one rung of a cascade with validation; failure falls through to heuristics + review, never to garbage |
| Page-offset inference (printed vs PDF page numbers) wrong | Validate every TOC anchor against a heading-like block on the target page; any mismatch drops to review |
| Kokoro chokes on residual odd input | Normalization layer + engine max-length contract + retry/split policy make the failure loud and local |
| Scope creep toward "document AI" | The gates define *done*; anything beyond the regression set's needs goes to post-v1 |
| Firestone scan quality caps OCR accuracy | Per-page flags surface the worst pages in review; that's the honest limit of a 1970 paperback scan |

## Sequencing note

Phases 1→4 are strictly ordered (each consumes the previous artifact). Within Phase 2,
boilerplate removal lands before chapter detection (headers are the main source of fake
chapters). Phase 3's normalization tests can be written in parallel with Phase 2 — they
are pure functions over strings.
