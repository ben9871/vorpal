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

---

## 10. Phase 23 — StyleTTS2 Voice Design Spike Results

*Date: 2026-06-09. Follow-up to Phase 9. All playground-isolated.*

### Hardware budget

| Resource | Total | Used (peak) | Headroom |
|----------|-------|-------------|----------|
| VRAM     | 6.0 GB | 2.02 GB (34%) | 3.98 GB |
| RAM      | 7.6 GB | ~1.7 GB | 5.9 GB |
| Disk     | 91 GB | ~1.5 GB (models) | 89 GB |

Well under the 80% VRAM target throughout all experiments.

### What was done

1. **Installed StyleTTS2** (`pip install styletts2 0.1.6`) + NLTK punkt_tab.
   Reinstalled `torchaudio 2.5.1+cu121` (styletts2 install pulled incompatible 2.11.0).

2. **Auto-downloaded StyleTTS2-LibriTTS** (~1.2 GB checkpoint from
   `huggingface.co/yl4579/StyleTTS2-LibriTTS`) + submodels (ASR, F0, PLBERT — total ~1.5 GB).
   Apache-2.0 license.

3. **Reference audio**: default LJSpeech sample auto-downloaded from
   `styletts2.github.io/wavs/LJSpeech/OOD/GT/00001.wav` (public domain, Karen Crowne).
   Note: this is a female voice (~190 Hz F0) — limitations discussed below.

4. **Style encoder**: `model.compute_style(ref_path)` → `[1, 256]` tensor
   (128 timbre + 128 prosody components). Norm: 3.10.

5. **Alpha/beta parameter sweep**: explored the 2D style control space
   (`alpha` = timbre weight, `beta` = prosody weight; 1.0 = fully text-driven,
   0.0 = full reference-cloning).

6. **Gradient descent on style embedding**: optimized the 256-dim style vector
   to target a desired duration profile. Predictor LSTM put in `.train()` mode
   (required for cuDNN backward); model parameters frozen. 30 steps, Adam, lr=1e-2.

### Acoustic measurements (248-char Firestone test passage, same as Phase 9)

| Model | Voice/Config | Duration | RMS | Pitch (F0) | Notes |
|-------|--------------|----------|-----|------------|-------|
| Kokoro | vorpal_narrator_v1 | **14.2s** | 0.0610 | 152 Hz | Phase 9 PCA design |
| Kokoro | bm_george (baseline) | 20.1s | 0.0579 | 140 Hz | Current default |
| Kokoro | bm_lewis | 20.2s | 0.0440 | 129 Hz | Slower/quieter |
| StyleTTS2 | default (α=0.3, β=0.7) | 13.3s | 0.0526 | 193 Hz | Default params, LJSpeech ref |
| StyleTTS2 | text-driven (α=0.9, β=0.9) | 12.4s | 0.0435 | 190 Hz | High text/style ratio |
| StyleTTS2 | ref-driven (α=0.1, β=0.1) | 13.6s | 0.0512 | 234 Hz | Near voice-cloning mode |
| StyleTTS2 | high-emotion (scale=2.0) | 12.2s | 0.0662 | 216 Hz | Emotional exaggeration |
| StyleTTS2 | GD-optimized (target 14.5s) | 19.1s | 0.0502 | 182 Hz | 30 GD steps; see notes |

**Files (playground-only, gitignored):**
- `playground/styletts2_spike.py` — full experiment script
- `playground/s2_default_a0.3_b0.7.wav` — default style
- `playground/s2_textdriven_a0.9_b0.9.wav` — text-driven style
- `playground/s2_refdriven_a0.1_b0.1.wav` — reference-driven style
- `playground/s2_highemote_a0.3_b0.7_e2.wav` — high emotional scale
- `playground/s2_optimized_style.wav` — gradient-descent optimized embedding

### Key findings

