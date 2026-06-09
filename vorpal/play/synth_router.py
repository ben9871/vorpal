"""Multi-voice synthesis routing for plays (Phase 35).

Turns a sequence of Beats into voiced synthesis chunks: each speech beat is
normalized into prosody chunks carrying the speaking character's voice id
from the cast sheet; stage directions are either dropped (default) or routed
to the narrator voice.

Synthesis itself reuses the book pipeline's cache + retry machinery
(`vorpal.synth`): one engine per distinct voice, chunks dispatched to the
engine their ``voice_id`` names. Cache keys include the voice id (see
``synth._cache_key``), so two characters reading the same line never collide.
"""

from pathlib import Path
from typing import Dict, List, Optional

from ..normalize import Chunk, normalize_chapter, PAUSE_PARAGRAPH_MS
from ..synth import _cache_key, _synth_with_retry
from ..tts.base import TTSEngine
from .casting import CastSheet

# Pause between two speakers' turns — slightly longer than a paragraph break,
# the audible cue that the voice is about to change.
PAUSE_TURN_MS = 700


def _direction_spoken_text(text: str) -> str:
    """Strip the [brackets] from a stage direction for narration."""
    t = text.strip()
    if t.startswith("[") and t.endswith("]"):
        t = t[1:-1].strip()
    if t and t[-1] not in ".!?":
        t += "."
    return t


def route_chunks(
    beats: list,
    cast_sheet: CastSheet,
    stage_directions: str = "skip",
    max_chars: int = 400,
) -> List[Chunk]:
    """Route a beat sequence to voiced synthesis chunks.

    ``stage_directions``: ``"skip"`` (default — directions dropped) or
    ``"narrator"`` (directions narrated with ``cast_sheet.narrator_voice``).

    A speech beat whose speaker is missing from the cast sheet is an error —
    the cast sheet is built from the same play, so a miss means the inputs
    are out of sync, and silently narrating it would miscast a character.
    """
    if stage_directions not in ("skip", "narrator"):
        raise ValueError(
            f"stage_directions must be 'skip' or 'narrator', "
            f"got {stage_directions!r}")

    routed: List[Chunk] = []
    for beat in beats:
        if beat.type == "direction":
            if stage_directions == "skip":
                continue
            text = _direction_spoken_text(beat.text)
            if not text:
                continue
            voice_id = cast_sheet.narrator_voice
        elif beat.type == "speech":
            if beat.speaker not in cast_sheet.assignments:
                raise ValueError(
                    f"speaker {beat.speaker!r} has no cast-sheet voice — "
                    f"cast sheet and play are out of sync")
            text = beat.text
            voice_id = cast_sheet.assignments[beat.speaker]
        else:
            continue

        beat_chunks = normalize_chapter(
            text, max_chars=max_chars,
            paragraph_pause_ms=PAUSE_PARAGRAPH_MS)
        for i, c in enumerate(beat_chunks):
            pause = c.pause_after_ms
            if i == len(beat_chunks) - 1:
                # Last chunk of a beat: pause for the speaker change.
                pause = max(pause, PAUSE_TURN_MS)
            routed.append(Chunk(
                idx=len(routed),
                text=c.text,
                pause_after_ms=pause,
                tone=c.tone,
                text_hash=c.text_hash,
                is_dialogue=c.is_dialogue,
                voice_id=voice_id,
            ))
    return routed


def synthesize_routed_chunks(
    chunks: List[Chunk],
    voice_engines: Dict[str, TTSEngine],
    cache_dir: Path,
) -> tuple:
    """Synthesize voiced chunks through the per-voice engines.

    ``voice_engines`` maps voice id → constructed engine. Every chunk's
    ``voice_id`` must be present (fail loud — a missing engine would
    otherwise silently drop a character's lines).

    Returns ``(chunk_wavs, report)`` where ``chunk_wavs`` is
    ``[(cache_path, pause_after_ms), …]`` in beat order and ``report`` is
    ``{"done": n, "cached": n}``.
    """
    import soundfile as sf

    missing = {c.voice_id for c in chunks} - set(voice_engines)
    if missing:
        raise ValueError(
            f"no engine for voice id(s): {sorted(missing)} — "
            f"voice_engines must cover every routed voice")

    cache_dir.mkdir(parents=True, exist_ok=True)
    chunk_wavs = []
    done = 0
    cached = 0
    for chunk in chunks:
        engine = voice_engines[chunk.voice_id]
        cache_path = cache_dir / _cache_key(chunk, engine)
        if cache_path.exists():
            cached += 1
        else:
            audio, _retried = _synth_with_retry(
                chunk.text, chunk.tone, engine,
                chapter_title="play", chunk_idx=chunk.idx,
                is_dialogue=chunk.is_dialogue,
            )
            sf.write(str(cache_path), audio, engine.sample_rate)
            done += 1
        chunk_wavs.append((cache_path, chunk.pause_after_ms))
    return chunk_wavs, {"done": done, "cached": cached}
