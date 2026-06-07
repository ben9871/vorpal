"""Kokoro TTS engine — the default (and currently only) engine."""

from typing import Optional

from .base import TTSEngine

KOKORO_VOICES = [
    "af_heart", "af_nova", "af_sky",
    "am_echo", "am_michael", "am_fenrir",
    "bf_emma", "bm_george",
]


class KokoroEngine(TTSEngine):
    name = "kokoro"
    sample_rate = 24000
    max_chunk_chars = 400
    supported_tones = ()   # Kokoro ignores tone hints

    def __init__(self, voice: str = "af_heart", speed: float = 1.0):
        self.voice = voice
        self.speed = speed
        self._pipeline = None

    def _load(self):
        if self._pipeline is None:
            from kokoro import KPipeline
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
            print(f"\n  Loading Kokoro model (first run ~300MB) on {device.upper()}...")
            self._pipeline = KPipeline(lang_code="a")
        return self._pipeline

    def synthesize(self, text: str, tone: Optional[str] = None):
        import numpy as np
        import torch

        pipeline = self._load()
        parts = []
        with torch.no_grad():
            for _, _, audio in pipeline(text, voice=self.voice, speed=self.speed):
                if audio is not None and len(audio) > 0:
                    parts.append(audio)
        if not parts:
            return None
        parts = [p.cpu().numpy() if hasattr(p, "cpu") else p for p in parts]
        return np.concatenate(parts)
