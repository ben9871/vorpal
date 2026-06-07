# Status & Handoff

*Last updated: 2026-06-07 (Phase 6 complete).* Read this first when picking the project back up.
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
| **Arc 2: Phase 6 — voice suite v1 (registry, blends, audition)** | ✅ done | this commit |
| Arc 2: Phase 7 — first tone-capable engine (API, cost-guarded) | queued | roadmap |
| Arc 2: Phase 8 — tone tagging + effectiveness gates (`--expressive`) | queued | roadmap |
| Arc 2: Phase 9 — in-house voices (spike-gated) | queued | roadmap |

## Phase 6 acceptance results

- **230 tests green** (205 before Phase 6). 25 new tests in `test_voices.py`:
  registry shape (count, blend count, field completeness, weight positivity),
  `resolve_voice` / `list_voices`, `_params_cache_key` (single vs blend, determinism,
  order-independence, weight-edit invalidation, speed exclusion), `KokoroEngine`
  params-based construction, `voice_cache_key` property, synth `_cache_key`
  integration (blend hash in key, no `None` for blend engines).

- **Registry:** 11 narrators — 8 Kokoro single voices + 3 curated blends.
  ≥ 6 voices and ≥ 2 blends: ✅

- **`vorpal voices` subcommand:** ✅ — lists suite as a formatted table with
  id, display name, type (single/blend), description; shows usage hints;
  `--sample` flag renders audition WAVs into `voices_preview/`.

- **`--voice <id>` registry validation:** ✅ — any registry id accepted
  (including blend ids); unknown ids print a clear error with the available
  list and pointer to `vorpal voices`.

- **Blend cache-key invalidation:** ✅ — `KokoroEngine.voice_cache_key`
  returns a `blend_<sha256[:16]>` string for blend params; editing blend
  weights produces a different key, invalidating exactly those cached chunks
  and leaving other voices untouched.

- **Manifest stores resolved params:** ✅ — `manifest.data["settings"]`
  gains `voice_id` (e.g. `"blend_warm_bright"`) and `voice_params`
  (e.g. `{"blend": {"af_heart": 0.65, "af_nova": 0.35}}`), so the build is
  reproducible from the manifest alone.

- **Single-voice backwards compatibility:** ✅ — `KokoroEngine(voice="af_heart")`
  (legacy form) still works; `voice_cache_key` returns the voice name string
  as before, so all existing cached audio remains valid.

### (human) acceptance items

- **(human)** Audition pass: render `voices_preview/` on the Windows GPU box
  (`vorpal voices --sample`) and pick favourite single + blend narrators.
- **(human)** Full-book build with a blend voice has not been run in container
  (Kokoro unavailable on CPU-only torch build).

## What Phase 6 built

### `tts/voices.py` (new)

- `VoiceEntry` dataclass: `{id, display_name, engine, params, description}`
- `VOICE_REGISTRY` — 11 curated entries:
  - 8 single Kokoro voices (`af_heart`, `af_nova`, `af_sky`, `am_echo`,
    `am_michael`, `am_fenrir`, `bf_emma`, `bm_george`)
  - 3 blends (`blend_warm_bright`, `blend_deep_steady`, `blend_transatlantic`)
- `_params_cache_key(params)` — stable cache-key string:
  single voice → voice name; blend → `blend_<sha256[:16]>` of sorted blend
  JSON (speed excluded — captured separately in the chunk-cache key formula)
- `resolve_voice(id)` → `VoiceEntry | None`
- `list_voices()` → `list[VoiceEntry]`

### `tts/kokoro_engine.py` (updated)

- `__init__` gains `params: Optional[dict]` — accepts registry VoiceEntry params
  directly; `speed` arg always overrides (CLI `--speed` wins)
- `voice_cache_key` property — delegates to `_params_cache_key(self._params)`
- `_get_voice_arg()` — returns voice name string for single voices; for blends,
  loads each embedding via `pipeline.load_voice()`, computes a L1-normalized
  weighted sum, caches the result tensor, returns it
