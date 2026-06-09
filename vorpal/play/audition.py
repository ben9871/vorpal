"""Cast audition mode (Phase 39): hear who sounds like whom before a
multi-hour synthesis.

For every non-cameo character, pick their 1–3 longest speeches (capped at
~200 words), synthesize with the assigned voice + tone hints, and write one
``<CHARACTER>.wav`` per character into the audition directory.
"""

from pathlib import Path
from typing import Callable, Dict, List, Optional

from ..synth import safe_filename
from ..tts.voices import VoiceEntry
from .casting import CastSheet
from .models import Beat, PlayDoc

MAX_AUDITION_LINES = 3
MAX_AUDITION_WORDS = 200


def select_audition_lines(
    play_doc: PlayDoc,
    character_name: str,
    max_lines: int = MAX_AUDITION_LINES,
    max_words: int = MAX_AUDITION_WORDS,
) -> List[Beat]:
    """The character's most representative speeches.

    Longest speeches first (most words = most to hear), capped at
    ``max_lines`` beats and a cumulative ``max_words`` — an audition,
    not a performance. Always returns at least one speech (the longest)
    when the character speaks at all, even if it alone exceeds the cap.
    """
    speeches = [
        beat
        for act in play_doc.acts
        for scene in act.scenes
        for beat in scene.beats
        if beat.type == "speech" and beat.speaker == character_name
    ]
    if not speeches:
        return []

    by_length = sorted(speeches, key=lambda b: len(b.text.split()),
                       reverse=True)
    selected: List[Beat] = [by_length[0]]
    words = len(by_length[0].text.split())
    for beat in by_length[1:]:
        if len(selected) >= max_lines:
            break
        n = len(beat.text.split())
        if words + n > max_words:
            continue
        selected.append(beat)
        words += n
    return selected


def build_audition(
    play_doc: PlayDoc,
    cast_sheet: CastSheet,
    cast: list,
    output_dir: Path,
    voices: Dict[str, VoiceEntry],
    engine_factory: Optional[Callable[[VoiceEntry], object]] = None,
    max_lines: int = MAX_AUDITION_LINES,
    max_words: int = MAX_AUDITION_WORDS,
) -> Dict[str, Path]:
    """Write one audition WAV per non-cameo character.

    Returns ``{character_name: wav_path}``. Characters whose selected lines
    produce no audio are skipped (reported by absence, never a crash).
    """
    import numpy as np
    import soundfile as sf

    if engine_factory is None:
        from .pipeline import default_engine_factory
        engine_factory = default_engine_factory()

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    engines: dict = {}
    results: Dict[str, Path] = {}

    for character in cast:
        if character.role == "cameo":
            continue
        lines = select_audition_lines(play_doc, character.name,
                                      max_lines=max_lines,
                                      max_words=max_words)
        if not lines:
            continue
        voice_id = cast_sheet.assignments.get(character.name)
        if voice_id is None or voice_id not in voices:
            raise ValueError(
                f"character {character.name!r} has no castable voice "
                f"({voice_id!r}) — regenerate the cast sheet")
        if voice_id not in engines:
            engines[voice_id] = engine_factory(voices[voice_id])
        engine = engines[voice_id]

        parts = []
        gap = np.zeros(int(0.6 * engine.sample_rate), dtype="float32")
        for beat in lines:
            audio = engine.synthesize(beat.text, tone=beat.tone_hint)
            if audio is None or len(audio) == 0:
                continue
            if parts:
                parts.append(gap)
            parts.append(np.asarray(audio, dtype="float32"))
        if not parts:
            continue

        wav_path = output_dir / f"{safe_filename(character.name)}.wav"
        sf.write(str(wav_path), np.concatenate(parts), engine.sample_rate)
        results[character.name] = wav_path

    return results
