"""Kokoro approximation layer — tone realization without an API key.

Maps the tone vocabulary onto Kokoro's available control surface:
  speed per tone + paragraph-pause scaling.

These are approximations, not direct style control — the acoustic delta
is measurable (duration/energy differ by the speed multiplier) but subtle.
The effectiveness gate (Phase 8) decides whether it's good enough.
"""

from typing import Optional

import numpy as np

from .base import TTSEngine


# Per-tone speed multipliers (applied to the user's --speed base)
TONE_SPEED: dict = {
    "neutral":    1.00,
    "somber":     0.88,  # slower, heavier
    "tense":      1.10,  # clipped urgency
    "warm":       0.95,  # relaxed
    "wry":        1.00,  # neutral pacing; irony is delivery, not speed
    "excited":    1.12,  # forward energy
    "urgent":     1.15,  # fastest
    "reflective": 0.90,  # unhurried
}

# Dialogue speed shift — conservative, barely perceptible; only active when
# dialogue_style="subtle" is configured on the engine.
DIALOGUE_SPEED: float = 0.97

# Per-tone pause-length multipliers (applied to pause_after_ms)
TONE_PAUSE_SCALE: dict = {
    "neutral":    1.00,
    "somber":     1.30,
    "tense":      0.75,
    "warm":       1.10,
    "wry":        1.00,
    "excited":    0.80,
    "urgent":     0.65,
    "reflective": 1.25,
}


class KokoroApproxEngine(TTSEngine):
    """Wraps KokoroEngine with per-tone speed adjustments.

    inner_engine: the wrapped engine (defaults to KokoroEngine; can be set to
    MockEngine for tests). Accepts any TTSEngine — the approximation layer is
    independent of the inner engine.
    """

    name = "kokoro_approx"
    sample_rate = 24000
    max_chunk_chars = 400
    supported_tones = tuple(TONE_SPEED.keys())
    cost_per_1k_chars: float = 0.0

    def __init__(self, voice: str = "af_heart", speed: float = 1.0,
                 params: Optional[dict] = None,
                 inner_engine: Optional[TTSEngine] = None,
                 dialogue_style: Optional[str] = None):
        self._base_speed = float(speed)
        self.dialogue_style = dialogue_style
        if inner_engine is not None:
            self._inner = inner_engine
        else:
            from .kokoro_engine import KokoroEngine
            self._inner = KokoroEngine(
                voice=voice if params is None else "af_heart",
                speed=speed,
                params=params,
            )

    @property
    def voice(self):
        return getattr(self._inner, "voice", None)

    @property
    def speed(self):
        return self._base_speed

    @property
    def voice_cache_key(self) -> str:
        inner_key = getattr(self._inner, "voice_cache_key", None) or \
                    getattr(self._inner, "voice", "unknown")
        return f"approx_{inner_key}"

    def scaled_pause(self, pause_ms: int, tone: Optional[str]) -> int:
        """Return pause duration scaled for the given tone."""
        scale = TONE_PAUSE_SCALE.get(tone or "neutral", 1.0)
        return max(0, int(pause_ms * scale))

    def synthesize(self, text: str, tone: Optional[str] = None,
                   is_dialogue: bool = False):
        """Synthesize with tone-adjusted speed and optional dialogue shift."""
        tone_speed = TONE_SPEED.get(tone or "neutral", 1.0)
        dlg_shift = DIALOGUE_SPEED if (is_dialogue and self.dialogue_style == "subtle") else 1.0
        actual_speed = self._base_speed * tone_speed * dlg_shift

        inner = self._inner
        old_speed = getattr(inner, "speed", actual_speed)
        try:
            inner.speed = actual_speed
            return inner.synthesize(text, tone=None)
        finally:
            inner.speed = old_speed


def acoustic_delta(audio_a: np.ndarray, audio_b: np.ndarray,
                   sample_rate: int) -> dict:
    """Measure acoustic distance between two renderings of the same text.

    Returns a dict with:
      rms_diff: relative RMS energy difference (0–1)
      dur_diff: relative duration difference (0–1)
      passes:   True if either metric exceeds the 5 % threshold
    """
    if len(audio_a) == 0 or len(audio_b) == 0:
        raise ValueError("acoustic_delta requires non-empty audio arrays")
    rms_a = float(np.sqrt(np.mean(audio_a ** 2)))
    rms_b = float(np.sqrt(np.mean(audio_b ** 2)))
    dur_a = len(audio_a) / max(sample_rate, 1)
    dur_b = len(audio_b) / max(sample_rate, 1)

    rms_diff = abs(rms_a - rms_b) / max(rms_a, rms_b, 1e-9)
    dur_diff = abs(dur_a - dur_b) / max(dur_a, dur_b, 1e-9)

    rms_r = round(rms_diff, 4)
    dur_r = round(dur_diff, 4)
    return {
        "rms_diff": rms_r,
        "dur_diff": dur_r,
        "passes": bool(rms_r >= 0.05 or dur_r >= 0.05),
    }
