"""Mock TTS engine for unit tests.

Produces deterministic, tone-aware audio (different tones → different sine
frequencies → testable acoustic deltas) without loading any model.
Used in tests that verify cost/retry/tone-pass-through logic without GPU.

fail_on: if set, synthesize() raises RuntimeError when the text contains that
string — lets tests drive the retry/abort policy.
"""

import math
from typing import Optional

import numpy as np

from .base import TTSEngine


class MockEngine(TTSEngine):
    name = "mock"
    sample_rate = 24000
    max_chunk_chars = 400
    supported_tones = ("somber", "tense", "warm", "wry", "neutral")
    cost_per_1k_chars: float = 0.0   # local/free
    supports_batch = True

    # Each tone maps to a distinct frequency (Hz); 0 → silence
    _TONE_FREQ: dict = {
        None: 0,
        "neutral": 0,
        "somber": 110,   # A2
        "tense": 220,    # A3
        "warm": 330,     # E4
        "wry": 440,      # A4
    }

    def __init__(self, voice: str = "mock_default", speed: float = 1.0,
                 fail_on: Optional[str] = None):
        self.voice = voice
        self.speed = speed
        self.fail_on = fail_on

    @property
    def voice_cache_key(self) -> str:
        return self.voice

    def synthesize(self, text: str, tone: Optional[str] = None):
        if self.fail_on and self.fail_on in text:
            raise RuntimeError(
                f"MockEngine: deliberately failing — text contains {self.fail_on!r}"
            )
        freq = self._TONE_FREQ.get(tone, 0)
        # Duration proportional to text length; clamped to a minimum of 0.1s
        duration_s = max(0.1, len(text) / max(1.0, 10.0 * self.speed))
        n = int(self.sample_rate * duration_s)
        if freq == 0:
            return np.zeros(n, dtype="float32")
        t = np.arange(n, dtype="float32") / self.sample_rate
        return (0.1 * np.sin(2.0 * math.pi * freq * t)).astype("float32")

    def synthesize_batch(self, texts, tone=None):
        """Sequential batch: MockEngine doesn't gain from true batching."""
        return [self.synthesize(t, tone=tone) for t in texts]
