# Status & Handoff

*Last updated: 2026-06-07 (Phase 7 complete — credential gate).* Read this first when picking the project back up.
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
| Phase 5 — multi-format input & end-to-end hardening | ✅ done | commit `1c460a8` |
| Phase 6 — voice suite v1 (registry, blends, audition) | ✅ done | commit `a06372f` |
| **Arc 2: Phase 7 — first tone-capable engine (credential gate)** | ✅ done (pending live acceptance) | this commit |
| Arc 2: Phase 8 — tone tagging + effectiveness gates (`--expressive`) | queued | roadmap |
| Arc 2: Phase 9 — in-house voices (spike-gated) | queued | roadmap |

## Phase 7 acceptance results

- **261 tests green** (230 before Phase 7). 31 new tests in `test_phase7.py`:
  MockEngine synthesis, tone acoustic delta, determinism, speed/duration, fail_on
  trigger, cost estimation (free/paid/skip/intro/empty), APIEngine structure
  (supported tones, cost positive, tone instructions complete), credential
  resolution (VORPAL_OPENAI_KEY preferred over OPENAI_API_KEY, missing → None),
  no-key raises correctly, cache-key integration (tone distinguishes chunks),
  registry has OpenAI voices, WAV decoder roundtrip.

- **MockEngine:** ✅ — deterministic, tone-aware (different tones → distinct sine
  frequencies → acoustic delta testable without GPU), `fail_on` trigger for
  retry/abort policy tests, `cost_per_1k_chars = 0.0`.

- **APIEngine:** ✅ — OpenAI TTS adapter (`gpt-4o-mini-tts` for tones, `tts-1`
  for neutral), instruction strings for all declared tones, WAV response decoder,
  `cost_per_1k_chars = 0.015` ($15/1M chars), `VORPAL_OPENAI_KEY` credential
  resolution (never bare `ANTHROPIC_API_KEY`).

- **Cost machinery:** ✅ — `estimate_synth_cost(chapters, engine)` counts chars
  × cost per 1k; `--max-cost <USD>` flag aborts before synthesis if estimate
  exceeds budget; estimate printed to stdout for API builds.

- **Tone cache-key isolation:** ✅ — chunk cache key carries `tone` component;
  neutral and somber chunks have distinct cache keys → tone change re-synthesizes
  only the affected chunks.

- **OpenAI voices in registry:** ✅ — 3 OpenAI voice entries (`oa_alloy`,
  `oa_echo`, `oa_nova`); registry grows to 14 narrators total. Voice dispatch in
  `cli.py` now checks `voice_entry.engine` and instantiates `APIEngine` or
  `KokoroEngine` accordingly; OpenAI voices abort with a clear error when
  `VORPAL_OPENAI_KEY` is absent.

### (blocked) live acceptance items

The following Phase 7 items require a live OpenAI API key and cannot be
self-verified in the container:

- **(blocked: needs VORPAL_OPENAI_KEY)** 1-chapter Firestone build through
  APIEngine completes with `failed: 0` and a printed cost line matching the
  estimate (±20 %).
- **(blocked: needs VORPAL_OPENAI_KEY)** Manual-tone chapter (`somber`) produces
  audio measurably distinct from its neutral build (f0/energy/rate acoustic delta).
- **(blocked: needs VORPAL_OPENAI_KEY)** Network-failure mid-build aborts loudly
  (tested by pulling network) with a resumable chunk cache.

These items are marked **(blocked)** per the Phase 7 credential-gate rule.
The phase is "done (pending live acceptance)" — Phase 8 is not blocked.

### (human) acceptance items

- **(human)** Audition pass: render `voices_preview/` on the GPU box and pick
  favourite Kokoro narrators (from Phase 6, still pending).
- **(human)** Full-book blend build not run in container.

## What Phase 7 built

### `tts/mock_engine.py` (new)

- `MockEngine(voice, speed, fail_on)` — deterministic mock TTS, no GPU/model
- `synthesize(text, tone)` returns float32 array:
  - `None`/`"neutral"` → silence (zeros); other tones → sine wave at tone-specific
    frequency (110/220/330/440 Hz → A2/A3/E4/A4)
- `fail_on`: if set, raises `RuntimeError` when text contains that string —
  drives retry/abort policy in tests
- `cost_per_1k_chars = 0.0` (local/free)
- `voice_cache_key` property returns `self.voice`

### `tts/api_engine.py` (new)

- `APIEngine(voice, speed, model)` — OpenAI TTS via `requests`
- `_resolve_openai_key()` → `VORPAL_OPENAI_KEY` ∥ `OPENAI_API_KEY` (never
  reads bare `ANTHROPIC_API_KEY` — would hijack agent subscription)