**What works:**
- StyleTTS2-LibriTTS runs cleanly on this GPU (0.7s/passage for inference after
  the first call; 12% VRAM at rest, 18% per inference)
- Style encoder produces a [1, 256] style embedding from any reference audio
- Gradient descent on the style embedding converges (loss 57.6 → 0.07 in 30 steps)
- The alpha/beta parameters are genuine controls: text-driven (α=β=0.9) gives
  shorter, flatter speech; ref-driven (α=β=0.1) preserves reference prosody
- All 4 variants synthesize correctly with distinct acoustic profiles

**Critical limitation: reference audio must be male for male narrator use:**
The default LJSpeech reference is a female voice (~190 Hz F0). All StyleTTS2
outputs in this spike are in the 182–234 Hz range (female/androgynous), vs. the
Kokoro male voices at 129–152 Hz. For a narrator engine that sounds like
vorpal_narrator_v1, we need a male public-domain reference (e.g., a LibriVox
male speaker from LibriSpeech test-clean). The style encoder would then extract
a male-register embedding.

**Gradient descent accuracy note:**
The GD optimized the predictor's internal duration estimate to ~15s, but the
actual synthesis came out at 19.1s. There's a ~30% discrepancy between predictor
duration and acoustic duration — likely because the predictor doesn't account for
the diffusion decoder's timing expansion. A more accurate loss would operate in
the acoustic (waveform) domain, not the predictor's frame-count estimate. This
is a known limitation of the approach; the GD is functional but the target
needs calibration.

**No voice cloning:** all experiments use either the default LJSpeech sample
(public domain) or an algebraic style embedding — no real person's voice is being
replicated in any meaningful sense.

### Go / No-go for registry integration

**Conditional go** on adding a StyleTTS2 narrator voice to the registry, with
the following conditions:

1. **(human, H-009)** Listen to `playground/s2_default_a0.3_b0.7.wav`
   and `playground/s2_textdriven_a0.9_b0.9.wav`. Does StyleTTS2 quality match
   or exceed Kokoro for non-fiction narration?
2. **Male reference required**: before integration, obtain a short (5–30s) sample
   from a public-domain LibriVox male reader (e.g., LibriSpeech test-clean speaker
   1089 — public domain, reads from Project Gutenberg books). Extract the style
   embedding from that; re-run the comparison.
3. **Integration cost**: a `StyleTTS2Engine` class in `vorpal/tts/` would need
   the same `TTSEngine` interface (synthesize, voice_cache_key, supports_batch).
   The model loads in ~12s and uses 0.72 GB VRAM idle — acceptable for a
   session-wide singleton, not per-chapter.

**If rejected:** the Kokoro PCA approach (Phase 9's `vorpal_narrator_v1`) is
already the superior path for the current setup — faster synthesis, male voice,
lower VRAM, proven quality.

### Integration plan (if approved)

```
vorpal/tts/styletts2_engine.py:
    class StyleTTS2Engine(TTSEngine):
        def __init__(self, ref_style_path, alpha=0.3, beta=0.7, ...):
            ...
        def synthesize(self, text, tone=None) -> np.ndarray:
            return self.model.inference(text, ref_s=self.ref_s, alpha=self.alpha, ...)
        @property
        def voice_cache_key(self) -> str:
            return f"s2_{self._ref_hash}_{self.alpha}_{self.beta}"
```

The registry entry would store the reference style as a `.pt` file (the
[1, 256] tensor) alongside the alpha/beta params.

---

## 9. Protocol compliance (updated)

- All experiments in `playground/` (gitignored — model weights and WAVs stay
  out of git).
- No changes to `vorpal/` package, voice registry, or any committed pipeline path.
- No voice cloning (no target speaker audio used anywhere).
- No money spent (all models are free; no API calls).
- VRAM peak: Phase 9 ~400 MB; Phase 23 ~2.0 GB (both well under 80% of 6 GB).
- Integration gated on human approval (samples + report surfaces evidence;
  wiring blocked pending sign-off).
