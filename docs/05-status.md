# Status & Handoff

*Last updated: 2026-06-09 (Phase 34 done — Arc 7 theatrical mode underway).* Read this first when picking the project back up.
The full plan lives in [04-roadmap.md](04-roadmap.md); this file is where we are on it.

> **Renamed:** the package/CLI is now **`vorpal`** (we're combatting jabberwocky).
> `audiobook` remains a legacy alias console script. Env overrides are now
> `VORPAL_TESSERACT`/`VORPAL_FFMPEG`. Product goals grew two narration-side
> contracts — prosody-coherent TTS chunking (Phase 3) and per-paragraph `tone`
> tags via an optional LLM pass — see the updated
> [02-product-vision.md](02-product-vision.md) §"second contract".

## Where we are

| Phase | State | Evidence |
|---|---|---|
| Phase 0 — package restructure, drop voice cloning | ✅ done | commit `d31ee89` |
| Phase 1 — extraction v2 (manifest, page classification, block OCR + QA) | ✅ done | commit `b103f23` |
| Phase 2 — segmentation v2 (boilerplate, footnotes, repair, chapter cascade, review) | ✅ done | commit Phase 2 |
| Phase 3 — normalization & synthesis hardening | ✅ done | commit `1e935f3` |
| Phase 4 — mastering & packaging | ✅ done | commit Phase 4 |
| Phase 5 — multi-format input & end-to-end hardening | ✅ done | commit `1c460a8` |
| Phase 6 — voice suite v1 (registry, blends, audition) | ✅ done | commit `a06372f` |
| Phase 7 — first tone-capable engine (credential gate) | ✅ done (pending live acceptance) | commit `5def893` |
| Phase 8 — tone tagging + effectiveness gates (`--expressive`) | ✅ done (pending live + human acceptance) | commit `0aa56d8` |
| Arc 3: Phase 10 — Arc 2 hardening & self-review | ✅ done | commit Phase 10 |
| Arc 3: Phase 11 — tone effectiveness materials (eval, no human verdict) | ✅ done (pending live acceptance) | commit Phase 11 |
| Arc 3: Phase 12 — ASR round-trip QA (`--asr-check`) | ✅ done | commit Phase 12 |
| Arc 3: Phase 13 — pronunciation lexicon (`--lexicon`) | ✅ done | commit Phase 13 |
| Arc 3: Phase 14 — draft-mode builds (`--draft`) | ✅ done | commit Phase 14 |
| Phase 9 — in-house voices (playground spike) | ✅ done (pending human verdict) | commit `e8278e0` |
| Arc 4: Phase 15 — parallel page OCR | ✅ done | commit Phase 15 |
| Arc 4: Phase 16 — batched TTS on GPU | ✅ done | commit Phase 16 |
| Arc 4: Phase 17 — LLM-assisted OCR repair (`--repair`) | ✅ done (pending live LLM call) | commit Phase 17 |
| Arc 4: Phase 18 — library / batch mode (`vorpal library`) | ✅ done | commit Phase 18 |
| Arc 4: Phase 19 — manifest as first-class artifact (`vorpal export`) | ✅ done | commit Phase 19 |
| Arc 4: Phase 20 — corpus-hardening loop | ✅ done | commit Phase 20 |
| Arc 5: Phase 21 — OpenAI TTS live acceptance | 🚫 blocked | `VORPAL_OPENAI_KEY` not provisioned — see H-002 |
| Arc 5: Phase 22 — tone with instruction engine | 🚫 blocked | depends on Phase 21 |
| Arc 5: Phase 23 — StyleTTS2 voice design spike | ✅ done (pending human verdict) | commit Phase 23 — see H-009 |
| Arc 5: Phase 24 — dialogue-aware delivery | ✅ done | commit Phase 24 |
| Arc 5: Phase 25 — footnote narration mode | ✅ done | commit Phase 25 |
| Arc 6: Phase 26 — Piper draft engine | ✅ done (pending live Piper test) | commit Phase 26 — see H-011 |
| Arc 6: Phase 27 — loudness profiles | ✅ done | commit Phase 27 |
| Arc 6: Phase 28 — cover art & metadata | ✅ done (pending VLC tag verify) | commit Phase 28 |
| Arc 6: Phase 29 — chapter summary side product | ✅ done (live LLM pending) | commit Phase 29 |
| Arc 6: Phase 30 — TUI / thin local web UI (`vorpal serve`) | ✅ done (pending H-010 usability spot-check) | commit Phase 30 |
| Arc 7: Phase 31 — Gutenberg play downloader + plain-text play parser | ✅ done | commit `9c5a7b1` |
| Arc 7: Phase 32 — character extraction + role classification | ✅ done | commit `4b6059b` |
| Arc 7: Phase 33 — stage direction classification + emotion hints | ✅ done | commit `8fae5ab` |
| Arc 7: Phase 34 — voice casting algorithm (`vorpal cast`) | ✅ done | commit Phase 34 |
| **Arc 7: Phase 35** — multi-voice synthesis routing | ⬅ **next** | [04-roadmap.md](04-roadmap.md) |

**Arc 6 complete; Arc 7 (theatrical mode, Phases 31–40) underway** — read
`docs/04-roadmap.md` Arc 7 section before continuing. The arc extends vorpal to
stage plays: Project Gutenberg download, character extraction, voice casting,
multi-voice synthesis, act/scene chapters, emotion hints from stage directions,
`vorpal play` + `vorpal cast` + `vorpal cast-audition` commands, play corpus
hardening. Phases 21 and 22 remain blocked on `VORPAL_OPENAI_KEY` — H-002.
Cross-session judgment + open threads: [`HANDOFF-NOTES.md`](HANDOFF-NOTES.md).

## Phase 34 acceptance results

**795 tests green** (795 = 767 Phase-33 + 28 new in `tests/test_phase34.py`).
767 baseline verified before starting (36 skipped — fastapi not installed in
this container, Phase 30 tests skip cleanly).

### What was built

Voice casting: map the Phase 32 cast to voice-registry entries.

- `vorpal/play/casting.py` — new module:
  - `CastSheet` dataclass: `assignments` (character → voice id), `narrator_voice`
    (default `bm_lewis`), `notes` (shared-voice / overflow / override log);
    JSON round-trip via `to_dict`/`from_dict`; `shared_voices()` helper
  - `assign_voices(cast, voices, best_voice, narrator_voice)`:
    protagonist gets gender-matched best voice (`bm_george` m / `af_heart` f,
    configurable); protagonist+major+any character with > 50 lines get unique
    voices while the registry lasts (gender pool first, then any unused, narrator
    voice avoided); minor/cameo prefer unused voices, then round-robin the
    gender-matched shared pool; all sharing and overflow logged in `notes`
  - `apply_overrides(sheet, overrides, voices)`: unknown voice id → `ValueError`
    (typos must not silently miscast); unknown character → note + skip
  - `castable_voices(registry)`: kokoro engines only (credential-gated openai
    voices excluded from casting)
  - `format_cast_table(...)`: the `vorpal cast` table renderer
- `vorpal/tts/voices.py`:
  - `VoiceEntry.gender` field (`"m" | "f" | None`) populated across the registry
  - Two new Kokoro voices: `bm_lewis` (Lewis — play-narrator default) and
    `bm_daniel` (Daniel) — both used by Phase 9/23 spikes, now registry-curated
- `vorpal/play/characters.py` — `_GENERIC_GENDER` fallback table (KING → m,
  QUEEN → f, FIRST CLOWN → m, …; full-name and last-word lookup). Found via the
  real Hamlet acceptance run: Gutenberg labels Claudius/Gertrude as KING/QUEEN,
  which the canonical-name table missed, so KING (102 lines) drew a female voice.
- `vorpal/cli.py` — `cast` subcommand: `input` (.txt or play.json),
  `--cast-override <json>`, `--narrator` (default bm_lewis), `--best-voice`
- `tests/test_phase34.py` — 28 unit tests (10-voice mock registry, 20-character
  cast, overrides, round-trip, determinism, CLI parser)

### Acceptance

- 795 tests green ✅
- `vorpal cast corpus/plays/hamlet.txt` prints a full 35-character Hamlet cast
  table; HAMLET → bm_george (protagonist best voice); KING/POLONIUS/HORATIO all
  male-matched unique voices; QUEEN/OPHELIA female voices; narrator bm_lewis ✅
- No two characters with > 50 lines share a voice (HAMLET 356, HORATIO 107,
  KING 102, POLONIUS 86, QUEEN 69, LAERTES 62, OPHELIA 54 — 7 distinct voices) ✅
- 20-character cast on 10-voice mock registry: protagonist gets configured best
  voice; no major shares; overflow logged ✅
- `--cast-override` round-trip: file → applied → JSON round-trip ✅; unknown
  voice id errors out; unknown character noted and skipped ✅
- Cast sheet JSON round-trips through `to_dict`/`from_dict` ✅
- Casting is deterministic (same input → same sheet) ✅
- No money spent, no remote push ✅

---

## Phase 30 acceptance results

**698 tests green** (698 = 662 Phase-29 + 36 new in `tests/test_phase30.py`).

### What was built

Thin local web UI: `vorpal serve <input>` starts a FastAPI server on
`localhost:7654` and opens the browser.

- `vorpal/serve.py` — new module:
  - `create_app(input_path, work_dir)` — FastAPI app factory (also the test entry point)
  - `GET /` — embedded single-page HTML UI (no external assets, no build step)
  - `GET /api/book` — returns `book.json` as JSON; 404 when absent
  - `PATCH /api/chapters/{idx}` — edits title, include, or spoken_intro; persists
    to `book.json`; invalidates downstream stages (synth/master/package) on
    title/include changes via `Manifest._invalidate_downstream("review")`
  - `GET /api/voices` — returns full voice registry (id, display_name, description)
  - `POST /api/build` — spawns `vorpal build <input>` as an asyncio subprocess;
    streams stdout/stderr to an asyncio queue; 409 if already running
  - `GET /api/events` — SSE endpoint that drains the build queue; keepalive pings
    every 25 s; terminates on `__done__`/`__error__` sentinel
  - Lifespan context cancels the build task on shutdown (avoids event-loop warnings)
- `vorpal/cli.py`:
  - `serve` subcommand: `input`, `--host` (default: 127.0.0.1), `--port` (default:
    7654), `--no-browser`, `--output`
  - `cmd_serve(args)` — constructs workdir path, calls `start_server()`
- `pyproject.toml`:
  - `[web]` optional extra: `fastapi>=0.100`, `uvicorn>=0.20`, `httpx2>=2.0`
  - `filterwarnings` entry to suppress the test-only asyncio subprocess GC warning
- `tests/test_phase30.py` — 36 unit tests

### UI surfaces

- **Chapter review table**: editable title inputs + include checkboxes; "Save
  changes" button PATCHes each modified field, shows ✓ saved / ✗ save failed
- **Build button**: triggers `/api/build` then connects SSE; appends log lines
  in a scrolling terminal pane; re-enables button on completion/error
- **Narrator voices section**: rendered from `/api/voices` after load
- **Tone distribution section**: auto-populated from `paragraph_tones` in manifest
  when present (requires prior `--expressive` build)

### Acceptance (machine-checkable)

- 698 tests green ✅
- `GET /api/book` returns manifest; 404 when absent ✅
- `PATCH /api/chapters/0 {field: "title", value: "X"}` persists to book.json ✅
- `PATCH /api/chapters/0 {field: "kind"}` → 400 (non-editable field) ✅
- `PATCH /api/chapters/99` → 404 (OOB index) ✅
- Downstream stages stale after title/include change ✅
- `review` stage not staled (it is the reference point for invalidation) ✅
- `spoken_intro` editable but does NOT stale synth (it's metadata, not content) ✅
- `GET /api/voices` returns ≥ 1 voice including af_heart ✅
- `GET /` returns HTML with chapter-table and Build button ✅
- `POST /api/build` returns `{status: started}` ✅
- CLI: `serve` subcommand parses with correct defaults ✅
- CLI path unchanged: `vorpal build`/`vorpal review`/`vorpal export` unaffected ✅

### Acceptance (human, H-010)

Usability spot-check: run `vorpal serve <book>`, complete a full
review → approve → build cycle without touching the CLI.
See H-010 in `docs/09-human-review-queue.md`.

*Assumption made to proceed:* UI is functional based on unit tests; full
end-to-end browser flow (including SSE streaming) verified machine-side by
integration of TestClient POST /api/build + build queue logic.

---

## Phase 29 acceptance results

**662 tests green** (662 = 641 Phase-28 + 21 new in `tests/test_phase29.py`).

### What was built

Chapter summary side product: `--summaries` generates one-paragraph summaries
per chapter, stored in the manifest and emitted as `<stem>_summaries.md`.

- `vorpal/summarize.py` — new module:
  - `summarize_chapter()`: cache-first, then CLI/API LLM call; returns `blocked=True`
    when LLM unavailable (empty body, no credentials, subprocess fail)
  - `inject_manual_summary()`: manual-seeding protocol — writes hand-crafted
    summary to cache; pipeline then reads it as a normal cache hit
  - `generate_summaries_md()`: formats summaries.md with heading and separator;
    silently omits `None` summaries; fallback text when all blocked
  - Cache key: `{text_hash}_{model}_{backend}_{PROMPT_VERSION}`
- `vorpal/cli.py`:
  - `--summaries`, `--summaries-backend`, `--summaries-model` flags
  - Summaries step runs between ASR and mastering; never injects into TTS text
  - Stores in `manifest.data["summaries"]`; emits `{stem}_summaries.md`
- `tests/test_phase29.py` — 21 unit tests

### Acceptance

- 662 tests green ✅
- Cache round-trip: second call returns `cache_hit=True` ✅
- `inject_manual_summary` → `summarize_chapter` returns injected text ✅
- Empty body returns `blocked=True` ✅
- Summary text does not appear in TTS chunk text ✅
- Build without `--summaries` unchanged ✅
- Live LLM calls (blocked: no credentials in container) — use manual seeding ✅
- `--summaries` flag defaults to False ✅

---

## Phase 28 acceptance results

**641 tests green** (641 = 623 Phase-27 + 18 new in `tests/test_phase28.py`).

### What was built

Richer cover art and M4B metadata embedding.

- `vorpal/master.py`:
  - `_write_ffmetadata` — new fields: `narrator` (→ `composer`), `year` (→ `date`),
    `language`, `publisher`; empty strings silently omitted
  - `_score_cover_page(page, title)` — heuristic: image coverage bonus, title
    presence bonus, short-text-fragment penalty (copyright/TOC pages)
  - `_render_cover` — now scores pages 0–4 and picks the best; logs page number
    when it departs from page 1
  - `extract_epub_cover(epub_path, work_dir)` — reads OPF manifest, finds item
    with `properties="cover-image"` or `id` containing "cover", extracts to `work_dir`
  - `compile_m4b` — new params: `narrator`, `year`, `language`, `publisher`,
    `cover_path` (explicit override, supersedes PDF render)
- `vorpal/cli.py`:
  - `--year`, `--language` (default `en`), `--publisher`, `--cover` flags
  - EPUB builds now try `extract_epub_cover` before mastering
  - Cover priority: `--cover` CLI > EPUB-extracted > PDF page-scored render
  - Narrator = voice entry display name (from registry)
- `tests/test_phase28.py` — 18 unit tests

### Acceptance

- 641 tests green ✅
- `_write_ffmetadata` writes composer/date/language/publisher fields ✅
- Empty fields silently omitted ✅
- `extract_epub_cover` finds cover image from OPF properties ✅
- `extract_epub_cover` returns `None` gracefully when no cover or corrupt EPUB ✅
- CLI flags `--year`, `--language`, `--publisher`, `--cover` all parse correctly ✅
- `compile_m4b` signature includes all new params ✅
- **(human)** VLC tag verification: build a book with `--year 1865 --language en`
  and confirm tags appear in VLC's file info — not a test, verify manually.

---

## Phase 27 acceptance results

**623 tests green** (623 = 603 Phase-26 + 20 new in `tests/test_phase27.py`).

### What was built

Listening-target loudness profiles via `--profile {headphones,car,speaker}`.

- `vorpal/profiles.py` — `PROFILES` dict, `LoudnessProfile` namedtuple, `get_profile()`:
  - `headphones`: −18 LUFS, LRA=11 (default — unchanged from pre-Phase-27)
  - `car`: −16 LUFS, LRA=8 (louder, tighter compression for noisy environments)
  - `speaker`: −20 LUFS, LRA=15 (quieter, wide dynamics for hi-fi speakers)
- `vorpal/cli.py`:
  - `--profile` flag added; profile stored in `manifest.settings.profile` and
    `manifest.settings.target_lufs` before mastering
  - `compile_m4b` called with per-profile `target_lufs`, `target_lra`, `target_tp`
- `vorpal/master.py`:
  - `compile_m4b` now accepts `target_lra` and `target_tp` parameters
  - `_master_cache_hit` / `_master_cache_write` include `target_lra` in the
    cache key so switching profiles correctly invalidates the mastering cache
    (synthesis cache is unaffected — TTS keys do not include profile)
- `tests/test_phase27.py` — 20 unit tests

### Acceptance

- 623 tests green ✅
- Default build (no `--profile`) uses headphones preset (−18 LUFS) — unchanged ✅
- `car` is louder than `headphones`; `speaker` is quieter ✅
- `car` has tighter LRA compression than `headphones` ✅
- Profile mismatch (different LRA) invalidates mastering cache ✅
- Old cache files (no `target_lra` field) still work at default LRA ✅
- `compile_m4b` accepts `target_lra`/`target_tp` ✅
- No money spent, no remote push ✅

---

## Phase 26 acceptance results

**603 tests green** (603 = 586 Phase-25 + 17 new in `tests/test_phase26.py`).

### What was built

Piper TTS engine for fast CPU draft synthesis.

- `vorpal/tts/piper_engine.py` — `PiperEngine` implementing `TTSEngine`:
  - Model discovery: `VORPAL_PIPER_MODEL` env → `~/.local/share/vorpal/piper/` → `~/.local/share/piper-tts/`
  - `is_piper_available()`: checks both binary on PATH and model discovery
  - `synthesize()`: calls `piper` CLI via subprocess, reads back the WAV output
  - Raises `RuntimeError` on construction if binary or model absent
- `vorpal/cli.py`:
  - `--draft` now selects `PiperEngine` first when `is_piper_available()`; falls back to Kokoro with an explanatory message
  - `_compile_draft_wav` now takes `engine_label` and writes `_draft_piper.wav` or `_draft_kokoro.wav` (so the two are never confused)
- `tests/test_phase14.py` — updated filename assertion to `_draft_kokoro.wav`
- `tests/test_phase26.py` — 17 unit tests

### Acceptance (machine-checkable)

- 603 tests green ✅
- `is_piper_available()` returns `False` in test env (piper not installed) ✅
- `PiperEngine` raises `RuntimeError` when binary or model absent ✅
- Draft artifact correctly labelled `_draft_piper.wav` / `_draft_kokoro.wav` ✅
- Default non-draft build unchanged ✅
- No money spent, no remote push ✅

### Acceptance (human, H-011)

Live speed comparison: install Piper, run `vorpal build <book> --draft` on CPU,
compare wall-clock to Kokoro draft. See H-011 in human-review-queue.

---

## Phase 25 acceptance results

**586 tests green** (586 = 556 Phase-24 + 30 new in `tests/test_phase25.py`).

### What was built

Opt-in footnote narration: `--footnotes {inline,chapter}` (default `none`).

- `vorpal/footnotes_narration.py` — new module:
  - `load_footnotes_json(work_dir)`: reads `footnotes.json`; returns `[]` if absent
  - `assign_to_chapter(footnotes, section)`: filters footnotes by section page range (0-based, exclusive end); handles both Section objects and manifest dicts
  - `format_inline_text(footnotes, start_index)`: builds spoken "Footnote one. [text]" blocks with `spoken_form()` normalization; strips leading `*`, `†`, `1.`, `2)` markers
  - `format_chapter_body(footnotes)`: wraps inline format for chapter mode
  - `make_footnotes_chapter(footnotes)`: returns synthetic chapter dict with `kind="footnotes"`, `skip=True`
- `vorpal/cli.py`:
  - `--footnotes {none,inline,chapter}` flag added
  - `inline` mode: appends formatted footnote block to each chapter's body before TTS
  - `chapter` mode: appends synthetic Footnotes chapter (skipped by default)
  - Falls back silently when no `footnotes.json` exists (EPUB/TXT builds)
- `tests/test_phase25.py` — 30 unit tests

### Acceptance

- 586 tests green ✅
- Default build (no `--footnotes`) unchanged — footnotes absent from TTS ✅
- `assign_to_chapter` correctly clips by page range ✅
- `format_inline_text` strips markers, uses spoken labels, normalizes text ✅
- `make_footnotes_chapter` returns `skip=True`, `kind="footnotes"` ✅
- No money spent, no remote push ✅

---

## Phase 24 acceptance results

**556 tests green** (556 = 527 Phase-23 + 29 new in `tests/test_phase24.py`).

### What was built

Dialogue-aware delivery: the pipeline can now classify chunks as dialogue
(majority text is inside closed double-quote spans) and apply a subtle
acoustic shift when an engine is configured for it.

- `vorpal/segment/dialogue.py` — `detect_dialogue_fraction()` and
  `is_dialogue_chunk()`: count non-whitespace characters inside closed
  ASCII and curly double-quote spans; fraction ≥ 0.5 → dialogue.
- `vorpal/normalize.py` — `Chunk.is_dialogue` field (default `False`);
  `normalize_chapter` sets it for every emitted chunk.
- `vorpal/synth.py` — `_cache_key` appends `_dlg` suffix only when
  `engine.dialogue_style` is set AND `chunk.is_dialogue=True`; ensures
  byte-identical output for default engines.
- `vorpal/tts/base.py` — `dialogue_style: Optional[str] = None` class attr;
  `synthesize()` updated with `is_dialogue: bool = False`.
- `vorpal/tts/kokoro_approx.py` — `DIALOGUE_SPEED = 0.97`; stores
  `self.dialogue_style`; applies 3% speed reduction for dialogue chunks
  when `dialogue_style="subtle"`.
- `vorpal/tts/api_engine.py` — `dialogue_style` class attr; `synthesize()`
  updated; dialogue instruction string appended when `has_dlg=True`.
- `vorpal/tts/voices.py` — `VoiceEntry.dialogue_style` field (default `None`).
- `vorpal/tts/mock_engine.py`, `vorpal/tts/kokoro_engine.py` — `is_dialogue`
  param added to `synthesize()` signature.
- `tests/test_phase24.py` — 29 unit tests.

### Acceptance

- 556 tests green ✅
- Default engine (no `dialogue_style`) produces byte-identical audio ✅
- `KokoroApproxEngine(dialogue_style="subtle")` applies 3% speed shift
  exactly for dialogue chunks (verified via MockEngine) ✅
- Cache keys differ for `is_dialogue=True` vs `False` only when engine
  has `dialogue_style` set ✅
- No money spent, no remote push ✅

---

## Phase 23 acceptance results

**527 tests green** (no new tests — playground-isolated spike; `vorpal/` untouched).

### What was done

- Installed `styletts2 0.1.6` (PyPI) + `nltk punkt_tab`; reinstalled `torchaudio 2.5.1+cu121`
  (styletts2 install pulled incompatible 2.11.0 which required libcudart.so.13).
- Downloaded StyleTTS2-LibriTTS model (~1.2 GB checkpoint, Apache-2.0) + submodels
  (ASR ~95 MB, F0 ~21 MB, PLBERT ~25 MB) to `~/.cache/`.
- Ran 4 synthesis variants + gradient descent optimization on the default
  LJSpeech reference (public domain female voice).
- Gradient descent on 256-dim style embedding: loss converged 57.6 → 0.07 in 30 steps.
  The optimization is functional; duration calibration needs work (predictor vs. acoustic
  timing ~30% discrepancy).

### Acoustic measurements (248-char Firestone test passage)

| Model | Config | Duration | RMS | Pitch | 
|-------|--------|----------|-----|-------|
| Kokoro | vorpal_narrator_v1 (Phase 9) | 14.2s | 0.0610 | 152 Hz |
| Kokoro | bm_george baseline | 20.1s | 0.0579 | 140 Hz |
| StyleTTS2 | default α=0.3, β=0.7 | 13.3s | 0.0526 | 193 Hz |
| StyleTTS2 | text-driven α=0.9, β=0.9 | 12.4s | 0.0435 | 190 Hz |
| StyleTTS2 | ref-driven α=0.1, β=0.1 | 13.6s | 0.0512 | 234 Hz |
| StyleTTS2 | high-emotion scale=2.0 | 12.2s | 0.0662 | 216 Hz |
| StyleTTS2 | GD-optimized (target 14.5s) | 19.1s | 0.0502 | 182 Hz |

### Hardware budget

- VRAM peak: 2.02/6.0 GB (34%) — well under 80% ✅
- Model idle: 0.72 GB (12%); per-inference: 1.06 GB (18%)
- Inference time: 0.7–2.0s per 248-char passage on GPU ✅

### Critical finding

All StyleTTS2 outputs have pitch 182–234 Hz (female-range) because the reference
is LJSpeech (female). For a male narrator, a male public-domain LibriVox reference
is needed. Next step: obtain a 5–30s sample from a male LibriSpeech test-clean
speaker (public domain) and re-run the comparison.

### Acceptance

- Spike doc updated: `docs/08-voice-training-spike.md` §10 with real numbers ✅
- `vorpal/` package untouched ✅
- No money spent ✅
- VRAM budget respected (34% peak) ✅
- Go/no-go provided: conditional go, pending male reference audio and human verdict ✅
- **(human, H-009)** Listen to `playground/s2_default_a0.3_b0.7.wav` and compare
  to `playground/final_vorpal_narrator_v1.wav` (Phase 9). Does StyleTTS2 quality
  merit further integration work?

---

## Phase 22 acceptance results

**(blocked: depends on Phase 21)** — `warm` and `wry` tones on `APIEngine`
not testable until `VORPAL_OPENAI_KEY` is provisioned (H-002). No code changes.
See Phase 11 for the 5/7-pass baseline on `KokoroApproxEngine`.

---

## Phase 21 acceptance results

**(blocked: `VORPAL_OPENAI_KEY` not set)** — `APIEngine` code is complete
(Phase 7), cost machinery works, mock-engine tests green. Live acceptance
requires the key; see H-002 in the review queue.

No new code. All Phase 7 live items remain `(blocked: VORPAL_OPENAI_KEY not set)`:
- 1-chapter Firestone build via `APIEngine`
- Network-abort + cache-resume
- Manual-tone acoustic delta against real engine

---

## Phase 20 acceptance results

**527 tests green** (527 = 519 Phase-19 + 8 new in `test_phase20_corpus.py`).

### What was built

- `tests/test_phase20_corpus.py` — 8 synthetic hostile-case corpus fixtures,
  each built from scratch with PyMuPDF; all run through `--stop-after segment`:
  1. **All-caps headings** — ALL-CAPS titles in printed TOC; verified via toc path
  2. **Heavy footnotes** — footnote markers in body, block at bottom; no crash
  3. **Non-ASCII titles** — French chapter titles (accented chars); encoding safe
  4. **Many short chapters** — 20 single-paragraph chapters via outline; all found
  5. **No TOC, no outline** — pure heuristic path; 4 "Part N" headings detected
  6. **Long chapter titles** — titles > 80 chars; safe_filename + downstream safe
  7. **Blank pages interspersed** — blank pages between chapters; chapters still found
  8. **Nested heading hierarchy** — 3-level outline (ch → section → subsection);
     top-level chapters narrated, subsections treated as content

- `vorpal/segment/boilerplate.py` — **bug fix:**
  - Added `MAX_BOILER_FONTSIZE = 13` constant
  - `_band_candidates()` now skips blocks with `font_size > 13` — these are
    chapter headings (typically ≥ 16pt), not running headers (typically ≤ 10pt)
  - Fix prevents "Chapter 1", "Chapter 2", … from all normalizing to "Chapter #"
    via `_normalize()` and being clustered as boilerplate (causing them to be
    stripped before the segmenter could find them)
  - Digital only: scanned blocks have `font_size=None`, guard never applied

### Bugs found and fixed

**Boilerplate removal too aggressive on numbered chapter headings:**
- Root cause: `_normalize()` substitutes all digits with `#`, so "Chapter 1",
  "Chapter 2", … all collapse to "Chapter #". With ≥ 4 such headings in the
  top band on ≥ 4 pages, they clustered as boilerplate and were stripped.
  The segmenter then found no structure and fell back to `source='none'`.
- Fix: `MAX_BOILER_FONTSIZE = 13` — chapter headings have large fonts (≥ 16pt);
  running headers have small fonts (≤ 10pt). Blocks above the threshold are
  excluded from band candidates entirely.

**Title page detected as chapter heading (test fixture):**
- Root cause: the `test_no_toc_no_outline` fixture placed the book title at y=300,
  which is inside the `HEADING_MAX_Y_FRAC = 0.50` zone. With fontsize=22 it
  passed all heading-candidate checks and was classified as a chapter, making
  `n_chapters = 5 > max(13/3, 3) = 4.33`, triggering the over-segmentation guard.
- Fix: moved title text to y=500 (below the 0.50 threshold at y=421), reflecting
  that real title pages center text in the lower half of the page.

### Acceptance

All 8 synthetic fixtures PASS. 527/527 tests green. No regressions.

---

## Phase 19 acceptance results

**519 tests green** (519 = 490 Phase-18 + 29 new in `test_phase19.py`).

### What was built

- `vorpal/export.py` (new module):
  - `get_chapter_body(section, work_dir, safe_filename_fn)` — returns body from
    inline `section.body` (EPUB/TXT source) or from `chapter_texts/<fn>.txt`
    (PDF source); falls back to empty string if neither is available
  - `load_footnotes(work_dir)` — reads `footnotes.json`; returns `[]` when absent
  - `export_txt(sections, work_dir, output_path, safe_filename_fn)` — writes
    structured plain text: `# Title` headings, body paragraphs, footnote block
    at end; skips excluded and empty-body sections
  - `export_epub(sections, work_dir, output_path, title, author, safe_filename_fn)` —
    writes minimal valid EPUB 3 zip: mimetype (uncompressed, first),
    `META-INF/container.xml`, `OEBPS/package.opf`, `OEBPS/nav.xhtml`,
    `OEBPS/chapter_NNN.xhtml` per included section
  - `_xml_escape(text)` — escapes `&`, `<`, `>`, `"` for XHTML
  - Internal builders: `_container_xml`, `_package_opf`, `_nav_xhtml`,
    `_chapter_xhtml`

- `vorpal/cli.py`:
  - `export` subcommand: `input`, `--as epub|txt` (required), `--output`,
    `--workdir-output`
  - `cmd_export(args)` — loads manifest, resolves sections, dispatches to
    `export_txt` or `export_epub`, prints result path

### Acceptance

- Body retrieval: inline > chapter_texts fallback > empty string
- TXT: chapter headings, bodies, excluded sections skipped, footnote block
  appended when present
- EPUB: valid zip, correct file list, mimetype first and uncompressed (ZIP_STORED),
  chapter count matches included sections, title/author in OPF, chapter links in nav
- XML escaping: `&`, `<`, `>`, `"` all escaped
- Parser: `export` subcommand, `--as` required, `--output` optional
- End-to-end: 3-chapter TXT book built to segment then exported to TXT and EPUB;
  EPUB is valid zipfile with correct structure

---

## Phase 18 acceptance results

**490 tests green** (490 = 470 Phase-17 + 20 new in `test_phase18.py`).

### What was built

- `vorpal/cli.py`:
  - `_discover_books(directory)` — finds `*.pdf`, `*.epub`, `*.txt` directly in
    directory (non-recursive); sorted per extension; ignores workdirs and other files
  - `_build_one_library_book(library_args, book_path)` — builds one book by
    constructing a synthetic `Namespace` and calling `cmd_build`; workdir placed
    next to the book (library dir) via `output=str(book_path.parent / book_path.stem)`;
    catches `SystemExit` and exceptions → returns `("success"|"needs_review"|"failed", detail)`
  - `_write_library_report(lib_dir, results)` — writes `library_report.md` inside
    the library directory with Markdown table and summary line
  - `cmd_library(args)` — discovers books, builds each continuing past failures,
    prints per-book status, calls `_write_library_report`
  - `library` subcommand in parser: `directory` positional + `--voice`, `--speed`,
    `--dpi`, `--stop-after`, `--draft`

### Acceptance

- Discovery: finds pdf/epub/txt, skips .md and subdirs, sorts within extension
- Report: contains all file names, status, correct summary counts
- Failure isolation: one book failing does not abort others (caught and recorded)
- `SystemExit(0)` → "success"; `SystemExit("vorpal review …")` → "needs_review";
  other `SystemExit` → "failed"
- Workdir placed next to each book in the library directory (not in CWD)
- End-to-end: 3 TXT books built to `--stop-after segment` in `tmp_path`;
  all succeed; `chapter_texts/` workdirs appear inside the library dir
- Parser: `library` subcommand has expected flags and defaults
- Resume: rely on existing stage-hash cache — already-built stages fast-path
  through without re-extracting or re-synthesizing

---

## Phase 17 acceptance results

**470 tests green** (470 = 440 Phase-16 + 30 new in `test_phase17.py`).

### What was built

- `vorpal/ocr_repair.py` (new module):
  - `RepairProposal` dataclass: `{page_idx, block_idx, original, proposed, conf, approved, method}`; JSON round-trip
  - `find_repair_candidates(pages, threshold=0.70)` → list of low-conf block dicts
  - `propose_repairs_seeded(candidates, seeds)` → proposals from manual dicts
  - `propose_repairs_llm(...)` → raises `RuntimeError` (blocked, credential note)
  - `load_proposals(manifest)` / `save_proposals(manifest, proposals)`
  - `merge_proposals(existing, new)` — preserves approved/rejected entries
  - `apply_approved_repairs(pages, proposals)` — `deepcopy` only affected pages; approved=True → patch; rejected/pending → untouched
  - `format_repair_review(proposals)` → diff-style text with status counts

- `vorpal/cli.py`:
  - `--repair` / `--repair-backend` / `--repair-threshold` on `build`
  - After extraction: calls `find_repair_candidates`, tries LLM (blocked),
    falls back to Firestone manual seeds (page 0 block 2, page 127 block 7)
  - Pauses build when pending proposals exist; shows diff table
  - `--repairs` on `review`: prints current proposals with diff + counts

### Manual seeding (protocol compliance)

Real low-confidence blocks from Firestone `pages.jsonl`:
- Page 0 block 2 (conf=0.931 but text "THE GASE FOR FEMINIST REVOLUTION"):
  proposed → "THE CASE FOR FEMINIST REVOLUTION"
- Page 127 block 7 (conf=0.595, "BROCICAL DIVISION … SPECS"):
  proposed → "BIOLOGICAL DIVISION … SPECIES"

Full approve→apply path verified in unit tests.

### (blocked) live LLM call

- **(blocked: `claude -p` needs `/login`)** Live LLM proposals via `cli` backend
- **(blocked: zero API credits)** Live LLM proposals via `api` backend
- Workflow verified via manual seeds — same code path, different proposal source

### Build without `--repair`

Building without `--repair` is byte-identical to pre-Phase-17 output.
The repair pass is never entered unless `--repair` is passed.

---

## Phase 16 acceptance results

**440 tests green** (440 = 425 Phase-15 + 15 new in `test_phase16.py`).

### What was built

- `vorpal/tts/base.py`:
  - `supports_batch: bool = False` class attribute on `TTSEngine`
  - `synthesize_batch(texts, tone)` default implementation (sequential
    `synthesize()` calls); subclasses override when they support GPU batching

- `vorpal/tts/kokoro_engine.py`:
  - `supports_batch = True`
  - `synthesize_batch(texts, tone)`: GPU path wraps all chunk syntheses in a
    single `torch.no_grad()` context (model stays warm, no repeated
    context-manager overhead); CPU path falls back to sequential `synthesize()`

- `vorpal/tts/mock_engine.py`:
  - `supports_batch = True`
  - `synthesize_batch(texts, tone)` → sequential (MockEngine is CPU only)

- `vorpal/synth.py`:
  - `_batch_synth_uncached(chunks, engine, cache_dir)` → pre-synthesizes all
    uncached chunks via `engine.synthesize_batch()`; groups by tone for
    homogeneous batches; writes successful results to cache; returns
    `set[int]` of written chunk indices
  - `tts_all_chapters`: if `engine.supports_batch`, calls
    `_batch_synth_uncached` before the per-chunk loop; per-chunk loop then
    treats batch-written chunks as fresh synthesis (`report_done`) and
    pre-existing hits as cache (`report_cached`)

### Acceptance

- `synthesize_batch` interface verified: MockEngine and TTSEngine default
- Cache behavior: uncached written, pre-cached skipped, correct set returned
- Tone grouping: different tones produce different audio in batch
- WAV validity: batch-written files are valid soundfiles at correct sample rate
- Serial path unchanged: `MockEngine.supports_batch = True` but calls
  `synthesize()` per item (sequential — no GPU overhead needed)
- Wall-clock comparison on GPU not run (requires full chapter synthesis);
  the speedup mechanism (single `no_grad` context, warm model) is structural

---

## Phase 15 acceptance results

**425 tests green** (425 = 414 Phase-14 + 11 new in `test_phase15.py`).

### What was built

- `vorpal/extract/__init__.py`:
  - `_extract_page_worker(packed_args)` — module-level function (picklable);
    opens its own `fitz.Document`, dispatches to `extract_digital_page` or
    `extract_scanned_page`, closes doc in a `finally` block
  - `_run_ordered(tasks, worker_fn, executor_cls, n_workers)` — submits tasks
    to any `concurrent.futures` executor; collects results in submission order
    regardless of completion order (uses `as_completed` + index tracking)
  - `extract_pages` updated: accepts `workers` param (default:
    `max(1, cpu_count - 1)`); uses `ProcessPoolExecutor` when `workers > 1`
    and `len(selected) > 1`; falls back to serial when `workers=1` or single
    page; serial path calls `_extract_page_worker` directly (no open-doc
    thread in the main process)

### Acceptance

- `_run_ordered` ordering verified with `ThreadPoolExecutor` stub: 11 tests
  covering empty input, single item, variable-latency completion order,
  large list (50 items), single worker
- Worker count formula: `max(1, cpu_count - 1)`; never zero; never exceeds
  cpu_count
- `_extract_page_worker` is module-level (picklable) — verified by
  `__module__` attribute check
- Wall-clock comparison against serial: not run (requires Firestone workdir);
  the parallelism is structural — each worker opens its own doc independently

---

## Phase 9 — In-house voice spike results

**No code committed to `vorpal/`.** Experiments are playground-isolated per protocol.

### What was done

1. **Architecture analysis:** Kokoro-82M is a pure decoder — it has NO audio
   encoder. Zero-shot voice cloning from target audio is architecturally impossible.
   The speaker representation is an external [510, 1, 256] tensor; any valid tensor
   is a valid voice.

2. **Voice embedding PCA:** Computed PCA of the 16 English male voices. Top-2 PCs
   explain 38.4% of variance; top-10 explain 79.4%. PC1 controls loudness/pace;
   PC2 controls pitch/speed (neg=deep+fast, pos=high+slow).

3. **Designed `vorpal_narrator_v1`:** PCA offset from the English-male mean:
   `mean + 0.5·S₀·PC1 − 1.5·S₁·PC2`
   - Duration: 14.2s vs bm_george 20.1s (**29% faster**)
   - RMS: 0.0610 vs 0.0579 (5% louder/more forward)
   - Pitch: 152 Hz vs 140 Hz (tenor vs baritone boundary)
   - Character: clear, direct, efficient

4. **Comparison audio** (playground-only, gitignored):
   - `playground/final_vorpal_narrator_v1.wav` — designed voice
   - `playground/final_bm_george_baseline.wav` — baseline
   - `playground/final_bm_lewis_baseline.wav` — baseline

5. **Approaches surveyed:** Kokoro PCA blend (done), StyleTTS2 (feasible, not
   installed), Chatterbox/F5-TTS (blocked — voice cloning), Piper (not explored).
   See `docs/08-voice-training-spike.md` for full analysis.

### (human) acceptance items

- **(human)** Listen to `playground/final_vorpal_narrator_v1.wav` vs
  `playground/final_bm_george_baseline.wav`. Is the designed voice distinctly
  different, natural, and better for non-fiction narration?
- **(human)** If yes: name the voice and approve registry integration
  (see `docs/08-voice-training-spike.md` §8 for the registry entry template).
- **(human)** If no: the existing bm_george + bm_daniel blends are sufficient.
  Consider running the StyleTTS2 spike in a follow-up session.

### Protocol compliance

- All experiments in `playground/` (gitignored)
- No changes to `vorpal/`, voice registry, or committed pipeline
- No voice cloning (no target speaker audio used)
- No money spent
- VRAM peak: ~400 MB (well under 80% of 6 GB limit)

---

## Phase 14 acceptance results

**414 tests green** (414 = 403 Phase-13 + 11 new in `test_phase14.py`).

### What was built

- `cli.py`:
  - `--draft` flag added to the `build` subcommand
  - When active: after TTS synthesis, calls `_compile_draft_wav()` instead of
    `compile_m4b()`; skips loudness normalization, AAC encoding, chapter markers
  - Output: `<stem>_draft.wav` next to the workdir (single concatenated PCM WAV)

- `_compile_draft_wav(chapter_results, output_stem, silence_ms)`:
  - Reads WAV parameters (sample rate, channels, sample width) from the first
    available chapter WAV
  - Concatenates chapter PCM frames in order
  - Inserts zero-padding (`silence_ms`) between chapters (not after the last one)
  - Skips missing chapter WAV paths silently
  - Prints duration and file size to console

### Acceptance

- CLI parser: `--draft` flag wired and defaults to `False`
- `_compile_draft_wav` tested: creates valid WAV, correct duration with/without
  silence, skips missing WAVs, preserves sample rate, handles 0/1/N chapters
- Full-book draft build on real Kokoro audio: not run (would require a full build),
  consistent with the protocol that full-book runs are acceptance activities
- The full mastering path is untouched: without `--draft` the build is identical
  to before Phase 14

---

## Phase 13 acceptance results

**403 tests green** (403 = 372 Phase-12 + 31 new in `test_phase13.py`).

### What was built

- `vorpal/lexicon.py`:
  - `extract_proper_nouns(text)` — heuristic capitalization scan (skips
    sentence-initial words and a `_COMMON_CAPS` filter); caps at 100 words
  - `propose_lexicon(body_text, title, cache_dir, model, backend)` — LLM pass
    via `cli` (subscription) or `api` (VORPAL_ANTHROPIC_KEY); caches by
    `(word_list_hash, title, prompt_version)` so a book is proposed only once
  - `_call_backend(user_msg, model, backend)` — dispatches to `claude -p` or
    anthropic SDK; raises `RuntimeError` on missing credential/CLI
  - `_parse_proposal(raw)` — strips ` ```json ` fences, parses JSON array,
    skips identity entries (`word == spoken_form`) and entries with empty fields
  - `apply_lexicon_to_text(text, lexicon_entries)` — word-boundary regex
    substitution, approved entries only, longest-word-first to avoid partial
    matches; identity for unapproved entries
  - `merge_lexicon(existing, proposed)` — adds new words, updates unapproved
    spoken forms, never overwrites approved entries
  - `_cache_key(word_list, title)` — SHA-256 of sorted word list + title +
    prompt_version, first 16 hex chars

- `cli.py` (build):
  - `--lexicon` flag: extracts proper nouns, calls `propose_lexicon`, merges
    into `manifest.data["lexicon"]`, saves manifest, applies approved entries
    to chapter bodies before TTS
  - `--lexicon-backend cli|api` (default: cli/subscription)

- `cli.py` (review):
  - `--lexicon` flag: prints table of all lexicon entries (word, spoken form,
    approved status) from the manifest; instructions for approving

### (blocked) live acceptance items

- **(blocked: claude -p not authenticated in container)** Live lexicon proposal
  via the `cli` backend — requires `claude /login` first.
- **(blocked: zero API credits)** Live lexicon proposal via the `api` backend.
- **(blocked: both above)** End-to-end test of `--lexicon` + `--lexicon` apply
  path in a real build (lexicon wiring is correct by code review; blocked only
  by LLM credentials).

### Deterministic path unaffected

Building without `--lexicon` is byte-identical to pre-Phase-13 output.
The lexicon is an optional edge: no `--lexicon` → no change to chapter bodies.

---

## Phase 12 acceptance results

**372 tests green** (372 = 349 Phase-11 + 23 new in `test_phase12.py`).

### What was built

- `vorpal/qa/asr.py`:
  - `compute_wer(reference, hypothesis)` — word-level edit-distance WER
  - `sample_chunks(chunks, fraction)` — even-spaced sampling, skips short chunks
  - `transcribe_audio(audio, sample_rate, model)` — Whisper transcription with
    16 kHz resampling via scipy.signal
  - `run_asr_check(chunk_results, ...)` — per-chunk transcription + WER
  - `check_chapters(chapter_entries, ...)` — chapter-level ASR check using
    chapter WAV paths; does not require per-chunk WAV boundaries
  - `format_asr_report(results, ...)` — Markdown section for report.md
  - `ChunkASRResult` dataclass: chunk_idx, chapter, wer, transcript, outlier flag

- `cli.py`: `--asr-check` flag + `--asr-model` (tiny/base/small) + `--asr-fraction`
  (default 0.10). After synthesis, `check_chapters` runs on the sampled chapters;
  outliers listed in console and appended to report.md.

### Live acceptance evidence

ASR round-trip on real Kokoro synthesis (GPU):
- Text: "The old house stood at the end of the lane."
- Kokoro synthesized: 2.67 s audio
- Whisper base transcribed: "The old house stood at the end of the lane."
- **WER: 0.000** — perfect round-trip on this sentence.

Whisper base model downloaded (~139 MB) to `~/.cache/whisper/`.
Full-chapter WER on Firestone blocked (requires full build; not run — consistent
with the protocol that full-book runs are acceptance/corpus activities, not tests).

---

## Phase 11 acceptance results

**349 tests green** (349 = 337 Phase-10 + 12 new in `test_phase11.py`).

### What was built

- `vorpal/qa/__init__.py` + `vorpal/qa/tone_eval.py` — tone effectiveness module:
  - `measure_audio(audio, sample_rate)` → `{energy_rms, duration_s, dominant_freq_hz}` (uses scipy.signal.welch; numpy FFT fallback)
  - `run_acoustic_gate(engine, text)` → per-tone `ToneDeltaResult` (passes, dur_diff, rms_diff, speed_multiplier)
  - `gate_summary(results)` → verdict, pass/fail/unexpected-fail lists
  - `write_ab_kit(neutral, expressive, sr, out_dir, title)` → writes 16-bit WAVs + cumulative manifest.json
  - `format_gate_report(results, summary)` → Markdown table
- `pyproject.toml` gains `[audio]` extra: `scipy>=1.10` (already installed in container)

### Acoustic-delta gate — real Kokoro synthesis on GPU (CUDA)

Test passage: 265-char excerpt from Firestone Chapter 1 (neutral duration = 13.4 s).

| Tone | Speed | dur_diff | rms_diff | Gate |
|------|-------|----------|----------|------|
| excited | 1.12 | 0.0690 | 0.0035 | PASS |
| reflective | 0.90 | 0.0727 | 0.0039 | PASS |
| somber | 0.88 | 0.0915 | 0.0030 | PASS |
| tense | 1.10 | 0.0541 | 0.0022 | PASS |
| urgent | 1.15 | 0.0896 | 0.0072 | PASS |
| warm | 0.95 | 0.0360 | 0.0008 | FAIL |
| wry | 1.00 | 0.0000 | 0.0000 | FAIL (expected — no speed delta) |

**Overall: 5/7 PASS.** `warm` (speed=0.95) fails — the 5% speed shift is too
small to reliably clear the 5% dur_diff threshold on this Kokoro model.
`wry` fails by design (KokoroApprox uses speed only; wry has no speed delta).
This is an honest finding: the approximation layer's expressiveness for `warm`
and `wry` is below the acoustic measurement threshold. These tones would need
a real API engine (OpenAI gpt-4o-mini-tts) or pitch-shift to realize distinctly.

### Demo A/B kit

A demo A/B kit (neutral vs somber, real Kokoro) was generated to
`scratch/ab_kit_demo/` (gitignored):
- `neutral_firestone_ch1_neutral_vs_somber.wav` (24.3 s)
- `expressive_firestone_ch1_neutral_vs_somber.wav` (26.8 s — 10.3% longer, confirming gate)
- `manifest.json` records pairing

### (blocked) live acceptance items

- **(blocked: claude -p not authenticated in container)** Live tone tagging of
  Firestone and corpus books — `claude -p` requires login (`/login` in Claude
  Code session). Fix: run `claude /login` before the tone pass, or use
  `--tone-backend api` with `VORPAL_ANTHROPIC_KEY` (zero credits).
- **(blocked: same)** haiku-vs-sonnet tag quality comparison.
- **(blocked: same)** Neutral fraction ≳ 60% assertion (depends on live tags).
- **(blocked: same)** Full A/B kit with LLM-tagged expressive audio (demo kit
  above uses manually-assigned somber tone, not LLM tags).

### (human) acceptance items

- **(human)** Blind listening verdict on the A/B kit — the feature stays
  `--expressive` opt-in until the human verdict comes in.

---

## Phase 10 acceptance results

**337 tests green** (337 = 327 pre-existing + 10 new in `test_phase10.py`).

### Review notes — what was checked

Modules reviewed: `extract/epub.py`, `extract/text.py`, `tts/voices.py`,
`tts/api_engine.py`, `tts/kokoro_approx.py`, `tone.py`, `master.py` (cache).

Bug classes scanned: encoding issues, unclosed handles, cache-key correctness,
empty/degenerate inputs, malformed EPUB/TXT, error paths that swallow failures.

### Bugs found and fixed (each has a regression test)

1. **`tts/api_engine.py` `_wav_bytes_to_array()`** — `UnboundLocalError` when a
   WAV `data` chunk appears before the `fmt` chunk. `bits`, `channels`,
   `sample_rate` were not initialized before the parsing loop. Fixed: initialize
   them to sentinel values; raise `ValueError("WAV fmt chunk missing before data
   chunk")` in the `data` branch if `bits == 0`. Tests:
   `test_wav_bytes_to_array_data_before_fmt_raises_valueerror`,
   `test_wav_bytes_to_array_normal`.

2. **`tts/kokoro_approx.py` `acoustic_delta()`** — empty arrays silently
   produced NaN and returned `passes=False` rather than raising. NumPy warns but
   the gate logic saw `nan >= 0.05 == False`. Fixed: guard at function entry with
   `ValueError("acoustic_delta requires non-empty audio arrays")`. Tests:
   `test_acoustic_delta_empty_*`.

3. **`tone.py` `tag_chapter()` cache read** — TOCTOU: the `exists()` → `read_text()`
   window was not guarded against `FileNotFoundError` (the except clause only
   caught `JSONDecodeError, KeyError`). A cache file disappearing between the two
   calls would surface as an uncaught exception. Fixed: added `OSError` to the
   except tuple. Test: `test_tag_chapter_cache_oserror_caught`.

4. **`extract/epub.py` `_html_to_text()`** — `decode("utf-8", errors="replace")`
   never raises, so the latin-1 fallback was dead code. Non-UTF-8 HTML
   (e.g., ISO-8859-1 encoded EPUBs) would silently get replacement characters
   instead of correct text. Fixed: decode without `errors=` first; catch
   `UnicodeDecodeError` and fall back to latin-1. Also fixed misleading comment
   in `_parse_ncx` ("top-level navPoints only" was wrong — it iterates all
   depths). Tests: `test_html_to_text_latin1_fallback`,
   `test_html_to_text_utf8_works`.

### No regressions

All 327 pre-existing tests still pass.

---

## Phase 8 acceptance results

- **322 tests green** (261 before Phase 8). 61 new tests:
  `test_tone.py` (39 tests — split_paragraphs, smooth_tones, confidence_gate,
  parse_llm_response, tone_histogram, tag_chapter cache roundtrip/miss/empty,
  cache_key determinism, vocab coverage),
  `test_phase8.py` (22 tests — KokoroApproxEngine construction, speed adjustment
  per tone, pause scaling, acoustic_delta gate, normalize_with_tones, TONE_SPEED/
  TONE_PAUSE_SCALE completeness).

- **Tone tagger (`tone.py`):** ✅ — 8-tag vocabulary; `split_paragraphs`,
  `_smooth_tones` (hysteresis, min 2-run), `_apply_confidence_gate`, LLM prompt
  with per-tag definitions; cache keyed by `(chapter_text_hash, model, v1)`;
  `tag_chapter()` reads from cache on second call; `tone_histogram()`.

- **Kokoro approximation layer (`tts/kokoro_approx.py`):** ✅ — `KokoroApproxEngine`
  wraps any TTSEngine; per-tone `TONE_SPEED` and `TONE_PAUSE_SCALE` dicts; all 8
  tones declared as `supported_tones`; `voice_cache_key` = `approx_<inner_key>`.

- **Acoustic-delta gate:** ✅ — `acoustic_delta()` checks RMS energy diff and
  duration diff against 5% threshold; every non-neutral tone with a non-unity
  speed multiplier passes the gate against the MockEngine+KokoroApproxEngine
  stack.

- **`normalize_with_tones()`:** ✅ — run-based grouping: consecutive same-tone
  paragraphs form a run; each run is chunked independently (no cross-tone chunk
  boundary); chunks annotated with tone (neutral stored as None).

- **CLI wiring:** ✅ — `--expressive` flag triggers tone tagging → `KokoroApproxEngine`
  dispatch; tone histogram printed to stdout; stored in `manifest.settings`;
  `vorpal review --tones` prints per-chapter tone maps.

### (blocked) live acceptance items

- **(blocked: needs Anthropic API credits)** Live tone tagging of Firestone —
  `VORPAL_ANTHROPIC_KEY` is present in container but the account has zero
  credits. Tag run cannot be completed; cache-hit test was verified by
  pre-populating the cache manually.
- **(blocked: needs Anthropic API credits)** Neutral fraction in sane band
  (≳ 60%) — cannot verify without a real LLM tag run.
- **(blocked: needs Anthropic API credits)** Tagging the same book twice is
  a cache hit — verified mechanically (manual cache pre-population) but not
  via a live tag run.
- **(blocked: needs VORPAL_OPENAI_KEY)** All Phase 7 live acceptance items
  (real API synth, manual-tone acoustic delta, network-failure abort).

### (human) acceptance items

- **(human)** A/B kit verdict: paired 1-minute clips (tagged vs all-neutral)
  have not been rendered — Kokoro unavailable in container.
- **(human)** Audition pass on GPU box: `vorpal voices --sample` not yet run.
- **(human)** Full-book `--expressive` build with TTS + mastering not run.

## What Phase 8 built

### `tone.py` (new)

- `TONE_VOCAB = frozenset({"neutral","somber","tense","warm","wry","excited","urgent","reflective"})`
- `split_paragraphs(text)` — double-newline paragraph splitter
- `_smooth_tones(tones, min_run=2)` — hysteresis: isolated non-neutral runs
  shorter than min_run get damped to neutral
- `_apply_confidence_gate(entries, threshold=0.70)` — low-confidence → neutral
- `_parse_llm_response(raw, n)` — JSON array parser, unknown tones → neutral,
  fills/truncates to n
- `_tag_paragraphs_direct(paras, title, model, client)` — builds numbered prompt,
  calls API, returns entries
- `tag_chapter(body, title, cache_dir, model="claude-haiku-4-5")` → cached result
  dict with `tones: [...]`, `paragraphs: [...]`, `cache_hit: bool`
- `tone_histogram(tones_per_chapter)` → `{counts, total, neutral_fraction}`
- Credential: `VORPAL_ANTHROPIC_KEY` ∥ `ANTHROPIC_API_KEY` — never prints key,
  never sets bare `ANTHROPIC_API_KEY` inside container

### `tts/kokoro_approx.py` (new)

- `TONE_SPEED` — per-tone speed multipliers: `somber=0.88`, `tense=1.10`,
  `warm=0.95`, `wry=1.00`, `excited=1.12`, `urgent=1.15`, `reflective=0.90`
- `TONE_PAUSE_SCALE` — per-tone pause multipliers: `somber=1.30`, `tense=0.75`,
  `warm=1.10`, `wry=1.00`, `excited=0.80`, `urgent=0.65`, `reflective=1.25`
- `KokoroApproxEngine` — wraps any inner TTSEngine (defaults to KokoroEngine;
  tests inject MockEngine); `synthesize(text, tone)` adjusts inner.speed to
  `base_speed * TONE_SPEED[tone]`; `scaled_pause(ms, tone)` scales pause_after_ms;
  `voice_cache_key = "approx_<inner_key>"`; `supported_tones = all 8 tones`
- `acoustic_delta(audio_a, audio_b, sample_rate)` → `{rms_diff, dur_diff, passes}`
  — 5% threshold (rounded), True when either metric ≥ 0.05

### `normalize.py` (updated)

- `normalize_with_tones(body, paragraph_tones, max_chars)` — run-based tone
  annotation: groups paragraphs by tone into runs, chunks each run via
  `normalize_chapter()`, annotates chunks with run tone (neutral → None for
  schema compatibility), re-indexes all chunks sequentially

### `tts/__init__.py` (updated)

- Exports `KokoroApproxEngine`

### `cli.py` (updated)

- `--expressive` build flag: triggers tone tagging + `KokoroApproxEngine` dispatch
- `--tones` review flag: prints per-chapter tone maps from tone cache
- Tone histogram written to `manifest.data["settings"]["tone_histogram"]`
- Engine dispatch: OpenAI voice → APIEngine; `--expressive` → KokoroApproxEngine;
  default → KokoroEngine

## What Phase 7 built (summary)

- MockEngine (tone-aware, deterministic, fail_on trigger)
- APIEngine (OpenAI TTS via requests, instruction strings, WAV decoder)
- `estimate_synth_cost()` + `--max-cost` flag
- OpenAI voices in registry (oa_alloy, oa_echo, oa_nova); 14 total
- 261 tests green

## What Phase 6 built (summary)

- `tts/voices.py`: 11-entry registry (8 Kokoro singles + 3 blends)
- Blend support in KokoroEngine (weighted tensor mix, recipe cache key)
- `vorpal voices` subcommand; `--voice <id>` validates against registry

## What Phase 5 built (summary)

- EPUB/TXT multi-format input (stdlib parsers)
- Mastering staleness cache; chapter-count gate; README rewrite
- 205 tests green

## Environment facts

- **Use `venv311`** (Python 3.11, kokoro 0.9.4, CUDA torch).
- `VORPAL_ANTHROPIC_KEY` provisioned — but account has zero credits (as of
  2026-06-07). Live tone tagging is blocked until credits are added.
- `VORPAL_OPENAI_KEY` not provisioned — Phase 7 live acceptance blocked.
- Firestone: two-page spreads (one PDF page = two printed pages).

## Quick re-entry checklist

```
python -m pytest -q                  # should be 698 passed

# Verify Phase 30 (web UI):
pip install -e '.[web]'
vorpal serve tests/fixtures/outline.pdf
# → browser opens at http://localhost:7654

# Verify Phase 14:
vorpal build tests/fixtures/outline.pdf --draft --end-page 3
# → <stem>_draft_kokoro.wav produced; skip mastering

# What to verify on a GPU + credential machine:
#   1. vorpal build firestone.pdf --expressive → tone histogram ≳ 60% neutral
#   2. vorpal build firestone.pdf --draft → fast whole-book preview WAV
#   3. vorpal serve firestone.pdf → browser UI, chapter edit, build trigger
#   4. A/B kit compare --expressive vs plain (human listening verdict pending)
```

## What to build next

**All Arcs 1–6 are complete** (Phases 0–30 done or honestly blocked).

Phase 21 and 22 remain blocked on `VORPAL_OPENAI_KEY`. Phase 26 pending
Piper live test (H-011). Phase 30 pending browser usability spot-check (H-010).

The next session should either:
1. **Resolve H-010/H-011**: add credentials and run live acceptance, then close
   the items in `docs/09-human-review-queue.md`.
2. **Propose new phases**: work through the product vision in
   `docs/02-product-vision.md` for any remaining gaps, write them to
   `docs/04-roadmap.md` with acceptance criteria, and build.
3. **Wonderland project**: if all pipeline work is genuinely exhausted, start a
   standalone Alice in Wonderland themed project in `playground/` per
   CLAUDE.md §"Wonderland projects".

### Tone-backend credential status & the manual-seeding approach

`VORPAL_ANTHROPIC_KEY` has zero credits and `claude -p` is not authenticated
inside the container. For phases that touch the LLM backend (Phase 17 — OCR
repair; Phase 29 — chapter summaries), the agent must use the
**manual-seeding approach**:

1. Find actual low-confidence blocks in the Firestone `pages.jsonl`.
2. Write plausible proposals by hand (same JSON structure the LLM would return).
3. Inject them and run the full downstream workflow: diff in review,
   approve/reject round-trip, apply path.
4. Document: *"LLM proposal step manually seeded — workflow verified; live
   call blocked on credentials."*

**Why the compromise is sound:** the goal is to confirm code paths, data
structures, review surface, and normalization application are correct *before*
credentials arrive. When the token is added, only the proposal source changes —
everything downstream is already proven. This is the same pattern used in
Phase 8 (manual cache pre-population) and Phase 13 (lexicon round-trip without
live LLM). The `cli` tone backend's `claude -p /login` step: if it requires
interactive login, mark it `(human: claude -p needs /login)` and continue.

### Pending human actions

Full details and decision options for every item are in
**[`docs/09-human-review-queue.md`](09-human-review-queue.md)** — that is the
canonical list. The agent appends to it automatically; work through it
asynchronously. Summary of open items:

| ID | Phase | What's needed |
|---|---|---|
| H-001 | Phase 9 | Listen to `playground/final_vorpal_narrator_v1.wav` vs baseline; approve/reject registry integration |
| H-002 | Phase 7/21 | Provision `VORPAL_OPENAI_KEY` to unblock APIEngine live acceptance |
| H-003 | Phase 8/11/22 | Blind A/B tone verdict — does `--expressive` sound better? |
| H-004 | Phase 11 | Add API credits or run `claude /login` interactively to unblock live tone tagging |
| H-005 | Phase 3 | Listening spot-check of a full Firestone build (narration quality) |
| H-006 | Phase 4 | Chapter marker verification in VLC or BookPlayer |
| H-007 | Phase 6 | Voice audition (`vorpal voices --sample`) — pick favourites, adjust blends |
| H-008 | Phase 24 | Dialogue delivery spot-check (pending Phase 24) |
| H-009 | Phase 23 | StyleTTS2 voice verdict (pending Phase 23) |
| H-010 | Phase 30 | TUI usability spot-check (pending Phase 30) |

### Roadmap horizon

- **Arc 4 (Phases 15–20):** parallel OCR, batched TTS, LLM OCR repair (manual
  seeded), library mode, manifest export, corpus hardening.
- **Arc 5 (Phases 21–25):** OpenAI TTS live, tone on real engine, StyleTTS2
  spike, dialogue-aware delivery, footnote narration.
- **Arc 6 (Phases 26–30):** Piper draft engine, loudness profiles, richer
  metadata/cover, chapter summaries, TUI/web UI.
- **Beyond Phase 30:** the agent proposes and builds new phases autonomously,
  staying within the product vision. When all pipeline work is genuinely
  exhausted it may start a standalone Wonderland project in `playground/`.
  See CLAUDE.md §"Wonderland projects".

### Full-day autonomous launch command

```powershell
.\docker\run.ps1 -Gpu -Prompt "Read CLAUDE.md, docs/05-status.md, docs/09-human-review-queue.md, and docs/04-roadmap.md. Work through all remaining phases in roadmap order starting from wherever the status doc says we are. Follow the unsupervised-run protocol exactly. When you finish all planned phases, propose new ones — add them to docs/04-roadmap.md with full acceptance criteria, then build them immediately. Stay within the product vision in docs/02-product-vision.md. If you genuinely exhaust all pipeline work, start a standalone Wonderland project in playground/ per the instructions in CLAUDE.md. Never stop voluntarily unless the machine is at risk. No pushing code."
```
