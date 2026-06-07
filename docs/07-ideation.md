# Ideation: Expressive Narration

*Started 2026-06-07. This is the thinking document for everything past the
"clean, correct, coherent" bar — new voices, an **effective** tone system, and
the path to the north star (any PDF → a voice you want to hear reads it
expressively). Ideas graduate from this doc into [04-roadmap.md](04-roadmap.md)
when they earn it. The deterministic core remains sacred: every idea below must
degrade gracefully to "books still build without it."*

> **Graduated 2026-06-07 → roadmap Arc 2:** voice registry/blending/audition
> (Phase 6), first tone-capable API engine + cost guard (Phase 7), tone
> tagging + effectiveness gates (Phase 8), in-house voice training spike
> (Phase 9), far-future UI note. The sections below remain the *reasoning*
> behind those phases — read them before implementing one. The product
> boundary sharpened in the vision doc: **users never supply voice samples**;
> in-house-trained voices ship as ordinary suite entries.

---

## 1. Voice expansion

### 1a. Free wins inside Kokoro (no new engine)

- **Voice blending.** Kokoro voices are embedding tensors; a weighted mix
  (`0.7 × af_heart + 0.3 × af_sky`) is a *new voice* for free. Expose as
  `--voice "af_heart:0.7,af_sky:0.3"`, store the blend in the manifest (it's
  part of the chunk cache key via `voice`). This is the cheapest "more voices"
  on the table and a prerequisite experiment for tone realization (§2c).
- **`vorpal voices` audition command.** `vorpal voices --sample "text"` renders
  a short sample per voice/blend into `voices_preview/`. Choosing a narrator
  today requires a full build cycle; this makes it a 30-second decision.
- **Speed/pause as character.** A voice is also its pacing: per-book
  `speed` + paragraph-pause profile presets ("brisk", "bedtime") — trivially
  cacheable, already in the cache key via `speed`.

### 1b. Engine landscape (local)

Behind `TTSEngine`, in rough order of interest:

| Engine | Why | Why not / risk |
|---|---|---|
| **StyleTTS2** | Style vectors = real tone control, local, strong quality | Style vector wrangling is research-ish; EN voices limited |
| **Orpheus TTS** (llama-based, 2025) | Inline emotive tags (`<sigh>`, `<laugh>`), natural prosody | 3B params — GPU-hungry next to Kokoro's 82M; speed |
| **Chatterbox** (Resemble) | Emotion-exaggeration knob — a literal tone dial | Cloning-adjacent framing; verify license + non-clone use |
| **Dia** (2025) | Dialogue + nonverbal sounds | Dialogue-focused, 1.6B; our use is narration |
| **Piper** | Very fast CPU; draft builds while iterating on a book | Quality clearly below Kokoro — never the final voice |
| VOICEVOX | Actual anime-character voices, free | Japanese-only in practice; EN is the product language |

Each candidate gets a one-day spike: implement the `TTSEngine` adapter, run a
2-chapter Firestone sample, listen. Keep adapters even for rejects — the
interface stays honest that way.

### 1c. Engine landscape (API) — surprisingly affordable

An 8 h book ≈ 410 k characters. Approximate full-book costs (verify current
pricing before any spike):

| Provider | Mechanism for tone | ~Cost/book | Note |
|---|---|---|---|
| **OpenAI `gpt-4o-mini-tts`** | *Instructions* per request ("read somberly, slowly") | ~$5–10 | Steerable TTS — the most direct tone-realization fit |
| **Azure Neural** | SSML `mstts:express-as style="sad" styledegree="1.4"` | ~$5–15 | Discrete styles map 1:1 onto our tone tags |
| **ElevenLabs v3** | Inline audio tags (`[whispers]`, `[excited]`) | ~$50–150 | Best voices incl. character/anime-adjacent designs; cost |
| Google Cloud | SSML, some styles | ~$5–15 | Meh styles; fallback option |

API engines change the failure model (network, rate limits, nondeterminism) —
the retry→split→abort policy and chunk cache already absorb most of that, but
add: per-build cost estimate + `--max-cost` guard before the first request.

### 1d. The anime-girl narrator, concretely

Honest assessment of paths, cloning still excluded:

1. **ElevenLabs voice design / curated character voices** — closest existing
   thing to the wish; pay-per-book (see costs above).
2. **Kokoro blends** toward brighter/higher voices (`af_sky`, `af_nicole`
   mixes) — a free approximation worth 30 minutes of auditioning.
3. **A fine-tuned local model** (StyleTTS2/Orpheus on a licensed character-
   voice dataset) — the "own it forever" path; real effort, park until tone
   realization (§2) proves out, since the same machinery serves both.

## 2. The tone system — making it *effective*

The Phase-3 schema (`tone` on every chunk, in the cache key) was the easy
part. An *effective* tone system needs four pieces, each independently
testable:

### 2a. Taxonomy — small enough to tag reliably, rich enough to hear

Draft vocabulary (≤ 8, deliberately coarse):

```
neutral · somber · tense · warm · wry · excited · urgent · reflective
```

- Two-axis alternative (valence × arousal, 3×3 grid) is more principled but
  harder to prompt an LLM with consistently; start discrete, revisit.
- Every tag needs a one-line definition + 2 example passages in the tagging
  prompt — vague taxonomies produce noise, not tone.
