"""TTS engine interface.

Engines synthesize one text chunk at a time and declare their sample rate,
maximum chunk length, and which tone hints they act on.
Voice cloning is out of scope by design (docs/02-product-vision.md).
"""

from abc import ABC, abstractmethod
from typing import List, Optional


class TTSEngine(ABC):
    name: str = "base"
    sample_rate: int = 24000
    max_chunk_chars: int = 500
    # Tones this engine acts on. Empty = engine ignores the tone hint.
    # Post-v1 expressive engines declare their vocabulary here.
    supported_tones: tuple = ()
    # Set True in subclasses that implement synthesize_batch().
    # When True, synth.py uses the batch path for uncached chunks.
    supports_batch: bool = False
    # Dialogue shift style: None = no shift (default, byte-identical to pre-Phase-24).
    # Set to "subtle" to apply a conservative delivery adjustment for quoted speech.
    dialogue_style: Optional[str] = None

    @abstractmethod
    def synthesize(self, text: str, tone: Optional[str] = None,
                   is_dialogue: bool = False):
        """Synthesize one chunk of text.

        Returns a 1-D float numpy array of samples at self.sample_rate,
        or None if the engine produced no audio for this text.
        Raises on engine failure (caller owns the retry/abort policy).

        tone: hint from the chunk schema (None = neutral). Engines that do not
        support expressive narration ignore this parameter.
        is_dialogue: True when the chunk is majority quoted speech. Engines with
        dialogue_style set apply a subtle delivery adjustment; others ignore it.
        """
        raise NotImplementedError

    def synthesize_batch(self, texts: List[str],
                         tone: Optional[str] = None) -> List:
        """Synthesize a batch of texts, returning one audio array per text.

        Default implementation falls back to sequential synthesize() calls.
        Subclasses that support efficient GPU batching override this and set
        supports_batch = True.

        Returns a list parallel to `texts`; each element is a 1-D float numpy
        array or None if that text produced no audio.
        """
        return [self.synthesize(t, tone=tone) for t in texts]