- `synthesize()` updated to call `_get_voice_arg()` instead of `self.voice`
- Legacy `KokoroEngine(voice="af_heart")` call still works

### `tts/__init__.py` (updated)

- Exports `VoiceEntry`, `VOICE_REGISTRY`, `resolve_voice`, `list_voices`

### `synth.py` (updated)

- `_cache_key()` uses `engine.voice_cache_key` when available (falls back to
  `engine.voice` for engines without the property) — blend engines produce
  `blend_<hash>` cache key prefixes, not `None`

### `cli.py` (updated)

- `--voice` arg: removed `choices=KOKORO_VOICES` restriction; validates against
  `VOICE_REGISTRY` after file existence check; prints registry id list + pointer
  to `vorpal voices` on unknown id
- Header print shows `voice.display_name (id, speed: N)` instead of just the id
- Engine constructed as `KokoroEngine(params=voice_entry.params, speed=args.speed)`
- `manifest.data["settings"]["voice_id"]` and `["voice_params"]` written before TTS
- `voices` subcommand added (parser + `cmd_voices()` handler)
- `_render_voice_samples()` — renders short audition WAVs via `KokoroEngine.synthesize()`
- `main()` dispatches `"voices"` command

### `README.md` (updated)

- "Voices" section with suite table (all 11 narrators, types, descriptions)
- `vorpal voices` command reference
- `--voice` help text updated from hard-coded list to registry pointer
- `tts/voices.py` added to project layout

## What Phase 5 built (summary — see previous status doc for full details)

- EPUB/TXT multi-format input (stdlib-only parsers, no AGPL deps)
- Mastering staleness cache (per-chapter M4A sidecar keyed by wav SHA + LUFS + bitrate)
- Duration-sanity / chapter-count gate using ffprobe
- 205 tests green (156 → 205)

## What Phase 4 built (summary)

- Per-chapter loudness normalization (two-pass loudnorm), ffmpeg concat-demuxer
  M4B assembly, chapter markers, cover art, MP3 side product, `report.md`.
- Constant-memory (65.9 MB peak RSS on Firestone). Full Firestone mastering:
  11/11 chapters PASS ±1 LU gate.

## What to build next (Phase 7)

From [04-roadmap.md](04-roadmap.md) Arc 2 Phase 7 — first tone-capable API engine:

**Credential gate applies: no TTS-provider key (OpenAI/Azure) in the container.**
The Phase 7 rule: wire a mock API engine with recorded-response tests; mark all
live-synthesis items **(blocked: needs TTS provider key)** — never simulate a pass.

1. `tts/api_engine.py` — `APIEngine(TTSEngine)` calling an HTTP endpoint
   (OpenAI TTS or compatible); `supported_tones` declares the tones it acts on
2. Mock engine (`tts/mock_engine.py`) — returns deterministic audio for any
   text, based on recorded stub responses; used in all tests
3. Cost guard: `--max-cost` flag; token estimator; abort before synthesis if
   estimated cost exceeds budget
4. `engine` field in manifest; multi-engine builds go to separate worktirs

Accept when: mock engine tests green; cost guard enforces limit; real synth with
a valid key produces audio of correct duration; **(blocked)** all live-synthesis
acceptance items listed honestly.

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
python -m pytest -q                  # should be 230 passed
vorpal voices                        # lists 11 narrators (8 single + 3 blend)

# Verify registry-aware --voice flag:
vorpal build scratch/outline.pdf --voice blend_warm_bright --stop-after segment

# Full regression (PDF structure, no TTS):
vorpal build firestone\firestone-shulamith-dialectic-sex-case-feminist-revolution.pdf \
    --output scratch\firestone_p6 --stop-after segment

# GPU host: audition all voices
vorpal voices --sample               # → voices_preview/*.wav
```

Then start Phase 7: mock API engine, cost guard, tone-capable synthesis.
