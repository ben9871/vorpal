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

## Phase 5 — Multi-format input & end-to-end hardening *(no release)*

*(Re-scoped 2026-06-07: no v1.0 tag, no PyPI — the project stays 0.x personal
tooling for now. "v1" below means the quality bar, not a release event. The
energy after this phase goes to expressiveness — see
[07-ideation.md](07-ideation.md).)*

- **EPUB + plain-text input (do this first — easy win, unlocks Gutenberg).**
  The PDF apparatus exists to *reconstruct* structure that PDFs destroy; EPUB
  ships structure intact, so it must NOT be forced through extract/segment.
  Per-format convergence points:
  - **PDF** → extract → segment (existing path, unchanged).
  - **EPUB** (`extract/epub.py`) → parse container/OPF spine + nav/NCX TOC →
    sections with clean bodies directly — converging at the *segment output*
    interface (manifest sections + body text). Chapters are ground truth
    (`source: "spine"`); review auto-approves. Implementation: stdlib
    (`zipfile` + `xml.etree` + `html.parser`) — avoid `ebooklib` (AGPL).
  - **TXT** (`extract/text.py`) → clean-text chapter heuristics (safe here:
    no OCR noise — v0's failure modes don't apply) → same section interface;
    falls back to single-section + review like any unstructured book.
  - `ingest` dispatches on file type; everything from normalize onward is
    format-blind already. Manifest records `source.format`.
  Accept when: a Gutenberg EPUB builds end-to-end with chapters from the
  spine/TOC and **zero review edits**; a Gutenberg TXT builds with plausible
  chapters (≤ 2 edits); small EPUB/TXT fixtures join the fast test suite.

- **Corpus sweep:** pull a diverse set of lawful real-world books — PDFs from
  the Internet Archive (see the validated recipe in
  [06-corpus.md](06-corpus.md)) **and EPUBs/TXTs from Project Gutenberg**
  (in scope once the item above lands) — spanning scan qualities, layouts
  (single page, two-page spread, multi-column), structure sources (outline /
  printed TOC / neither / spine), and formats. Run the pipeline through
  segment on all of them and end-to-end on a sample; fix what surfaces;
  minimize each breakage into a test. Generalization is the point — a tool
  that only survives Firestone is not v1.
- **Testing tiers (standing rule):** the pytest suite runs on *small fixtures
  only* (page excerpts, generated mini-books, minimized regressions —
  seconds, deterministic); full-book runs are *acceptance/corpus activities*
  whose results are **recorded** in the status doc and corpus table, never
  asserted in pytest. No test may take minutes.
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

*Credential gate:* no TTS-provider key (OpenAI/Azure) is provisioned yet.
Without one: implement the adapter, cost machinery, and failure mapping
against a **mock engine with recorded-response tests**; mark every live
acceptance item **(blocked: needs TTS provider key)** in the status doc —
never simulate a pass. The phase is "done (pending live acceptance)" in that
state. Do not block Phase 8 on this — see its no-key path.

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

*No-key path:* the tagging pass needs only `VORPAL_ANTHROPIC_KEY` (already
provisioned — CLAUDE.md §Credentials). For realization, use the **Kokoro
approximation layer** (speed/pause/blend shifts) as the tone-capable engine —
run the acoustic-delta gate and produce the A/B kit against it. Re-run the
gates against a real API engine when Phase 7's credential arrives.

# Arc 3 — Hardening, QA & reachable post-v1 *(designed for unsupervised runs)*

*(Added 2026-06-07. Arc 2 (Phases 5–8) shipped fast; this arc is a curated
day's worth of **safe, bounded, reversible** work to run while the operator is
away. Execution order is numeric: **10 → 11 → 12 → 13 → 14**, then Phase 9
(research, proposal-only) last. Every phase: independently committable, one
`Phase N: …` commit with evidence, status-doc update, suite green. Obey the
Unsupervised-run protocol in CLAUDE.md — no money spent, no >100 MB downloads
except where a phase names them, no remote pushes, no irreversible ops; if
blocked or out of work, write a proposal and stop cleanly — never invent risky
work or simulate acceptance.)*

## Phase 10 — Arc 2 hardening & self-review *(do first — pure quality, no deps)*

Arc 2 was built fast; this phase is the adversarial second pass.

- Review the Phase 5–8 modules (`extract/epub.py`, `extract/text.py`,
  `tts/voices.py`, `tts/api_engine.py`, `tts/kokoro_approx.py`, `tone.py`,
  `master.py` cache) for the bug classes a fast build leaves: encoding
  (the cp932 `read_text` class), unclosed file/subprocess handles, cache-key
  correctness, empty/degenerate inputs, malformed EPUB/TXT, error paths that
  swallow failures. Fix with a test per bug.
- Re-run the full corpus through `--stop-after segment`; confirm no regressions
  vs the recorded `06-corpus.md` results.
- No behavior change to already-passing paths; net new tests only.

**Accept when:** review notes (what was checked, what was found) in the status
doc; each fix has a regression test; suite green; corpus results unchanged or
improved.

## Phase 11 — Tone effectiveness materials *(the eval, minus the human verdict)*

Phase 8 built the tagger and gates; this runs them for real and produces the
evidence the human A/B verdict needs. The `cli` tone backend runs on the
subscription — **no API spend**.

- Live-tag Firestone + 2 corpus books (`--expressive`, default `cli`/haiku);
  emit per-book tone histograms; assert neutral fraction ≳ 60 %.
- **Acoustic-delta gate**: synthesize a fixed sample passage under each
  non-neutral tone via the Kokoro approximation engine; measure f0
  mean/variance, energy, speaking rate; assert non-neutral tones are
  statistically distinct from neutral. Add `librosa` (or scipy-only) under a
  `[audio]` extra — expected dependency for this phase.
- **A/B kit**: write paired ~1-minute clips (tagged vs all-neutral) to
  `ab_kit/` with a manifest, for the operator's blind listening verdict.
- Also re-run with `--tone-model sonnet` on one book so haiku-vs-sonnet tag
  quality can be compared.

**Accept when:** histograms + acoustic-delta numbers (pass/fail per tone) in
the status doc and a report; A/B kit on disk; **(human, pending)** the blind
verdict — the feature stays `--expressive` opt-in until it wins.

## Phase 12 — ASR round-trip QA *(catch TTS derailment automatically)*

- `qa/asr.py`: transcribe a sampled fraction of synthesized chunks with a
  small local Whisper (`base` or smaller — names a model download, expected),
  compare to the chunk's source text, compute word-error rate, flag outliers.
  Catches mispronunciation / dropped-word / derailment classes nothing else
  catches. Off by default (`--asr-check`); GPU-accelerated when present.
- Unit-test the WER + sampling logic on synthetic transcript pairs (no model
  needed in tests).

