# Phase 9 — In-House Voice Spike Report

*Date: 2026-06-07. Hardware: RTX 4050 Laptop GPU (6 GB VRAM), 7.6 GB RAM.
All experiments playground-isolated (`playground/`). Nothing was modified in
the shipped `vorpal/` package.*

---

## 1. Goal

Design a "house narrator" voice for vorpal — distinct from any single existing
Kokoro voice — without voice cloning (CLAUDE.md: "no voice cloning, ever").

---

## 2. Hardware budget

| Resource | Total | Used (peak) | Headroom |
|----------|-------|-------------|----------|
| VRAM     | 6.1 GB | 0.34 GB (KokoroModel on GPU) | 5.7 GB |
| RAM      | 7.6 GB | ~1.5 GB | 6.1 GB |
| Disk     | — | ~15 MB (WAVs + .pt) | — |

Kokoro-82M itself is only 327 MB. Inference used <400 MB VRAM. Hardware
budget was never a concern for this approach.

---

## 3. Architecture analysis

Kokoro-82M is a **pure decoder** (text + style tensor → audio). It does NOT
have an audio encoder. This means:

- **Zero-shot style transfer from audio is architecturally impossible** with
  this model. There is no path from "record a voice → Kokoro voice tensor."
- The speaker representation is an **external [510, 1, 256] float32 tensor**
  loaded from `.pt` files. Any valid tensor of this shape can be used as a voice.
- The existing "blend" mechanism in vorpal's registry (weighted sum of voice
  tensors) is the intended customization API.

**Consequence:** the only ethical, in-house voice design path with Kokoro is
algebraic manipulation of existing voice tensors. This is distinct from voice
cloning because (a) it doesn't use any specific person's audio, and (b) the
output is a novel point in the voice embedding space.

---

## 4. Voice embedding PCA

Analyzed the 16 English male/neutral voices (am_* + bm_*) in the Kokoro-82M
repository. Each voice is a [510, 1, 256] tensor; I used the mean over the 510
style-token dimension to get a [256] summary embedding.

PCA of the 16×256 matrix:

| Components | Variance explained |
|------------|-------------------|
| Top-1      | 26.3%             |
| Top-2      | 38.4%             |
| Top-3      | 48.1%             |
| Top-5      | 61.8%             |
| Top-10     | 79.4%             |

The voice space has moderate intrinsic dimensionality (~10 components for 80%
variance). The first two PCs account for ~38% — enough to navigate meaningfully.

### What the PCs control (empirically, from synthesis tests)

| Axis | Negative end | Positive end |
|------|-------------|-------------|
| PC1 | Faster speech, slightly higher pitch, quieter | Slower, slightly lower pitch, louder/more forward |
| PC2 | Faster + deep (82–117 Hz) | Slower + higher pitch (398 Hz — occasionally noisy) |

---

## 5. Designed narrator voice: `vorpal_narrator_v1`

**Recipe:** mean of the 10 English male voices + 0.5·S₀·PC1 − 1.5·S₁·PC2

This pushes away from deep/fast region (−PC2) and slightly toward the
forward/louder direction (+PC1).

**Acoustic comparison (test passage: 248 chars, Firestone Ch.1 excerpt):**

| Voice | Duration | RMS | Pitch est. | Notes |
|-------|----------|-----|------------|-------|
| `vorpal_narrator_v1` | **14.2s** | **0.0610** | **152 Hz** | Designed voice |
| `bm_george` (baseline) | 20.1s | 0.0579 | 140 Hz | Current default narrator |
| `bm_lewis` | 20.2s | 0.0440 | 129 Hz | Quieter, slower |

`vorpal_narrator_v1` is **29% faster** and **5% louder** than bm_george, with
a slightly higher fundamental frequency (152 vs 140 Hz — tenor vs baritone).
The character profile: *clear, confident, efficient* — less stately than george,
more direct.

**Cosine similarity to existing voices:**
The designed voice has highest similarity to bm_daniel (0.81) and bm_george
(0.79) — it sits within the British/American male cluster but at a novel
position not identical to any single source voice.

**Files (playground-only, gitignored):**
- `playground/vorpal_narrator_v1.pt` — the voice tensor (510×1×256, float32)
- `playground/final_vorpal_narrator_v1.wav` — comparison sample
- `playground/final_bm_george_baseline.wav` — bm_george comparison
- `playground/final_bm_lewis_baseline.wav` — bm_lewis comparison

---

