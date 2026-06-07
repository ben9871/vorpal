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
    supported_tones = ()

    def __init__(self, voice: str = "af_heart", speed: float = 1.0,
                 params: Optional[dict] = None):
        """Construct a Kokoro engine.

        Pass either the legacy voice string + speed, or a VoiceEntry params
        dict (from the registry) which may contain a blend recipe.  When
        params is given, speed still overrides any speed in the params dict so
        the --speed CLI flag always wins.
        """
        if params is not None:
            self._params = dict(params)
            # Single-voice params carry {"voice": "af_heart"}; blend params
            # carry {"blend": {"af_heart": 0.6, "af_nova": 0.4}}.
            self.voice = params.get("voice") if "blend" not in params else None
        else:
            self.voice = voice
            self._params = {"voice": voice}
        self.speed = float(speed)
        self._pipeline = None
        self._blend_tensor = None   # lazily computed on first synthesis

    @property
    def voice_cache_key(self) -> str:
        """Stable string for the voice component of chunk-cache keys.

        Single voices return the voice name; blend voices return a compact
        SHA-256 of the blend recipe so that editing recipe weights correctly
        invalidates cached audio.
        """
        from .voices import _params_cache_key
        return _params_cache_key(self._params)

    def _load(self):
        if self._pipeline is None:
            from kokoro import KPipeline
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
            print(f"\n  Loading Kokoro model (first run ~300MB) on {device.upper()}...")
            self._pipeline = KPipeline(lang_code="a")
        return self._pipeline

    def _get_voice_arg(self):
        """Return the voice argument to pass to the Kokoro pipeline.

        Single voices: returns the string name.
        Blends: returns a pre-computed FloatTensor (cached after first call).
        """
        if "blend" not in self._params:
            return self.voice

        if self._blend_tensor is None:
            import torch
            pipeline = self._pipeline   # already loaded by _load()
            recipe = self._params["blend"]
            parts = []
            weights = []
            for voice_name, weight in recipe.items():
                tensor = pipeline.load_voice(voice_name)
                parts.append(tensor)
                weights.append(float(weight))
            total = sum(weights)
            # Weighted sum with L1 normalisation
            blend = sum(t * (w / total) for t, w in zip(parts, weights))
            self._blend_tensor = blend
        return self._blend_tensor

    def synthesize(self, text: str, tone: Optional[str] = None):
        import numpy as np
        import torch

        pipeline = self._load()
        voice_arg = self._get_voice_arg()
        parts = []
        with torch.no_grad():
            for _, _, audio in pipeline(text, voice=voice_arg, speed=self.speed):
                if audio is not None and len(audio) > 0:
                    parts.append(audio)
        if not parts:
            return None
        parts = [p.cpu().numpy() if hasattr(p, "cpu") else p for p in parts]
        return np.concatenate(parts)
