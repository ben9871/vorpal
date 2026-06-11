# Voices

vorpal ships with 11 curated voices: 8 single Kokoro voices and 3 blend voices.
All are local — no cloud, no account, no per-character cost.

## Single voices

| ID | Name | Accent | Gender | Character |
|----|------|--------|--------|-----------|
| `af_heart` | Heart | American | Female | Warm, expressive — **default** |
| `af_nova` | Nova | American | Female | Clear, precise, neutral |
| `af_sky` | Sky | American | Female | Light, airy, higher register |
| `am_echo` | Echo | American | Male | Resonant, warm mid-range |
| `am_michael` | Michael | American | Male | Steady, measured, long-form |
| `am_fenrir` | Fenrir | American | Male | Deep, commanding, authoritative |
| `bf_emma` | Emma | British | Female | Clear RP accent, measured |
| `bm_george` | George | British | Male | Distinguished, period-appropriate |

Voice IDs follow the convention `{accent}{gender}_{name}`:
`a` = American, `b` = British; `f` = female, `m` = male.

## Blend voices

Blend voices are weighted averages of two single-voice speaker embeddings,
computed at inference time. No training required — the recipe is a dict of
`{voice_id: weight}` in the registry.

| ID | Recipe | Character |
|----|--------|-----------|
| `blend_warm_bright` | Heart 65% + Nova 35% | Warmth with added clarity |
| `blend_deep_steady` | Fenrir 55% + Michael 45% | Authority with steadiness |
| `blend_transatlantic` | Heart 50% + Emma 50% | Mid-Atlantic quality |

The blend recipe is included in the TTS chunk cache key — changing the weights
invalidates only that voice's cached audio; other voices are unaffected.

## Auditioning voices

```bash
# Render a short audition WAV for every voice
vorpal voices --sample

# Use a passage from your actual book
vorpal voices --sample --text "The army is not merely a fighting force; it is also a school."
```

WAVs are written to `voice_samples/` in the current directory.
Pre-rendered audition clips for three voices are in `samples/clips/`.

## Choosing a voice

**Political, military, and historical non-fiction** — `blend_deep_steady`.
Authority without harshness. Used for the 19-hour Trotsky production.

**Literary fiction, contemporary** — `af_heart` (default) or `blend_warm_bright`.
Heart is the most versatile voice; the blend adds precision without losing warmth.

**British classics and period fiction** — `bm_george` or `bf_emma`.
`blend_transatlantic` for mid-Atlantic material.

**Science fiction and speculative fiction** — `am_echo` or `af_nova`.
Precise, neutral delivery suits speculative content.

**Theatrical plays** — vorpal casts these automatically. The `--voice` flag
sets the narrator/stage-directions voice; characters are assigned from the
rest of the suite. See {doc}`plays`.

**When unsure** — run `--sample` with a passage from your book and trust your ear.

## Using a voice in a build

```bash
vorpal build book.epub --voice blend_deep_steady
```

The voice is recorded in `book.json` under `settings.voice`. Rebuilding with a
different voice only re-synthesises — extraction and chapter detection are skipped.

## Adding a custom blend

Edit `vorpal/tts/voices.py` and add an entry to `VOICE_REGISTRY`:

```python
"blend_my_voice": {
    "blend": {"am_fenrir": 0.4, "bm_george": 0.6},
    "description": "Fenrir 40% + George 60% — transatlantic male",
},
```

Run `vorpal voices` to confirm it appears, then use it with `--voice blend_my_voice`.