## 6. Approaches surveyed

| Approach | VRAM needed | Training data | Voice cloning? | Status |
|----------|-------------|--------------|----------------|--------|
| Kokoro PCA blend | <400 MB | None | No | **Done** (this spike) |
| StyleTTS2 inference | ~4-5 GB | Public-domain audio | No (if used for design) | Feasible; not installed |
| StyleTTS2 fine-tune | 5-6 GB | 30 min labeled audio | Possible if careful | Marginal on 6 GB |
| Chatterbox (Resemble, MIT) | ~2 GB | Target speaker audio | Yes (blocked by CLAUDE.md) | Blocked |
| F5-TTS (E2 TTS) | ~4 GB | Target speaker audio | Yes (blocked) | Blocked |
| Piper VITS fine-tune | CPU-feasible | 1+ hour labeled audio | No (if source is public-domain) | Not explored |

### StyleTTS2 feasibility note

StyleTTS2 (`yl4579/StyleTTS2-LibriTTS`, ~1.2 GB) has both an encoder and a
decoder. The encoder maps mel-spectrogram → style vector; the decoder maps
(text, style) → audio — same as Kokoro but with the encoding path. This would
allow designing a voice by iterating on a *target acoustic profile* (e.g.,
public-domain LibriVox speaker) and then fine-tuning only the style embedding.

Not installed; would take ~30 min to set up and verify on this GPU. Deferred
for a follow-up session.

---

## 7. What cannot be done with Kokoro alone

1. **True novel voices** outside the convex span of existing voices: PCA offsets
   create new combinations but are bounded by the existing voice manifold. A
   truly fresh timbre would require either a different model architecture or
   training.

2. **Voice fine-tuning**: Kokoro-82M does not expose a training API. The model
   weights are fixed; only the style tensor can be varied. Fine-tuning the
   decoder would require the full training codebase (styletts2-kokoro or similar).

3. **Zero-shot from target audio**: no encoder → can't extract a style vector
   from audio. Any path from "record a sample → voice tensor" is architecturally
   absent in Kokoro-82M.

---

## 8. Recommendation for integration

### Go / No-go

**Conditional go** on adding `vorpal_narrator_v1` to the registry.

**Conditions:**
1. **(human)** Listening comparison: play `playground/final_vorpal_narrator_v1.wav`
   vs `playground/final_bm_george_baseline.wav`. Is the designed voice distinctly
   different and better for a non-fiction narrator? Does it sound natural?
2. **(human)** Character sign-off: confirm the voice is suitable for the intended
   use case (academic/literary non-fiction narration).
3. **(human)** Name the voice — suggest `am_scholar` or `am_rector` to convey the
   character profile.

**If approved:**
```python
# In vorpal/tts/voices.py, add to VOICE_REGISTRY:
VoiceEntry(
    id="am_rector",
    display_name="Rector",
    description="Designed narrator: clear, forward, efficient; male baritone-tenor",
    engine="kokoro",
    params={"voice_pt": "playground/vorpal_narrator_v1.pt"},  # path TBD after promotion
)
```
The `.pt` file would be copied to `vorpal/tts/voices/am_rector.pt` (checked in,
or hosted on HuggingFace alongside the other voices).

**If rejected:** the existing `bm_george` + `bm_daniel` blend in the registry
already covers the "clear male narrator" use case.

### Future spike option: StyleTTS2

A follow-up session could:
1. Download StyleTTS2-LibriTTS (~1.2 GB, Apache-2.0 license)
2. Pick a public-domain LibriVox reader with a desired acoustic profile
3. Use StyleTTS2's encoder to extract a reference style embedding
4. Optimize that embedding (gradient descent on reconstruction loss, no decoder
   retraining) to design a character-level style
5. Convert back to Kokoro format (style dimensions are different; would need
   mapping or separate inference pipeline)

This is non-trivial but feasible on 6 GB VRAM in 2-3 hours. Decision should
follow the human verdict on the PCA approach first.

---

## 9. Protocol compliance

- All experiments in `playground/` (gitignored — model weights and WAVs stay
  out of git).
- No changes to `vorpal/` package, voice registry, or any committed pipeline path.
- No voice cloning (no target speaker audio used anywhere).
- No money spent (Kokoro is local; no API calls).
- VRAM peak: ~400 MB (well under 80% of 6 GB = 4.9 GB target).
- Integration gated on human approval (this report surfaces samples +
  recommendation; wiring blocked pending sign-off).
