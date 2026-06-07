"""TTS engine interface.

Engines synthesize one text chunk at a time and declare their sample rate,
maximum chunk length, and which tone hints they act on.
Voice cloning is out of scope by design (docs/02-product-vision.md).
"""

from abc import ABC, abstractmethod
from typing import Optional


class TTSEngine(ABC):
    name: str = "base"
    sample_rate: int = 24000
    max_chunk_chars: int = 500
    # Tones this engine acts on. Empty = engine ignores the tone hint.
    # Post-v1 expressive engines declare their vocabulary here.
    supported_tones: tuple = ()

    @abstractmethod
    def synthesize(self, text: str, tone: Optional[str] = None):
        """Synthesize one chunk of text.

        Returns a 1-D float numpy array of samples at self.sample_rate,
        or None if the engine produced no audio for this text.
        Raises on engine failure (caller owns the retry/abort policy).

        tone: hint from the chunk schema (None = neutral). Engines that do not
        support expressive narration ignore this parameter.
        """
        raise NotImplementedError
