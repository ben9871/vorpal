# Implementation Roadmap

Phased plan to get from the current `pipeline.py` to the tool described in
[03-architecture.md](03-architecture.md). Each phase ends in a working state with
explicit acceptance criteria — no big-bang rewrite. The Firestone scan is the standing
regression book throughout; a born-digital PDF (with outline) and an outline-less digital
PDF join the regression set in Phase 2.

---

## Phase 0 — Foundation & triage *(small)*

Restructure without changing behavior, and delete what's already decided against.

- Create the `vorpal/` package skeleton + `pyproject.toml` + `tests/`; move
  `pipeline.py`'s working logic into modules verbatim (extract/segment/normalize/synth/
  master boundaries), wire the existing CLI flags through `cli.py`.
- **Remove the F5-TTS / voice-clone path entirely** (`--voice-ref`, `--ref-text`,
  whisper dependency, dead `synthesise_chunks()` and the corrupted sanitizers —
  audit §3). Kokoro becomes the only engine, behind the `TTSEngine` interface.
- Binary discovery via `shutil.which` + fallbacks; pinned `requirements.txt` /
  `pyproject` deps; collapse to one venv; delete `setup.bat`'s venv-creation drift.
- Seed `tests/` with the first golden assets: a 10-page excerpt of the Firestone scan +
  its expected extraction output.

**Accept when:** `vorpal build firestone.pdf --end-page 20` reproduces today's
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
- `vorpal review`: chapter table + manifest editing + selective downstream
  invalidation.

**Accept when (regression set):**
- Firestone: exactly the book's TOC chapters detected (11 incl. conclusion), zero
  running headers in any chapter body (lint), diagram pages excluded as figures,
  front matter classified — review step is approve-only or ≤ 2 edits.
- Born-digital book: chapters from outline, zero review edits.
- Outline-less digital book: chapters via TOC-parse or heuristics, ≤ 2 review edits.

## Phase 3 — Normalization & synthesis hardening *(where coherence is won)*

- `normalize.py`: spoken-form normalization, `pysbd` segmentation, **prosody-aware
  chunk packing** (sentence-safe, paragraph-aligned, packed toward the engine's
  context size, pause metadata — coherent narration is a chunking property before it
  is an engine property), **no-loss invariant** assertion, junk-lint gate.
- Chunk schema carries the `tone` field (default `null`/neutral) end-to-end from this
  phase, so the post-v1 expressive layer needs no schema migration. Phase 3 does
  **not** fill it — `tone.py` (LLM tagging) is post-v1.
- `synth`: retry → split → abort failure policy (no silent drops), chunk cache keyed by
  `(text_hash, engine, voice, speed, tone)`, `spoken_intro` chapter announcements,
  synthesis report. `TTSEngine.synthesize(text, tone=None)` — Kokoro ignores the hint.

**Accept when:** normalization unit suite green (numbers, romans, abbreviations,
citations, dashes — table-driven tests); a full Firestone synth run reports
`failed: 0`; editing one chapter title re-synthesizes only that chapter's intro chunk;
**(human)** listening spot-check of 3 random 2-minute segments finds no narrated junk
and no mid-sentence prosody breaks. *(An autonomous agent completes everything else,
then lists the pending listening check in the status doc.)*

## Phase 4 — Mastering & packaging *(sounds like a product)*

- Per-chapter loudness normalization to target LUFS; ffmpeg concat-demuxer assembly
  (constant memory); configurable inter-chapter silence.
- `.m4b` with chapters, metadata, embedded cover; `chapters_mp3/` side product;
  `report.md` QA summary.

**Accept when:** full-length Firestone build peaks < 1 GB RSS; chapters within ±1 LU
(machine-checkable via ffmpeg loudnorm stats); **(human)** markers land at chapter
starts in a real player (VLC/BookPlayer) — an agent can verify marker *timestamps*
against chapter audio durations in the muxed file as the automated proxy; report
lists every gate's result.

## Phase 5 — End-to-end hardening *(the "any PDF" milestone — no release)*

*(Re-scoped 2026-06-07: no v1.0 tag, no PyPI — the project stays 0.x personal
tooling for now. "v1" below means the quality bar, not a release event. The
energy after this phase goes to expressiveness — see
[07-ideation.md](07-ideation.md).)*

- **Corpus sweep:** pull a diverse set of lawful real-world PDFs (public-domain
  scans from the Internet Archive, Project Gutenberg born-digital, etc. — see
  CLAUDE.md "Expanding the test corpus") spanning scan qualities, layouts
  (single page, two-page spread, multi-column), and structure sources (outline /
  printed TOC / neither). Run the pipeline through segment on all of them and
  end-to-end on a sample; fix what surfaces; minimize each breakage into a test.
  Generalization is the point — a tool that only survives Firestone is not v1.
- Run the full regression set end-to-end; fix what surfaces.
- Duration-sanity and marker-count package gates; `--allow-gaps` escape hatch with
  audible markers.
- README rewrite: install (Tesseract/ffmpeg), quickstart, review workflow, manifest
  reference. (No version tag — stays 0.x.)
- Mastering staleness cache (today every build re-masters all 8 h: cache chapter
  AACs keyed by `(chapter_wav_hash, lufs, bitrate)`); `--mp3` opt-in for the side
  product instead of always paying a second full encode.

**Accept when:** fresh clone → `pip install -e .` → `vorpal build` succeeds on all
three regression books on Windows, meeting every product-level criterion in
[02-product-vision.md](02-product-vision.md); and on the corpus sweep, every book
either builds clean or pauses at review with an honest, actionable table — never
garbage output, never a crash.

---

# Arc 2 — The voice suite & expressive narration

