# Status & Handoff

*Last updated: 2026-06-07 (Phase 8 complete).* Read this first when picking the project back up.
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
| **Arc 2: Phase 8 — tone tagging + effectiveness gates (`--expressive`)** | ✅ done (pending live + human acceptance) | this commit |
| Arc 2: Phase 9 — in-house voices (spike-gated) | queued | roadmap |

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
python -m pytest -q                  # should be 322 passed

# Verify Phase 8 additions:
vorpal voices                        # 14 narrators (11 kokoro + 3 openai)
vorpal build book.epub --expressive  # runs tone tagger + KokoroApproxEngine
                                     # (blocked until API credits added)

# What to verify on a GPU + credit machine:
#   1. vorpal build firestone.pdf --expressive
#      → tone histogram shows neutral fraction ≳ 60%
#   2. second run → 100% cache hit on tagging
#   3. vorpal voices --sample → voices_preview/ plays correctly
#   4. A/B kit: compare --expressive vs plain build on a 1-min clip
```

## What to build next (Phase 9 or corpus expansion)

Phase 9 — in-house voices (spike only): design + one proof-of-concept voice,
per the guardrails in [04-roadmap.md](04-roadmap.md). Full phase plan gets
written only after the spike reports.

Alternatively: resolve Phase 7/8 live acceptance items (add API credits, add
OpenAI key) and complete the human acceptance items before starting Phase 9.