- `neutral` must be the overwhelming default (~80 %+ of a typical book).
  A tagger that paints everything `excited` is worse than no tagger.

### 2b. Tagging pass (`tone.py`)

- LLM tags **paragraphs** (not sentences — too jittery; not chapters — too
  flat), with a window of surrounding context and the chapter title.
- **Smoothing/hysteresis:** minimum run length of ~2–3 paragraphs per
  non-neutral tone; isolated one-paragraph spikes get damped to neutral.
  Tonal whiplash is the #1 way this feature becomes ridiculous.
- **Cache per `(chapter_text_hash, model, prompt_version)`** — a book is
  tagged once, ever, unless the text or prompt changes. Tagging an 11-chapter
  book ≈ 75 k words ≈ a few dollars of LLM at most; cache makes it once.
- Output is *reviewable*: `vorpal review --tones` prints a per-chapter tone
  map (paragraph ranges + tags) the user can edit in `book.json`, same
  contract as chapter review. Tone histogram lands in `report.md`.
- Confidence: tagger emits per-tag confidence; low-confidence → neutral.

### 2c. Realization — per-engine, capability-declared

The tag means nothing until an engine *does* something with it. Realization
matrix (engine declares `supported_tones`, normalize/synth pass tags through):

| Engine class | Realization |
|---|---|
| Instruction APIs (gpt-4o-mini-tts) | Tone → instruction string per chunk ("low energy, somber, slightly slower") |
| SSML APIs (Azure) | Tone → `express-as` style + `styledegree` |
| Tag engines (ElevenLabs v3, Orpheus) | Tone → inline audio tag at chunk start |
| **Kokoro (no native control)** | Approximation layer: speed ±8 %, paragraph-pause scaling, optional voice-blend shift (somber → +20 % toward a deeper voice). Must A/B test — risk of sounding broken instead of expressive |
| Anything else | Ignore tags (today's behavior — always valid) |

Chunk-boundary discipline matters more with tone: a tone change mid-paragraph
forces a chunk split (tone is per-chunk); the chunker should align tone-run
boundaries with chunk boundaries.

### 2d. Effectiveness evaluation — "effective" must be measurable

The trap is shipping vibes. Two cheap measurements before any listening party:

1. **Acoustic delta check (objective):** synthesize the same passage under
   each tone; extract f0 mean/variance, energy, speaking rate (librosa).
   A tone system where `somber` and `excited` produce statistically
   indistinguishable audio is *not working*, whatever the tags say. This
   becomes a unit-style gate for every tone-capable engine adapter.
2. **Blind A/B protocol (human, tiny):** 10 paired clips (tagged build vs
   all-neutral build), user picks which reads better. The feature earns its
   default-on only by winning this; otherwise it stays `--expressive` opt-in.

## 2e. Far future: a visual layer (parked by decision)

Bottom of the priority list — *we need a product before packaging* — but
worth one paragraph of foresight so future planning has a hook: the moments
that would benefit from UI are exactly the existing human checkpoints —
review-table editing, voice audition, tone-map inspection, live build
progress. All of them are manifest reads/writes, so the natural shape is a
thin local web UI (FastAPI + a small page) or a TUI over `book.json`, later
wrapped as an exe (PyInstaller) if distribution ever matters. No architecture
changes needed now; explicitly not being built.

## 3. Parking lot (adjacent ideas, unsorted)

- **Pronunciation lexicon** per book (names/terms → IPA hints; misaki supports
  custom pronunciation). LLM can *propose* the lexicon from the book's proper
  nouns; user approves in review.
- **Dialogue-aware delivery** — detect quoted speech, render with subtle
  delivery shift (same narrator voice — multi-voice drama stays out of scope).
  Natural extension of the tone machinery; scope-tension flag: keep subtle.
- **Draft-mode builds** (`--draft`: Piper/CPU, no mastering) for fast whole-book
  iteration before committing the GPU/API spend.
- **Listening-target loudness profiles** (car / headphones / speaker presets).
- **Chapter summary side product** (text-only, never narrated — content
  fidelity is a product contract).
- **ASR round-trip QA** and **parallel OCR / batched TTS** — still queued from
  the original post-v1 list; batched TTS matters more once API engines bill
  per request.

## 4. Suggested sequencing (cheap + load-bearing first)

1. **Kokoro voice blending + `vorpal voices` audition** — days, pure win,
   teaches us voice-identity plumbing the tone work reuses.
2. **First tone-capable engine adapter** (gpt-4o-mini-tts or Azure) behind
   `TTSEngine` — proves the realization path with a vendor who already solved
   expressiveness; includes cost guard.
3. **`tone.py` tagging pass** with cache + review surface + histogram.
4. **Acoustic delta gate + blind A/B** — the "effective?" verdict.
5. Decide the character-voice path (1d) with everything above in hand.

Steps 1–2 are independent of each other; 3 is useless without 2; 4 judges 2+3.

## 5. Guardrails (unchanged)

- No voice cloning — character voices come from engines/curated designs.
- Deterministic core: tone/LLM passes are optional layers; `vorpal build`
  without them must remain byte-for-byte reproducible.
- One narrator voice per book (delivery may flex; identity may not).
- Tone edits follow the same review contract as chapters: visible, editable,
  cache-precise (a re-tagged paragraph re-synthesizes only its chunks).