**Accept when:** on a Firestone chapter, per-sampled-chunk WER computed,
outliers listed in `report.md`; unit suite green; default build path unchanged.

## Phase 13 — Pronunciation lexicon *(per-book name/term overrides)*

- `lexicon.py`: an optional LLM pass (tone-backend infra — `cli`/subscription
  by default) proposes pronunciations for the book's proper nouns; stored in
  the manifest; surfaced in `vorpal review --lexicon` for approval/edit;
  `normalize` applies approved entries (misaki custom-pronunciation hooks).
- Deterministic core untouched: no lexicon ⇒ byte-identical output.

**Accept when:** a lexicon is proposed for Firestone's proper nouns, stored,
editable in review, and applied in normalization (round-trips); table-driven
tests on application logic; build without `--lexicon` is unchanged.

## Phase 14 — Draft-mode builds *(`--draft`: fast whole-book iteration)*

- `--draft`: skip mastering (no loudnorm/M4B), emit a single concatenated
  preview WAV/MP3; optionally a faster synth config. For checking chapter
  detection + narration flow across a whole book before committing the full
  GPU/mastering spend.

**Accept when:** `--draft` produces a listenable whole-book preview markedly
faster than a full build; documented in README; full build path unchanged.

---

## Phase 9 — In-house voices *(hands-on research spike — isolated, run last)*

The own-it-forever path to a character narrator. This is a **real spike**: the
container is a sandbox, so the agent may download open models, pull
properly-licensed / public-domain voice data, and run actual fine-tune /
inference experiments on the GPU — **as long as it stays within hardware budget
and isolated from the shipped pipeline**. Constraints (see CLAUDE.md
Unsupervised-run protocol § research playground):

- **Isolation:** all experiment work lives under `playground/` (gitignored —
  model weights, datasets, sample audio). It must NOT modify the shipped
  package (`vorpal/…`), the voice registry, or any committed pipeline path.
  Integrating a trained voice into `tts/voices.py` is gated on human
  confirmation — surface samples + a recommendation, don't wire it in.
- **Hardware budget:** detect VRAM (`nvidia-smi`) and RAM (`free`) at the
  start; stay well under (target ≤ ~80 % VRAM, leave system RAM headroom);
  monitor during runs and abort before OOM. Prefer small models / LoRA /
  short runs over anything that would wedge the machine. The RTX 4050 laptop
  GPU (~6 GB VRAM) is modest — size experiments to it.
- **Still hard limits:** no money (no paid APIs / no paid datasets — open &
  public-domain only); no accepting commercial licenses on the operator's
  behalf; no remote pushes; no single run left unattended that you can't
  checkpoint and resume.
- **Output (committed):** `docs/08-voice-training-spike.md` — what was tried,
  what worked, hardware actually used, sample-audio pointers in `playground/`,
  candidate base models (StyleTTS2 / Orpheus / Kokoro fine-tune) with real
  measured trade-offs, a **go / no-go recommendation**, and a proposed
  Phase-15 plan for *integrating* a chosen voice (the part that needs sign-off).

**Accept when:** the spike doc exists and is grounded in *actual* experiments
(real numbers, real hardware usage, listenable samples in `playground/`); the
shipped package is untouched; the run stayed within budget and spent no money;
ends with a go/no-go + proposed integration plan.

---

# Arc 4 — Scale, repair & the product shape *(next unsupervised day)*

*(Added 2026-06-07 as the run that built Arc 3 finished in under an hour — the
queue needs more depth. Same protocol as Arc 3: numeric order, one
`Phase N: …` commit + status update per phase, host-verified, reversible, no
spend / no remote push, mark blocked/human honestly, stop-clean-with-a-proposal
if you run dry. Order: 15 → 16 → 17 → 18 → 19 → 20.)*

### Tone-backend credential status — manual-seeding protocol (Arc 4)

`VORPAL_ANTHROPIC_KEY` has zero credits and `claude -p` is not authenticated
inside the container. For **any phase that exercises the LLM tone/repair
backend** (currently Phase 17), the agent must use the **manual-seeding
approach** rather than blocking:

1. Find actual low-confidence blocks in the Firestone `pages.jsonl` (real data,
   not synthetic).
2. Write plausible repair proposals by hand for 1–2 of them — the same JSON
   structure the LLM would return.
3. Inject them into the manifest and run the full downstream workflow:
   diff-surfacing in review, approve/reject round-trip, apply path in
   normalization.
4. Document clearly: *"LLM proposal step was manually seeded — logic and
   workflow verified; live call blocked on credentials."*

**Why this approach:** the goal is to confirm that the code paths, data
structures, review surface, and normalization application are all correct
*before* credentials are wired in. When the token is added, only the source
of the proposals changes — everything downstream is already proven. A manually-
seeded green is honest (and useful); a blocked phase that does nothing is not.
This same pattern was used successfully in Phase 8 (tone cache pre-populated
manually) and Phase 13 (lexicon round-trip tested without live LLM call).

The `claude -p` `/login` step: if it requires interactive login the agent
cannot complete it unsupervised — mark it `(human: claude -p needs /login)`
in the status doc and proceed. Do not let it stall Phase 15.

## Phase 15 — Parallel page OCR *(biggest wall-clock win)*

- OCR is the slowest stage; parallelize page extraction across a process pool
  (`concurrent.futures.ProcessPoolExecutor`), worker count from CPU budget.
  Pages are independent — the page model already isolates them. Deterministic
  output order preserved; per-page QA unchanged.

**Accept when:** Firestone extraction is markedly faster (record before/after
wall-clock) with byte-identical `pages.jsonl` vs serial; worker count
cpu-bounded; unit test on the dispatch/ordering with a stub extractor.

## Phase 16 — Batched TTS on GPU *(synthesis throughput)*

- Synthesize multiple chunks per GPU call where the engine supports it;
  respects the chunk cache (only uncached chunks batched) and the
  retry→split→abort policy per chunk. Falls back to serial on CPU.

**Accept when:** a Firestone chapter synthesizes faster batched than serial on
GPU (record numbers), `failed: 0`, cache hits unchanged, output audio
equivalent; serial path untouched on CPU.

## Phase 17 — LLM-assisted OCR repair *(the scalpel)*

- Optional pass (`--repair`, tone-backend infra, `cli`/subscription default):
  for blocks flagged low-confidence by extraction QA, send the mangled text
  **with surrounding clean context** to the model, get a proposed repair,
  **show the diff in review** for approval. Deterministic core untouched — no
  `--repair` ⇒ byte-identical output; repairs are opt-in, diff-shown, never
  silently applied.

**Accept when:** on a low-quality scan, mangled passages get plausible repair
proposals surfaced in review (not auto-applied); approve/reject round-trips
through the manifest; build without `--repair` unchanged; logic unit-tested
with a mock backend.

