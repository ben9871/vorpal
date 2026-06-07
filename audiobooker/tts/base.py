"""TTS engine interface.

Engines synthesize one text chunk at a time and declare their sample rate and
maximum chunk length; the normalizer/chunker respects max_chunk_chars.
Voice cloning is out of scope by design (docs/02-product-vision.md).
"""

from abc import ABC, abstractmethod


class TTSEngine(ABC):
    name: str = "base"
    sample_rate: int = 24000
    max_chunk_chars: int = 500

    @abstractmethod
    def synthesize(self, text: str):
        """Synthesize one chunk of text.

        Returns a 1-D float numpy array of samples at self.sample_rate,
        or None if the engine produced no audio for this text.
        Raises on engine failure (caller owns the retry/abort policy).
        """
        raise NotImplementedError