*(Added 2026-06-07 after Phases 0–4 landed. These phases are planned from
[07-ideation.md](07-ideation.md) — the thinking lives there, the commitments
live here. Same rules as Arc 1: each phase ends in a working state with
acceptance criteria; the Firestone book + digital regression books remain the
standing test set. Hard boundary throughout: **users never supply voice
samples** — the suite is curated by us, even when a voice was trained by us.)*

## Phase 6 — Voice suite v1 *(picking a narrator becomes a 30-second decision)*

- `tts/voices.py` — the **voice registry**: curated entries
  `{id, display_name, engine, params, description}`. v1 sources: Kokoro
  single voices + **curated blends** (Kokoro voices are embedding tensors; a
  weighted mix is a new narrator for free). The registry is the only thing
  users see; engines/params are implementation detail.
- `vorpal voices` — list the suite; `vorpal voices --sample [--text "…"]`
  renders a short audition WAV per voice into `voices_preview/`.
- `--voice <id>` resolves through the registry; the manifest stores the id
  **and the resolved params**, and the chunk-cache key uses resolved params —
  editing a blend recipe must invalidate precisely the affected audio.
- README gains a "Voices" section with the suite table.

**Accept when:** registry ships ≥ 6 curated voices including ≥ 2 blends with
distinct character (audition them — **(human)** pick favorites); a full build
runs with a blend voice; changing a blend's weights re-synthesizes (cache
invalidation test); `vorpal voices --sample` outputs play correctly.

## Phase 7 — First tone-capable engine *(the realization path, proven)*

- One API engine adapter behind `TTSEngine` — choose at spike time between
  OpenAI steerable TTS (instruction strings) and Azure Neural (SSML
  `express-as` styles); both map cleanly onto our tone vocabulary
  (full-book cost ≈ $5–15, see ideation §1c).
- Cost machinery before the first request: per-build character count →
  estimate printed at the review gate; `--max-cost` aborts over budget.
- Network failure modes mapped into the existing retry→split→abort policy;
  API results enter the same chunk cache (keys already carry engine + tone).
- Tone pass-through proven **without** the tagger: manually set one chapter's
  chunks to `somber` in a scratch run; the engine must realize it.

**Accept when:** a 1-chapter Firestone build through the API engine completes
with `failed: 0` and a printed cost line matching the estimate (±20 %); the
manual-tone chapter measurably differs from its neutral build (f0/energy/rate
delta — the acoustic check from ideation §2d); pulling the network mid-build
aborts loudly with a resumable cache.

## Phase 8 — Tone tagging & the effectiveness verdict *(`--expressive`)*

- `tone.py` — LLM tags **paragraphs** against the ≤ 8-tag vocabulary
  (ideation §2a) with context windows; **smoothing/hysteresis** (min 2–3
  paragraph runs; isolated spikes damped to neutral); confidence-gated
  (low confidence → neutral); cached per
  `(chapter_text_hash, model, prompt_version)`.
- Review surface: `vorpal review --tones` prints the per-chapter tone map for
  editing in `book.json`; `report.md` gains the tone histogram.
- Chunker aligns chunk boundaries with tone-run boundaries (tone is
  per-chunk).
- The **effectiveness gate**, per ideation §2d: (a) acoustic-delta check —
  non-neutral tags must produce statistically distinct audio; (b) a blind A/B
  kit — paired 1-minute clips (tagged vs all-neutral) emitted for the user.
- Everything behind `--expressive`, off by default. The deterministic
  no-tone build must remain byte-identical to Phase 7 output.

**Accept when:** tagging Firestone twice is a 100 % cache hit; neutral
fraction lands in a sane band (≳ 60 %); the acoustic-delta gate passes for
every tag the engine claims to support; **(human)** the A/B kit verdict —
the feature stays opt-in unless the tagged build wins.

## Phase 9 — In-house voices *(design + spike only, gated on 6–8)*

Custom-training our own suite voices (the own-it-forever path to the
character narrator). Deliberately **not specified yet** beyond guardrails:

- Spike first: dataset licensing diligence (only properly licensed voice
  data), candidate base models (StyleTTS2 / Orpheus / Kokoro fine-tune), one
  proof-of-concept voice evaluated against the suite's quality bar.
- Ships, if ever, as a registry entry like any other — users see a name and
  a sample, never the training story.
- Full phase plan gets written into this doc only after the spike reports.

---

## Far future (thought about, deliberately not planned)

- **A visual layer / exe.** Bottom of the priority list by decision
  (2026-06-07): we need a product before packaging. When its day comes, the
  UI-worthy moments are already CLI checkpoints — review-table editing, voice
  audition, tone-map inspection, build progress — which suggests a thin local
  web UI (or TUI) over the manifest, then perhaps a PyInstaller exe. Nothing
  in the architecture blocks this; nothing in it is being built now.

## Post-Arc-2 candidates (explicitly deferred)

In rough value order (expressive narration graduated into Phases 6–9 above):

1. **ASR round-trip QA** — Whisper spot-check of sampled chunks, WER alerts.
2. **Performance** — parallel page OCR (process pool), batched TTS on GPU
   (matters more once API engines bill per request).
3. **EPUB input** — second `extract` backend; segmentation gets structure for free.
4. **LLM-assisted repair** — optional pass for OCR-damaged passages and smarter
   front-matter classification on weird books (deterministic core,
   model-assisted edges).
5. **Pronunciation lexicon** (per-book overrides for names/terms; LLM proposes
   from the book's proper nouns, user approves in review).
6. **Draft-mode builds** (`--draft`: fast engine, no mastering) for whole-book
   iteration before committing GPU/API spend.

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
