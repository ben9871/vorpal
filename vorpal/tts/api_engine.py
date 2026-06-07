"""OpenAI TTS API engine — tone-capable narration via instruction strings.

Uses gpt-4o-mini-tts for instruction-following synthesis (tone steering).
Falls back to tts-1 when no tone is requested (cheaper, $15/1M chars).

Credential: VORPAL_OPENAI_KEY (or OPENAI_API_KEY as fallback).

Cost:
  tts-1:           $15 / 1M chars → 0.000015 $/char
  gpt-4o-mini-tts: ~$15 / 1M chars (same tier — confirm at billing page)

All three values are class attributes so estimate_synth_cost() can read them
without instantiating the engine.
"""

import io
import os
import struct
from typing import Optional

import numpy as np

from .base import TTSEngine


def _resolve_openai_key() -> Optional[str]:
    return (
        os.environ.get("VORPAL_OPENAI_KEY")
        or os.environ.get("OPENAI_API_KEY")
    )


def _wav_bytes_to_array(wav_bytes: bytes) -> Optional[np.ndarray]:
    """Decode a WAV byte payload to a float32 numpy array."""
    buf = io.BytesIO(wav_bytes)
    # Read RIFF header
    riff, size, wave = struct.unpack_from("<4sI4s", buf.read(12))
    if riff != b"RIFF" or wave != b"WAVE":
        raise ValueError("Response is not a valid WAV file")
    # Find 'data' chunk; initialize fmt fields so they're defined if data comes first
    bits: int = 0
    channels: int = 1
    sample_rate: int = 0
    while True:
        hdr = buf.read(8)
        if len(hdr) < 8:
            raise ValueError("No data chunk found in WAV response")
        chunk_id, chunk_size = struct.unpack_from("<4sI", hdr)
        chunk_data = buf.read(chunk_size)
        if chunk_id == b"fmt ":
            audio_fmt, channels, sample_rate, _, _, bits = struct.unpack_from(
                "<HHIIHH", chunk_data
            )
            if audio_fmt != 1:
                raise ValueError(f"Unsupported WAV format {audio_fmt} (expected PCM=1)")
        elif chunk_id == b"data":
            if bits == 0:
                raise ValueError("WAV fmt chunk missing before data chunk")
            if bits == 16:
                raw = np.frombuffer(chunk_data, dtype="<i2").astype("float32") / 32768.0
            elif bits == 32:
                raw = np.frombuffer(chunk_data, dtype="<f4")
            else:
                raise ValueError(f"Unsupported bit depth {bits}")
            if channels > 1:
                # Stereo → mono by averaging
                raw = raw.reshape(-1, channels).mean(axis=1)
            return raw


class APIEngine(TTSEngine):
    """OpenAI TTS adapter — instruction-following, tone-aware.

    Credentials: set VORPAL_OPENAI_KEY (or OPENAI_API_KEY) in your environment.

    Tone steering: ``supported_tones`` lists the tags the engine acts on; each
    maps to an instruction string appended to the OpenAI request.  Neutral and
    unrecognised tones use a plain "clear, neutral" instruction.
    """

    name = "openai"
    sample_rate = 24000
    max_chunk_chars = 4096  # OpenAI TTS supports longer inputs
    supported_tones = ("somber", "tense", "warm", "wry", "neutral")
    cost_per_1k_chars: float = 15.0 / 1000  # $15 per 1M chars = $0.015 per 1k

    # When tone hints are active, use the instruction-capable model
    _TONAL_MODEL = "gpt-4o-mini-tts"
    _BASE_MODEL = "tts-1"
    _API_URL = "https://api.openai.com/v1/audio/speech"

    _TONE_INSTRUCTIONS: dict = {
        "somber": (
            "Speak in a somber, reflective tone — measured and unhurried, "
            "with a sense of weight. No forced solemnity; let the words carry it."
        ),
        "tense": (
            "Speak with controlled urgency — slightly clipped delivery, "
            "forward-leaning energy, as if each sentence matters."
        ),
        "warm": (
            "Speak in a warm, inviting tone — relaxed, resonant, approachable, "
            "like telling a story to a friend."
        ),
        "wry": (
            "Speak with dry wit — a hint of irony, understated delivery. "
            "The humor is in the restraint."
        ),
        "neutral": (
            "Speak in a clear, neutral tone — natural, unhurried, "
            "letting the text stand on its own."
        ),
    }

    def __init__(self, voice: str = "alloy", speed: float = 1.0,
                 model: Optional[str] = None):
        self.voice = voice
        self.speed = speed
        self._model_override = model  # None → auto-select by tone

    @property
    def voice_cache_key(self) -> str:
        return f"openai_{self.voice}"

    def synthesize(self, text: str, tone: Optional[str] = None):
        key = _resolve_openai_key()
        if not key:
            raise RuntimeError(
                "OpenAI TTS requires VORPAL_OPENAI_KEY — see CLAUDE.md §Credentials"
            )

        instruction = self._TONE_INSTRUCTIONS.get(tone or "neutral",
                                                   self._TONE_INSTRUCTIONS["neutral"])
        has_tone = tone and tone != "neutral"
        model = self._model_override or (self._TONAL_MODEL if has_tone else self._BASE_MODEL)

        payload: dict = {
            "model": model,
            "input": text,
            "voice": self.voice,
            "response_format": "wav",
            "speed": max(0.25, min(4.0, self.speed)),
        }
        if has_tone or model == self._TONAL_MODEL:
            payload["instructions"] = instruction

        try:
            import requests as _req
        except ImportError:
            raise RuntimeError(
                "The 'requests' package is required for APIEngine "
                "(pip install requests)"
            )

        resp = _req.post(
            self._API_URL,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=120,
        )
        if resp.status_code != 200:
            body = resp.text[:400]
            raise RuntimeError(
                f"OpenAI TTS API error {resp.status_code}: {body}"
            )

        return _wav_bytes_to_array(resp.content)
