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
if you run dry. Arc 4 **opens by resolving the `cli` tone-backend auth** —
`claude -p` inside the container wanted a `/login` (HANDOFF-NOTES §1); if it
needs interactive login the agent can't do unsupervised, mark it `(human)` and
proceed. Order: 15 → 16 → 17 → 18 → 19 → 20.)*

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

## Far future (thought about, deliberately not planned)

- **A visual layer / exe.** Bottom of the priority list by decision
  (2026-06-07): we need a product before packaging. When its day comes, the
  UI-worthy moments are already CLI checkpoints — review-table editing, voice
  audition, tone-map inspection, build progress — which suggests a thin local
  web UI (or TUI) over the manifest, then perhaps a PyInstaller exe. Nothing
  in the architecture blocks this; nothing in it is being built now.

## Post-Arc-3 candidates (explicitly deferred)

In rough value order (most of the old post-Arc-2 list graduated into Arc 3):

1. **Performance** — parallel page OCR (process pool), batched TTS on GPU
   (matters more once API engines bill per request).
2. **LLM-assisted OCR repair** — optional scalpel pass over OCR-damaged
   passages, with the surrounding clean text as context; diff-shown,
   review-approved (deterministic core, model-assisted edges).
3. **Library / batch mode** — point at a directory, build a shelf overnight;
   queue + progress over the existing content-addressed cache.
4. **Manifest as a first-class artifact** — other renderers (clean EPUB, study
   guide) from the same cleaned `book.json`.

*(EPUB/TXT input graduated into Phase 5; ASR QA, pronunciation lexicon, and
draft-mode graduated into Arc 3, all on 2026-06-07. DOCX/web stay out.)*

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
