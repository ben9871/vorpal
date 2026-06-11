"""Piper TTS engine — fast VITS-based synthesis for draft mode.

Piper (https://github.com/rhasspy/piper) is a fast, CPU-friendly TTS engine.
It is an opt-in dependency: the engine degrades gracefully when the `piper`
binary is not on PATH or no model is configured.

Typical usage:
    echo "Hello world" | piper --model en_US-amy-low.onnx --output_file out.wav

Model discovery order:
  1. VORPAL_PIPER_MODEL environment variable (path to .onnx file)
  2. ``~/.local/share/vorpal/piper/*.onnx`` (first match)
  3. ``~/.local/share/piper-tts/*.onnx`` (first match — common Piper install path)

Piper "low" models (~15 MB) are fast but lower quality than Kokoro.
They exist solely to make ``--draft`` actually fast on CPU.
Never use PiperEngine for the final audiobook build.
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np

from .base import TTSEngine


def _find_piper_binary() -> Optional[str]:
    """Return the path to the `piper` binary, or None if not on PATH."""
    return shutil.which("piper")


def _find_piper_model() -> Optional[Path]:
    """Return the first usable Piper model path, or None if none found."""
    # 1. Explicit env override
    env_path = os.environ.get("VORPAL_PIPER_MODEL")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p

    # 2. Vorpal-managed location
    vorpal_dir = Path.home() / ".local" / "share" / "vorpal" / "piper"
    if vorpal_dir.exists():
        models = list(vorpal_dir.glob("*.onnx"))
        if models:
            return sorted(models)[0]

    # 3. Common Piper install location
    piper_dir = Path.home() / ".local" / "share" / "piper-tts"
    if piper_dir.exists():
        models = list(piper_dir.glob("*.onnx"))
        if models:
            return sorted(models)[0]

    return None


def is_piper_available() -> bool:
    """Return True if both the piper binary and a model are discoverable."""
    return bool(_find_piper_binary()) and bool(_find_piper_model())


class PiperEngine(TTSEngine):
    """Fast VITS-based TTS via the piper CLI.

    Intended for ``--draft`` mode on CPU-only machines where Kokoro synthesis
    is impractically slow.  Quality is lower than Kokoro; use Kokoro for final
    builds.

    Raises RuntimeError on construction if piper is not available or no model
    is found — callers should check is_piper_available() first.
    """

    name = "piper"
    sample_rate = 22050   # typical Piper output; overridden from actual WAV
    max_chunk_chars = 500
    supported_tones = ()
    supports_batch = False
    cost_per_1k_chars: float = 0.0

    def __init__(self, model_path: Optional[str] = None, speed: float = 1.0):
        binary = _find_piper_binary()
        if not binary:
            raise RuntimeError(
                "piper binary not found on PATH. "
                "Install Piper (https://github.com/rhasspy/piper) or "
                "skip --draft for the standard Kokoro draft."
            )
        self._binary = binary

        if model_path:
            mp = Path(model_path)
            if not mp.exists():
                raise RuntimeError(f"Piper model not found: {model_path}")
            self._model = mp
        else:
            mp = _find_piper_model()
            if mp is None:
                raise RuntimeError(
                    "No Piper model found. Set VORPAL_PIPER_MODEL=<path/to/model.onnx> "
                    "or place a model in ~/.local/share/vorpal/piper/."
                )
            self._model = mp

        self.speed = float(speed)
        self.voice = f"piper:{self._model.stem}"

    @property
    def voice_cache_key(self) -> str:
        return f"piper_{self._model.stem}"

    def synthesize(self, text: str, tone: Optional[str] = None,
                   is_dialogue: bool = False) -> Optional[np.ndarray]:
        """Synthesize text using the piper CLI.

        Writes to a temp WAV, reads it back as float32.  Tone hints are
        ignored (Piper does not support instruction-based tone steering).
        """
        import wave

        if not text.strip():
            return None

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            cmd = [
                self._binary,
                "--model", str(self._model),
                "--output_file", tmp_path,
            ]
            proc = subprocess.run(
                cmd,
                input=text.encode("utf-8"),
                capture_output=True,
                timeout=120,
            )
            if proc.returncode != 0:
                err = proc.stderr.decode("utf-8", errors="replace")[:400]
                raise RuntimeError(f"piper exited {proc.returncode}: {err}")

            with wave.open(tmp_path, "rb") as wf:
                self.sample_rate = wf.getframerate()
                frames = wf.readframes(wf.getnframes())
                n_channels = wf.getnchannels()
                sampwidth = wf.getsampwidth()

            if sampwidth == 2:
                pcm = np.frombuffer(frames, dtype="<i2").astype("float32") / 32768.0
            elif sampwidth == 4:
                pcm = np.frombuffer(frames, dtype="<f4")
            else:
                raise RuntimeError(f"Unsupported Piper sample width: {sampwidth}")

            if n_channels > 1:
                pcm = pcm.reshape(-1, n_channels).mean(axis=1)

            return pcm
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