*Credential note (Arc 4):* `cli` backend needs `/login`; `api` backend needs
credits. Use the **manual-seeding protocol** (see Arc 4 intro above): take 1–2
actual low-confidence blocks from the Firestone `pages.jsonl`, write plausible
repairs by hand, inject them, and run the full approve→apply path. This proves
the diff-surface, review round-trip, and normalization application. Mark the
live LLM proposal call as `(blocked: credentials — manual seed used for
workflow verification)`. When credentials arrive, the only change is replacing
the seed with a real LLM call; all downstream logic is already verified.

## Phase 18 — Library / batch mode *(folder → shelf)*

- `vorpal build <dir>` (or `vorpal library <dir>`): discover book files, build
  each over the existing content-addressed cache, continue past a single book's
  failure (record it, don't abort the shelf), emit a library-level summary.
  This turns the autonomous muscle into a product feature.

**Accept when:** pointing at a directory of 3+ mixed-format books builds each
to M4B (or pauses each at review honestly), one book's failure doesn't sink
the rest, a `library_report.md` lists per-book status; resume skips
already-built books via cache.

## Phase 19 — Manifest as a first-class artifact *(other renderers)*

- The cleaned `book.json` + chapter bodies are a structured edition, not just a
  build file. Add a renderer: `vorpal export <input> --as epub|txt` emits a
  clean reading EPUB / structured text from the manifest (chapters, front/back
  matter, footnotes as a side-channel) — no audio. Proves the manifest is the
  real asset; the audiobook becomes one renderer of many.

**Accept when:** a built book exports to a valid clean EPUB (opens in a reader,
correct chapter nav) and a structured TXT; footnotes present but separated;
round-trips through the same manifest the audiobook uses.

## Phase 20 — Corpus-hardening loop *(generalization, loop-until-dry)*

- Pull a wider, more hostile corpus (multi-column journals, heavy-footnote
  academic books, non-English public-domain, poor scans) per the
  `06-corpus.md` recipe; run each through `--stop-after segment`; for every
  breakage, **minimize it into a small fixture test** and fix. Loop until a
  round surfaces nothing new. Record every book + result in `06-corpus.md`.

**Accept when:** ≥ 8 new diverse books processed without crash or garbage (each
builds clean or pauses honestly at review); every breakage found became a
committed regression test; `06-corpus.md` updated.

---

# Arc 5 — Voice depth & the expressive tier proven *(Phases 21–25)*

*(Queued 2026-06-08. Arc 4 builds scale and product shape; Arc 5 completes the
expressive narration story that Arc 2 started. The two credential gaps that
have blocked live acceptance since Phase 7 (OpenAI TTS key, Anthropic API
credits / `claude -p` auth) are assumed resolved before Arc 5 begins — or each
blocked item is marked honestly and skipped. Same protocol: numeric order, one
commit per phase, status-doc update, no spend beyond what's explicitly
authorized per phase, no remote push.)*

## Phase 21 — OpenAI TTS live acceptance *(Phase 7 pending items)*

Phase 7 built the `APIEngine` adapter, cost machinery, and mock-engine tests,
but every live acceptance item was blocked for lack of `VORPAL_OPENAI_KEY`. This
phase completes it — no new code expected beyond wiring the credential.

- Run a 1-chapter Firestone build via `APIEngine`: cost estimate printed before
  synthesis, `failed: 0`, chapter audio present.
- Pull the network mid-build; confirm abort with a resumable cache (no re-synth
  of already-completed chunks on resume).
- Manual-tone acoustic delta: set one chapter's chunks to `somber` in the
  manifest; confirm f0/energy/rate measurably differ from the neutral build.

**Accept when:** all Phase 7 live acceptance items cleared; `(blocked)` marks
removed from the status doc. *(Credential gate: if `VORPAL_OPENAI_KEY` still
not provisioned, mark every item `(blocked: VORPAL_OPENAI_KEY not set)` and
skip — do not simulate a pass.)*

## Phase 22 — Tone with instruction engine *(warm/wry fixed)*

The Kokoro approximation layer passed 5/7 tones on the acoustic gate (Phase 11).
`warm` failed (5% speed shift too small to clear the 5% dur_diff threshold) and
`wry` failed by design (no speed delta). A real instruction-based engine
(gpt-4o-mini-tts) expresses tone through prose instructions, not speed alone,
so both should clear.

- Re-run the Phase 11 acoustic-delta gate against `APIEngine`; assert all 8
  tones pass.
- Regenerate the A/B kit (paired clips, tagged vs all-neutral) against the
  instruction engine; emit to `ab_kit_v2/`.
- Update `report.md` template to record which tones passed on which engine.

**Accept when:** all 8 tones pass the acoustic gate; A/B kit re-generated;
**(human)** blind listening verdict on the new clips. *(Blocked on Phase 21.)*

## Phase 23 — StyleTTS2 voice design spike *(Phase 9b)*

Follow-up to Phase 9's conditional go/no-go and the proposal in
`docs/08-voice-training-spike.md` §8. Run this whether or not the PCA voice
was approved — it addresses the architectural gap Kokoro has (no audio encoder)
and extends the voice-design space beyond the existing voice manifold.

- Download StyleTTS2-LibriTTS (~1.2 GB, Apache-2.0 license) to `playground/`.
- Pick a public-domain LibriVox reader with a desired acoustic profile; use
  StyleTTS2's encoder to extract a reference style embedding.
- Optimize that embedding toward a target character profile (gradient descent
  on reconstruction loss, no decoder retraining).
- Compare output to `vorpal_narrator_v1` (Phase 9 PCA voice) on the same 248-
  char Firestone test passage; record duration, RMS, pitch.
- Update `docs/08-voice-training-spike.md` with real numbers, listenable
  samples in `playground/`, and a go/no-go on registry integration.

**Accept when:** spike doc updated with measured comparisons; `vorpal/` package
untouched; no money spent; VRAM budget respected (target ≤ 80% of 6 GB);
ends with go/no-go + proposed integration plan.
*(Isolation: all experiment work in `playground/` — same protocol as Phase 9.)*

## Phase 24 — Dialogue-aware delivery *(same narrator, subtle shift)*

Detect quoted speech in chapter bodies; annotate the corresponding chunks;
apply a conservative delivery adjustment. The one-narrator contract holds —
this is tonal inflection, not dramatization.

- Quoted-speech detector in `normalize.py` or a new `segment/dialogue.py`:
  identify `"…"` spans, classify as dialogue vs narration, annotate chunks
  with `is_dialogue: bool`.
- `TTSEngine` adapters that support it (`APIEngine` instruction strings,
  `KokoroApproxEngine` speed/pause) apply a subtle shift for `is_dialogue`
  chunks. Controlled by a registry-level `dialogue_style` field; default: no
  shift (safe upgrade for existing builds).
- Unit tests on the detector with edge cases: nested quotes, multi-paragraph
  dialogue, em-dash interruptions, dialogue-only chapters.

**Accept when:** detector unit tests green; a Firestone chapter with quoted
speech has `is_dialogue` chunks annotated; build without dialogue support
byte-identical to pre-Phase-24; **(human)** listening spot-check finds the
delivery shift natural and not jarring.

## Phase 25 — Footnote narration mode *(opt-in)*

Footnotes have been separated and discarded since Phase 2. Some books (heavily
annotated academic texts) lose meaningful content that way. Add opt-in modes:

- `--footnotes inline`: append each footnote after its parent chapter body,
  preceded by a spoken delimiter ("Footnote one: …"). Footnote markers in the
  body text are replaced with brief spoken cues ("footnote one").
- `--footnotes chapter`: emit all footnotes as their own chapter entry
  (`kind: footnotes`, default `include: false` in review — visible, not
  auto-included).
- Normalization applies to footnote text: citation markers stripped, numbers
  spoken, same TTS normalization path as body text.
- Unit tests on footnote formatting for both modes; default build (no flag)
  unchanged.

**Accept when:** both modes produce valid manifest entries; footnote text
normalized and audible in the build; no content appears in TTS text without
`--footnotes`; round-trip through review checkpoint works.

---

# Arc 6 — Polish & reach *(Phases 26–30)*

*(Queued 2026-06-08. Arc 5 completes the expressive tier; Arc 6 is about
quality-of-life, output richness, and the product's front door. Each phase is
independently committable and self-contained. No new credential requirements
beyond what Arc 5 resolved.)*

## Phase 26 — Piper draft engine *(CPU-speed drafts)*

`--draft` currently skips mastering but still synthesizes with Kokoro. On a
CPU-only machine Kokoro synthesis is the bottleneck; a full Firestone draft
still takes hours. Piper (VITS-based, very fast on CPU, lower quality) makes
`--draft` actually fast.

- `tts/piper_engine.py` implementing `TTSEngine`; Piper discovered via
  `shutil.which('piper')` — opt-in dependency, gracefully absent.
- `--draft` selects `PiperEngine` when Piper is on PATH; falls back to Kokoro
  with a warning if not found (current behavior preserved).
- Quality difference clearly documented in the build log; draft artifacts
  labelled `_draft_piper` vs `_draft_kokoro` so they're not confused.
- Unit test: `PiperEngine` conforms to `TTSEngine` interface; Piper-absent
  fallback path exercised.

**Accept when:** a full-book draft on CPU with Piper is markedly faster than
Kokoro draft (record wall-clock); audio intelligible; default non-draft build
unchanged; Piper absence degrades gracefully.

## Phase 27 — Listening-target loudness profiles *(car / headphones / speaker)*

The mastering stage targets a fixed −18 LUFS. Different playback contexts have
materially different optimal targets — a car environment benefits from higher
average loudness and slightly more compression; headphones prefer more dynamic
range.

- Named presets behind a `--profile` flag: `headphones` (−18 LUFS, current
  default), `car` (−16 LUFS, slightly tighter compression), `speaker`
  (−20 LUFS, more dynamic). Stored in `manifest.settings.profile`.
- Changing `--profile` invalidates only the mastering stage (synthesis cache
  untouched — the profile affects loudnorm parameters, not TTS).
- Unit test: each preset produces the expected `target_lufs` in the manifest;
  downstream LUFS gate uses the per-profile target, not the hard-coded −18.

**Accept when:** `--profile car` builds to −16 LUFS verified via ffprobe
loudnorm stats; synthesis cache hit (no re-synth); default (`--profile
headphones`) unchanged.

## Phase 28 — Richer cover art & metadata *(the audiobook as artifact)*

Cover art is currently extracted from PDF page 1, which is often the copyright
page on scanned books, not the cover. Metadata (narrator, year, language,
publisher) is minimal.

- Smarter cover extraction for PDFs: score candidate pages (page 1, pages 2–5)
  by image density and title-text proximity; pick the best candidate or accept
  `--cover <image>` override (already wired).
- For EPUBs: read the OPF `<item properties="cover-image">` entry directly
  instead of rendering a page.
- Embed additional MP4/ID3v2 tags: narrator (from `--voice` registry entry
  display name), year (`--year`), language (`--language`, default `en`),
  publisher (`--publisher`).
- Unit tests on cover-selection heuristic with stub pages.

**Accept when:** a built M4B has correct title/author/year/narrator tags
verifiable in VLC; EPUB cover used when available; `--cover` override still
works; `--cover` flag documented in `vorpal build --help`.

## Phase 29 — Chapter summary side product *(text-only, never narrated)*

An optional `--summaries` flag that uses the LLM tone-backend to generate a
one-paragraph summary per chapter, stored in the manifest and emitted as
`summaries.md` alongside the audiobook. Content-fidelity contract holds: the
summaries are never narrated, never injected into TTS text.

- Cache per `(chapter_text_hash, model, prompt_version)` — same pattern as
  `tone.py`; a book is summarised once, ever.
- Use the **manual-seeding protocol** (Arc 4) if credentials are still absent:
  hand-write one or two summaries, inject them, verify the manifest storage,
  review surface, and `summaries.md` emission. Mark live calls
  `(blocked: credentials — manual seed used)`.
- `vorpal review` shows summaries for spot-checking; summaries are editable in
  `book.json` like any other manifest field.

**Accept when:** summaries stored in manifest and emitted to `summaries.md`;
zero summary text appears in any TTS chunk; cache round-trip tested; build
without `--summaries` byte-identical.

## Phase 30 — TUI / thin local web UI *(the product's front door)*

The "far future" item from `docs/07-ideation.md` §2e, now earned: Arc 1–5
built a product whose real asset is a clean `book.json`. A thin local UI makes
that manifest interactive — the same human checkpoints that exist as CLI steps
become a UI flow.

- `vorpal serve <input>` starts a local FastAPI server and opens the browser.
- The UI reads/writes `book.json` directly — no new data model beyond what
  already exists.
- Surfaces: chapter review table (editable, with approve/reject), voice
  audition (plays samples from `voices_preview/`), tone-map inspection
  (per-chapter tone distribution), build progress (streamed via SSE).
- Editing a chapter title or toggling `include` in the UI writes to the
  manifest and triggers selective downstream invalidation — same as the CLI
  review path.
- CLI path entirely unchanged: `vorpal serve` is additive.

**Accept when:** `vorpal serve` starts a local server; chapter table is
editable and changes persist to `book.json`; a build can be triggered from
the UI with live progress; CLI `vorpal build`/`vorpal review` unaffected.
**(human)** usability spot-check: can complete a full review→approve→build
cycle without touching the CLI.

---

---

# Arc 7 — Theatrical Mode: Play Ingestion & Multi-Voice Dramatization *(Phases 31–40)*

*(Queued 2026-06-09. Arc 6 completed the book pipeline; Arc 7 extends vorpal
into a second content class: stage plays. A play is a book where the "chapters"
are acts and scenes, the "text" is speeches attributed to named characters, and
the "narrator" is a full cast. The manifest-driven pipeline carries over almost
entirely — the new work is a play parser, a voice-casting layer, and a
multi-voice synthesis router. Source: Project Gutenberg public-domain plays
(Shakespeare and others). Download recipe: same `docs/06-corpus.md` fetch
recipe, pointed at the Gutenberg play catalogue.)*

*(All phases follow the standard unsupervised protocol: one commit per phase,
`docs/05-status.md` updated, 09-human-review-queue.md for human items.
Free-time Wonderland work in `playground/` between phases as usual.)*

---

## Phase 31 — Gutenberg play downloader + plain-text play parser

The entry point for everything that follows. Plays on Project Gutenberg ship as
plain UTF-8 `.txt` files with a standard header/footer, ALL-CAPS speaker labels,
and square-bracket stage directions. Parse this into a structured `play.json`
that Arc 7's subsequent phases consume.

- `vorpal/play/fetcher.py`: `fetch_play(title_or_id)` — resolves a title to
  a Gutenberg book ID (small hardcoded catalogue: Hamlet `#1524`,
  A Midsummer Night's Dream `#1514`, Macbeth `#1533`, Twelfth Night `#1523`,
  The Tempest `#23042`, Much Ado `#1882`), downloads with `urllib`, strips the
  standard PG boilerplate header/footer (regex on the canonical boundary
  strings), saves to `corpus/plays/<slug>.txt`.
- `vorpal/play/parser.py`: `parse_play(text) → PlayDoc` — a dataclass tree:
  `PlayDoc(title, author, acts[Act(name, scenes[Scene(name, location,
  beats[Beat(type, speaker?, text)])])])`. Beat types: `speech`, `direction`.
  Speaker labels detected as ALL-CAPS words followed by `.` or nothing at a
  line start (Gutenberg Shakespeare convention). Stage directions: `[…]`
  blocks and indented italic-substitute lines. Act/scene headers: lines
  matching `ACT [IVX]+` / `SCENE [IVX]+`.
- `vorpal/play/models.py`: the PlayDoc / Act / Scene / Beat dataclasses;
  `to_dict()` / `from_dict()` for JSON round-trip.
- Unit tests: generated mini-play fixtures (inline strings — no downloaded
  files in pytest); assert act count, scene count, speaker set, direction
  count for a 3-act 2-character excerpt.

**Accept when:** `vorpal fetch-play hamlet` downloads and strips the PG
Hamlet text to `corpus/plays/hamlet.txt`; `parse_play()` produces a PlayDoc
with 5 acts, 20 scenes, and all major speakers present; unit tests green on
small fixtures; no test requires a network call.

---

## Phase 32 — Character extraction + role classification

From `play.json`, build `cast.json`: the character registry the casting
algorithm (Phase 33) and the synthesis router (Phase 35) will consume.

- `vorpal/play/characters.py`: `extract_cast(play_doc) → list[Character]`.
  Each `Character`: name, `line_count`, `word_count`, `role`
  (`protagonist | major | minor | cameo` — thresholds by word-count
  percentile: top 1 = protagonist, top 10% = major, top 40% = minor, rest =
  cameo), `gender_guess` (`m | f | unknown` — heuristic: pronoun scan in
  stage directions referencing the character + a hardcoded Shakespeare
  canonical-name gender table covering the ~60 most common names; fallback
  `unknown`).
- `cast.json` written to the play workdir alongside `play.json`.
- Unit tests: Hamlet fixture → Hamlet is protagonist, Horatio/Ophelia are
  major, First Gravedigger is minor; gender heuristic correct on the
  hardcoded-name set.

**Accept when:** `extract_cast` on the parsed Hamlet returns the correct role
classification for at least 10 named characters; `cast.json` round-trips
through `from_dict`; gender table covers Hamlet, Ophelia, Horatio, Gertrude,
Laertes; unit tests green on fixtures.

---

## Phase 33 — Stage direction classification + emotion extraction

Stage directions in Shakespeare range from scene-setting ("*Elsinore. A platform
before the castle.*") to action ("*Exit*") to emotional cues ("*weeping*",
"*aside*", "*in despair*"). Arc 7 uses the emotional cues as tone hints for the
following speech; the rest are either silenced or narrated.

- `vorpal/play/directions.py`: `classify_direction(text) → DirectionKind`:
  `action | location | emotion_hint | entry_exit | song | other`.
  Classification is rule-based: keyword vocabulary per class (no LLM).
  `entry_exit`: contains `Enter`, `Exit`, `Exeunt`.
  `location`: first direction of a scene, no verb, describes a place.
  `emotion_hint`: contains words from an ~80-word vocabulary:
  *weeping, furiously, aside, solemnly, laughing, kneeling, embracing,
  shouting, whispering, bitterly, tenderly, in despair, in horror, joyfully*…
  `song`: stage direction contains `Sings` or `Song`.
  `action`: everything else with a verb.
- `extract_emotion_hint(direction_text) → str | None`: maps to a tone-system
  tag (`somber`, `tense`, `warm`, `wry`, `neutral`) using the vocabulary above.
  Stored on the following `Beat` as `tone_hint`.
- Unit tests: fixture directions correctly classified; hint extraction maps
  "weeping" → `somber`, "furiously" → `tense`, "aside" → `wry`,
  "tenderly" → `warm`.

**Accept when:** all direction kinds classified with ≥ 90% accuracy on a
manually labelled 50-direction fixture from Hamlet; emotion hints present on
the correct beats in the parsed play; unit tests green.

---

## Phase 34 — Voice casting algorithm

Map `cast.json` characters to voices from `vorpal/tts/voices.py`. The goal is
a plausible, varied cast: protagonist gets the richest voice, no two named
characters with more than 50 lines share a voice, gender is matched where
available, minor/cameo characters cycle through a shared pool.

- `vorpal/play/casting.py`: `assign_voices(cast, voice_registry) → CastSheet`.
  `CastSheet`: `{character_name: VoiceEntry}`.
  Algorithm:
  1. Collect available voices from registry, split into male/female/unknown pools.
  2. Assign protagonist: best voice matching gender (configurable best-voice
     name, default `bm_george` for male protagonist).
  3. Assign major characters: round-robin through gender-matched pool, skip
     already-assigned.
  4. Assign minor/cameo: shared pool — multiple characters may share a voice
     when the registry is exhausted; logged clearly.
  5. Narrator voice (for stage directions): configurable, default `bm_lewis`.
- `vorpal cast <play_txt_or_json>` CLI command: prints the cast sheet as a
  table (character | voice | role | lines | gender).
- `--cast-override cast_override.json`: `{"HAMLET": "bm_daniel"}` — overrides
  individual assignments before synthesis.
- Unit tests: 20-character cast assigned correctly from a 10-voice mock
  registry; protagonist always gets the configured best voice; no major
  character shares a voice when registry has room; overflow logged.

**Accept when:** `vorpal cast corpus/plays/hamlet.txt` prints a full Hamlet
cast table with no two major characters sharing a voice; `--cast-override`
tested round-trip; unit tests green.

---

## Phase 35 — Multi-voice synthesis routing

The synthesis engine currently uses one voice for the whole book. Plays route
each speech chunk to its character's assigned voice. Stage directions go to the
narrator voice (or are silenced). Cache keys must include the voice name so
character-A and character-B lines don't collide.

- `vorpal/play/synth_router.py`: `route_chunks(beats, cast_sheet) → list[ChunkWithVoice]`.
  Each chunk gains a `voice: VoiceEntry` field. Stage directions: if
  `--stage-directions narrator`, append a direction chunk with the narrator
  voice; if `skip` (default), drop.
- `vorpal/synth.py`: extend `_cache_key()` to include `voice.name` (already
  safe — voice name is a stable string; existing cache entries with no voice
  field get a migration default of the book-level voice name so they're not
  invalidated).
- `synthesize_chunks()`: accept per-chunk voice override; pass to engine.
- **Default (non-play) behavior unchanged** — no voice override field set,
  same cache keys as before.
- Unit tests: 2-character 4-beat exchange produces 4 synthesis calls with
  correct voice names; cache key differs between characters; narrator chunks
  have narrator voice; direction chunks absent when `--stage-directions skip`.

**Accept when:** a generated 2-character mini-play synthesizes to 2 distinct
voice assignments; cache round-trip correct; existing non-play tests unchanged
(zero cache key drift); unit tests green.

---

## Phase 36 — Act/scene chapter structure

Books get one chapter per chapter marker. Plays get one chapter per act
(default) or per scene (`--chapters scene`). Chapter titles incorporate the
scene location pulled from the first stage direction of each scene.

- `vorpal/play/chapters.py`: `build_play_chapters(play_doc, mode) → list[Chapter]`.
  `mode`: `act` (default) or `scene`. Chapter title format:
  `"Act I"` / `"Act I, Scene 3 — Elsinore. A platform before the castle."`.
  Location extracted from the scene's first `location`-classified direction
  (Phase 33); falls back to no location suffix when absent.
- These `Chapter` objects slot into the existing manifest chapter list — the
  mastering pipeline needs no changes.
- Unit tests: a 3-act 2-scene-per-act play in `act` mode → 3 chapters; in
  `scene` mode → 6 chapters; location appended when present.

**Accept when:** a mini-play fixture in `act` mode produces correct chapter
count and titles; `scene` mode tested; titles pass through `spoken_form()`
normalization without errors; existing chapter pipeline tests green.

---

## Phase 37 — Tone/emotion from stage direction context

Wire the `tone_hint` fields placed by Phase 33 into the existing tone
approximation system (Phase 11's `KokoroApproxEngine` layer). A speech
preceded by "[Weeping]" is synthesized with the `somber` tone; "[Furiously]"
with `tense`; "[Aside]" with `wry`; etc. No LLM call required — the hint
comes from Phase 33's rule-based classifier.

- `vorpal/play/synth_router.py`: extend `route_chunks()` to propagate
  `tone_hint` from the preceding direction beat onto the speech chunk's
  `tone` field.
- `vorpal/synth.py`: `_cache_key()` already includes tone; no change needed.
  `synthesize_chunk()` receives the per-chunk tone from the manifest — no
  change needed.
- Acoustic delta test (recorded in docs, not asserted in pytest): synthesize
  Ophelia's "There's rosemary, that's for remembrance" with `tone_hint=somber`
  vs `neutral`; measure pitch-mean delta (expect ≥ 5 Hz as per Phase 11
  gate). Log result in status doc.
- Unit tests: chunks following a "weeping" direction carry `somber` tone;
  chunks with no preceding direction carry `neutral`; `aside` → `wry`.

**Accept when:** tone hints from Phase 33 propagate correctly to synthesis
chunks in unit tests; acoustic delta recorded (not gated in pytest); default
book pipeline unaffected.

---

## Phase 38 — `vorpal play` end-to-end command

The unified entry point. `vorpal play <input>` runs the full play pipeline:
fetch (if URL/title given) → parse → extract cast → assign voices → tone-tag
→ synthesize (multi-voice) → chapter-structure → master → package. Includes
the same review gate as `vorpal build` — the cast sheet is the review surface.

- `vorpal/play/pipeline.py`: `build_play(input_path, options) → Path` — the
  orchestrating function, analogous to `build_book()`.
- `vorpal/cli.py`: `play` subcommand with flags:
  `--chapters act|scene` (default `act`),
  `--stage-directions skip|narrator` (default `skip`),
  `--cast-override <json>`,
  `--voice <narrator-voice>` (narrator for stage-direction mode),
  plus the standard `--output`, `--draft`, `--footnotes`, `--profile` flags.
- The review gate surfaces: cast sheet (character → voice → lines), chapter
  list, and standard chapter-text excerpt — the operator can approve or edit
  before synthesis begins.
- `vorpal/play/__init__.py` exports the public API; the `vorpal/` package
  gains no new top-level files — all play code lives under `vorpal/play/`.

**Accept when:** `vorpal play corpus/plays/hamlet.txt` runs without error
to the review gate on the small hamlet fixture; cast sheet displayed; after
`--approve`, synthesis completes with distinct per-character voices; output
is a valid `.m4b`; `vorpal build` on a non-play file unchanged.

---

## Phase 39 — Cast audition mode

Before committing to a 4-hour multi-voice Hamlet synthesis, the operator
should be able to hear who sounds like whom. `vorpal cast-audition` synthesizes
2–3 representative lines per character and outputs one `.wav` per named
character.

- `vorpal/play/audition.py`: `build_audition(play_doc, cast_sheet, output_dir)`.
  For each character with `role != cameo`: pick the 1–3 speeches with the most
  words (representative sample), synthesize with the assigned voice and tone
  hint, write `<output_dir>/<CHARACTER_NAME>.wav`.
- `vorpal cast-audition <input> [--output <dir>]` CLI subcommand.
- Lines are short (audition, not full synth): cap at 200 tokens per character.
- H-NNN entry in `docs/09-human-review-queue.md`: operator listens to the
  audition directory and decides whether to accept the casting, adjust via
  `--cast-override`, or re-run the audition with different voices. Document
  the two outcomes clearly.

**Accept when:** `vorpal cast-audition` on the mini-play fixture produces one
`.wav` per non-cameo character; files are non-empty and correctly named;
H-NNN filed in review queue; unit tests green on audition line-selection logic.

---

## Phase 40 — Play corpus hardening loop

The same loop-until-dry methodology as Phase 20, applied to plays. Download
and parse at least 5 plays, identify breakage points, minimize each into a
fixture test.

Target corpus (all Project Gutenberg public-domain):
1. **Hamlet** (`#1524`) — large cast, 5 acts, prose + verse mix.
2. **A Midsummer Night's Dream** (`#1514`) — fairy characters, short scenes,
   songs, high stage-direction density.
3. **Macbeth** (`#1533`) — short play, strong emotion cues, witches as a
   group speaker.
4. **Twelfth Night** (`#1523`) — high prose content, disguise plotline,
   many minor characters.
5. **The Importance of Being Earnest** by Oscar Wilde (`#844`) — non-Shakespeare,
   different formatting conventions: speaker labels with no ALL-CAPS, dashes
   instead of periods, longer stage directions. Good format-diversity test.

Edge cases to watch and fix:
- Group speakers: `ALL`, `BOTH`, `CHORUS`, `WITCHES` (Three Witches) — handle
  as a single synthetic character with a blended voice or dedicated group voice.
- Numbered speakers: `FIRST GENTLEMAN`, `SECOND GENTLEMAN` — deduplicate into
  pools.
- Embedded songs / sonnets (italicised, indented differently from speeches).
- Very long speeches split across multiple text paragraphs.
- Non-PG-format Wilde (different capitalisation conventions).
- Each found breakage → minimized fixture in `tests/test_phase40_plays.py`.

Update `docs/06-corpus.md` with a "Play corpus" section: title, PG ID, why
chosen, what edge case it exercises, parse result summary.

**Accept when:** all 5 plays parse without error (act count, scene count,
speaker count verified); any pre-existing parse bugs fixed and covered by
fixture tests; `docs/06-corpus.md` play section filled in; full test suite
green.

---

# Arc 8 — Trotsky Military Writings Production Run *(Phases 41–46)*

*(Queued 2026-06-09. Arc 7 delivered multi-voice play synthesis. Arc 8 is the
first full production run against real political/military literature: five volumes
of Leon Trotsky's Military Writings (1918–1923), sourced from public-domain EPUBs
and a PDF in `trotsky/`. The goal is audiobooks a human will actually listen to —
not pipeline demonstrations. Utmost respect for the source material means the text
that reaches the listener must be faithful to Trotsky's words. Two contracts
govern this arc: (1) text fidelity — every word in the source that is narrable
must reach the synthesizer; (2) audio coherence — the narration must read
naturally and the chapter structure must reflect the book's actual organisation.*

*Voice rationale: Trotsky's prose is declarative, urgent, and highly structured —
polemic and analysis in equal measure. The voice must carry authority without
theatricality. `blend_deep_steady` (Fenrir 55% + Michael 45%) is the
recommended candidate; `am_fenrir` alone is the fallback.*

*All phases follow the standard unsupervised protocol. Human review items
(listening spot-checks) are filed as H-NNN and do not block synthesis.)*

---

## Phase 41 — Text fidelity tooling + pre-flight audit *(small)*

Build a `vorpal fidelity` command that compares what the pipeline extracted
against what the source file actually contains. Run it on all five Trotsky
volumes before any synthesis.

**Tooling (`vorpal/qa/fidelity.py`):**
- `extract_epub_chapter_texts(epub_path) → dict[chapter_id, str]` — strip XHTML
  tags, decode entities, return one string per OPF spine item
- `extract_workdir_chapter_texts(workdir) → dict[filename, str]` — reads
  `chapter_texts/*.txt` written during the segment stage
- `compare_chapters(source_texts, workdir_texts) → FidelityReport`:
  - Per-chapter similarity score (difflib sequence ratio, 0–1)
  - Dropped paragraph detection: paragraphs in source absent from workdir text
  - Order anomaly detection: chapters out-of-spine sequence
  - Overall: passed (all chapters ≥ 0.90), degraded (any chapter 0.70–0.90),
    failed (any chapter < 0.70)
- `format_fidelity_report(report) → str` — Markdown table with per-chapter
  scores, dropped paragraph counts, anomaly flags
- `vorpal fidelity <epub_or_pdf> <workdir>` CLI subcommand

**Pre-flight audit:**
- Run `vorpal build <vol> --stop-after segment` for all five volumes
- Run `vorpal fidelity` on each workdir
- Record results in `docs/06-corpus.md` §"Trotsky pre-flight"
- Any chapter scoring < 0.90 is a blocker for that volume until root cause is found

**Accept when:** `vorpal fidelity` command exists and unit tests cover similarity
scoring, dropped-paragraph detection, order anomalies, and edge cases (empty
workdir, mismatched chapter counts). Pre-flight audit results recorded.

---

## Phase 42 — Voice selection: Trotsky audition

Produce audition clips for the top voice candidates using passages drawn from
Volume 1 that exercise the range of Trotsky's prose: a polemical opening, a
dense analytical passage, a direct address to soldiers, and a closing peroration.

- Select four representative passages (~150 words each) from `trotsky/military-writings-trotsky-v1.epub`
- Synthesize each with: `blend_deep_steady`, `am_fenrir`, `bm_george`
- Output audition clips to `trotsky/audition/<voice>_<passage>.wav`
- File **H-013**: listen to audition clips and confirm or override voice choice;
  default to `blend_deep_steady` if H-013 is not yet resolved
- Proceed with `blend_deep_steady` immediately; H-013 outcome may trigger a
  re-synthesize if a different voice is chosen (TTS cache makes re-render cheap)

**Accept when:** audition clips produced and non-empty; H-013 filed;
`docs/06-corpus.md` records the audition candidates and the assumed selection.

---

## Phase 43 — Audio stitching quality fix *(must land before any Trotsky synthesis)*

**Problem:** TTS models have slightly different prosody at the start and end of
each generation call — the model "knows" the context begins and ends there. When
adjacent chunk WAVs are concatenated with a hard cut, the boundary is audible:
the narrator stops mid-flow and restarts, even at a correct sentence boundary.
This is most noticeable in long, analytically dense prose (exactly what Trotsky
wrote).

**Two-part fix:**

**Part 1 — Paragraph-boundary chunking (`vorpal/normalize.py`):**
- A blank-line paragraph break must flush the chunk accumulator, even if the
  current pack is below `CHUNK_MAX_CHARS`.
- Sentences must never cross a paragraph boundary in the same chunk.
- Add `PARAGRAPH_BREAK` sentinel: when `normalize_chapter()` encounters a
  paragraph boundary, emit the current chunk (if non-empty) before starting a
  new one.
- Cache keys are unchanged (keyed on text content, not boundary logic).
- Existing unit tests must still pass; add tests covering: multi-paragraph input
  produces separate chunks per paragraph; single over-long sentence still splits
  at CHUNK_MAX_CHARS as before.

**Part 2 — Crossfade stitching at chapter assembly (`vorpal/synth.py` or
`vorpal/master.py`):**
- When concatenating adjacent intra-paragraph chunk WAVs into a chapter WAV,
  apply a short (20–30 ms) linear crossfade at the join instead of a hard cut.
- The crossfade is inaudible as a fade but eliminates the prosody-restart
  artifact by blending the tail of one generation into the head of the next.
- Inter-paragraph silence (the gap between paragraph chunks) is unchanged.
- The crossfade is applied at assembly time; the per-chunk cache files are
  unaffected (re-stitching a cached chapter is cheap and correct).
- Add `crossfade_ms: int = 25` parameter, defaulting to 25 ms; expose as
  `--crossfade-ms` CLI flag for experimentation.

**Acceptance:**
- Existing regression set (Firestone + digital books) still green — no
  stitching regression.
- Unit test: crossfade of two known WAVs produces correct output length
  (`len_a + len_b - crossfade_samples`), valid WAV, no clipping.
- Unit test: paragraph boundaries produce separate chunks; sentence boundaries
  within a paragraph pack into the same chunk when under limit.
- **(human, H-019):** synthesize a 3-paragraph passage (use a Firestone excerpt)
  before and after this fix and listen for the boundary artifact. The fix should
  make sentence-boundary joins inaudible.
- **Do not begin any Trotsky production synthesis (Phase 44 onward) until this
  phase is committed and green.** The v1 chapter WAVs already rendered
  (`trotsky_v1_workdir/chapters/`) were produced before the fix — delete them
  so they are re-synthesized with the corrected stitching.

---

## Phase 44 — Volume 1 production build (1918)

Full production build of `trotsky/military-writings-trotsky-v1.epub`.

**Build command:**
```
vorpal build trotsky/military-writings-trotsky-v1.epub \
  --voice blend_deep_steady \
  --year 1918 \
  --author "Leon Trotsky" \
  --publisher "New Park Publications" \
  --language en \
  --profile headphones \
  --output trotsky_v1
```

**QA steps after build:**
1. Run `vorpal fidelity trotsky/military-writings-trotsky-v1.epub trotsky_v1_workdir` —
   all chapters must score ≥ 0.90
2. Run `vorpal review trotsky/military-writings-trotsky-v1.epub` — verify chapter
   count matches the EPUB's spine; check no chapters have empty body text
3. Spot-check chapter titles: confirm they match Trotsky's actual section headings,
   not OCR artifacts or EPUB navigation labels
4. File **H-014**: listening spot-check — first chapter + one randomly selected
   mid-book chapter; human checks for dropped text, unnaturally rendered passages,
   and chapter-boundary clicks

**Accept when:** build completes, fidelity check passes (all ≥ 0.90), review gate
shows correct chapter count, H-014 filed, results in `docs/06-corpus.md`.

---

## Phase 45 — Volumes 2 and 3 production builds (1919, 1920)

Build `military-writings-trotsky-v2.epub` (Volume 2, 1919) and
`military-writings-trotsky-v3.epub` (Volume 3, 1920) with the same
voice/profile/metadata settings as Volume 1 (year adjusted per volume).

For each volume:
- Full build with `--year <year>` adjusted
- `vorpal fidelity` — all chapters ≥ 0.90
- `vorpal review` — correct chapter count, no empty bodies
- File **H-015** (v2) and **H-016** (v3): listening spot-checks

If a volume's fidelity check fails any chapter (score < 0.90), investigate root
cause before proceeding: compare the EPUB's raw chapter text to what the pipeline
produced and identify the extraction or segmentation step that degraded fidelity.
Fix if it is a general bug; record as a corpus anomaly if it is volume-specific.

**Accept when:** both builds complete, both fidelity checks pass, H-015 and H-016
filed, results in `docs/06-corpus.md`.

---

## Phase 46 — Volumes 4 and 5 production builds (1921–1923, PDF)

**Volume 4** (`military-writings-trotsky-v4.epub`, 1921–1923): EPUB, same
pipeline as Volumes 1–3. Build with `--year 1921`.

**Volume 5** (`Military-Writings-Trotsky-v5.pdf`): This is a PDF — likely a
scan or born-digital document. Approach:

1. Run `vorpal build --stop-after extract --end-page 30` and inspect `pages.jsonl`:
   - If `scan_type` is `digital`: born-digital, proceed directly to full build
   - If `scan_type` is `scanned`: check mean OCR confidence; if < 0.85, investigate
     before committing to a full build (potentially hundreds of synthesis hours lost
     to bad OCR)
2. If OCR quality is acceptable (mean confidence ≥ 0.85, flagged pages ≤ 10%),
   proceed to full build
3. Run `vorpal fidelity` using the PDF path (text-layer extraction vs workdir text)
4. If OCR quality is not acceptable: record findings in `docs/06-corpus.md`, file
   **H-019** (human OCR verdict), and stop — do not attempt full synthesis

For both volumes, file **H-017** (v4) and **H-018** (v5 if built): listening
spot-checks.

**Accept when:** Volume 4 builds and passes fidelity; Volume 5 is either
built and passes fidelity, or is honestly documented as blocked with OCR
evidence. H-017 filed; H-018 filed or noted as blocked. All five volume results
in `docs/06-corpus.md`.

---

## What has graduated out of "far future"

*(Updated 2026-06-09 — items that were "thought about, not planned" have
earned their place in the arcs above.)*

- **Parallel OCR / batched TTS** → Arc 4 (Phases 15–16). Done.
- **LLM-assisted OCR repair** → Arc 4 (Phase 17). Done.
- **Library / batch mode** → Arc 4 (Phase 18). Done.
- **Manifest as first-class artifact** → Arc 4 (Phase 19). Done.
- **Corpus hardening** → Arc 4 (Phase 20). Done.
- **OpenAI TTS live acceptance** → Arc 5 (Phase 21).
- **Tone with real instruction engine** → Arc 5 (Phase 22).
- **StyleTTS2 voice design** → Arc 5 (Phase 23, Phase 9b).
- **Dialogue-aware delivery** → Arc 5 (Phase 24).
- **Footnote narration** → Arc 5 (Phase 25).
- **Piper draft engine** → Arc 6 (Phase 26).
- **Loudness profiles** → Arc 6 (Phase 27).
- **Richer cover art / metadata** → Arc 6 (Phase 28).
- **Chapter summaries** → Arc 6 (Phase 29).
- **TUI / local web UI** → Arc 6 (Phase 30).
- **Multi-voice dramatization / theatrical mode** → Arc 7 (Phases 31–40).
- **Trotsky Military Writings production run + text fidelity QA tooling** → Arc 8 (Phases 41–45).

**Still explicitly out of scope:** voice cloning; DOCX/web input; GUI as a
*replacement* for the CLI (Phase 30 is additive); DRM circumvention.

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