- `synthesize(text, tone)`: selects model (`gpt-4o-mini-tts` when tone active;
  `tts-1` otherwise), builds instruction string from `_TONE_INSTRUCTIONS` dict,
  POSTs to `https://api.openai.com/v1/audio/speech`, decodes WAV response
- `_wav_bytes_to_array(bytes)` — stdlib-only WAV decoder (PCM int16/float32,
  mono/stereo)
- Raises `RuntimeError` if key missing or API returns non-200
- `cost_per_1k_chars = 0.015` ($15/1M chars)

### `synth.py` (updated)

- `estimate_synth_cost(chapters, engine)` → `(total_chars, estimated_usd)`:
  counts spoken_intro + body chars for non-skipped chapters; uses
  `engine.cost_per_1k_chars`

### `tts/voices.py` (updated)

- 3 OpenAI voice entries added: `oa_alloy`, `oa_echo`, `oa_nova`; total 14

### `cli.py` (updated)

- `--max-cost USD` flag: aborts before synthesis if cost estimate exceeds budget
- Engine dispatch: `voice_entry.engine == "openai"` → `APIEngine`; else
  `KokoroEngine` (avoids importing APIEngine at startup)
- OpenAI key check happens before engine construction
- Cost estimate printed + checked against `--max-cost` before TTS stage

### `pyproject.toml` (updated)

- `[api]` optional extra: `pip install -e .[api]` installs `requests>=2.28`

## What Phase 6 built (summary — see previous status doc for full details)

- `tts/voices.py`: 11-entry voice registry (8 Kokoro singles + 3 blends)
- `KokoroEngine` blend support (weighted tensor mix, recipe-based cache key)
- `vorpal voices` subcommand + `--sample` audition rendering
- `--voice <id>` validates against registry; manifest stores resolved params
- 230 tests green (205 → 230)

## What to build next (Phase 8)

From [04-roadmap.md](04-roadmap.md) Arc 2 Phase 8 — tone tagging + effectiveness:

**No-key path: use the Kokoro approximation layer (speed/pause/blend shifts)
as the tone-capable engine.** `VORPAL_ANTHROPIC_KEY` is provisioned (CLAUDE.md).

1. `tone.py` — LLM paragraph-level tone tagging:
   - Vocabulary: ≤ 8 tags (`somber`, `tense`, `warm`, `wry`, `neutral` + others
     from ideation §2a)
   - Context windows for coherence, smoothing/hysteresis (min 2–3 para runs,
     isolated spikes → neutral), confidence gate
   - Cache: `(chapter_text_hash, model, prompt_version)` → never re-tag
   - Batches API (`claude-haiku-4-5`) for cost efficiency
   - `vorpal review --tones` prints per-chapter tone map for editing

2. Kokoro approximation layer — tone realization without API key:
   - `KokoroApproxEngine` wraps KokoroEngine with per-tone speed/pause adjustments
   - `somber` → speed 0.88, longer paragraph pauses
   - `tense` → speed 1.1, shorter pauses
   - `warm` → speed 0.95
   - `wry` → speed 1.0 (default), emphasis hints via punctuation

3. Effectiveness gate (from ideation §2d):
   - (a) Acoustic-delta check: non-neutral tags must produce statistically distinct
     audio from neutral
   - (b) A/B kit: paired 1-minute clips emitted by `--expressive`

4. Everything behind `--expressive` flag; deterministic no-tone build byte-identical
   to Phase 7 output

Accept when: tagging Firestone twice is a 100 % cache hit; neutral fraction ≳ 60 %;
acoustic-delta gate passes; **(human)** A/B kit verdict.

## Environment facts

(Agent onboarding incl. Linux/Docker setup lives in [`CLAUDE.md`](../CLAUDE.md))

- **Use `venv311`** (Python 3.11, kokoro 0.9.4, CUDA torch).
- `VORPAL_ANTHROPIC_KEY` provisioned in container (for tone tagging — Phase 8).
- `VORPAL_OPENAI_KEY` NOT provisioned — Phase 7 live acceptance blocked.
- `rapidfuzz`, `pysbd` added in Phases 2–3; `requests` in system path.
- Firestone: two-page spreads (one PDF page = two printed pages).

## Quick re-entry checklist

```
python -m pytest -q                  # should be 261 passed

# Verify Phase 7 additions:
vorpal voices                        # should show 14 narrators (11 kokoro + 3 openai)

# Cost estimate check (no key needed — just the estimate):
# (run against a real EPUB to get chapters with bodies)

# Phase 8 starting point:
# vorpal build book.epub --expressive  (--expressive flag not yet wired)
```

Then start Phase 8: `tone.py` (LLM tagger + Kokoro approximation), `--expressive` flag.
