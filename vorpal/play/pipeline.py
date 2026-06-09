"""End-to-end play pipeline (Phase 38): `vorpal play <input>`.

parse → extract cast → assign voices → chapter structure → review gate →
multi-voice synthesis → master → package.

The review gate mirrors `vorpal build`: the first run stops after printing
the cast sheet and chapter list; the operator approves with `--approve`
(optionally editing `cast_sheet.json` in the workdir or passing
`--cast-override` first). Artifacts persisted in the workdir:
``play.json``, ``cast.json``, ``cast_sheet.json``.
"""

import json
from pathlib import Path
from typing import Callable, Dict, List, Optional

from ..normalize import spoken_form
from ..synth import safe_filename
from ..tts.voices import VOICE_REGISTRY, VoiceEntry
from .casting import (
    DEFAULT_NARRATOR_VOICE,
    CastSheet,
    apply_overrides,
    assign_voices,
    castable_voices,
    format_cast_table,
)
from .chapters import build_play_chapters
from .characters import extract_cast
from .models import PlayDoc
from .parser import parse_play
from .synth_router import route_chunks, synthesize_routed_chunks


def load_play(input_path: Path) -> PlayDoc:
    """Load a play from stripped Gutenberg .txt or a parsed play.json."""
    if input_path.suffix.lower() == ".json":
        return PlayDoc.from_dict(
            json.loads(input_path.read_text(encoding="utf-8")))
    return parse_play(input_path.read_text(encoding="utf-8"))


def default_engine_factory() -> Callable[[VoiceEntry], object]:
    """Kokoro engine factory with a shared model pipeline.

    Each voice gets its own engine (its own voice/blend params) but all
    engines share one loaded Kokoro model — a full cast must not load the
    model once per character. Engines are wrapped in KokoroApproxEngine so
    Phase 37 tone hints are realized.
    """
    from ..tts.kokoro_approx import KokoroApproxEngine
    from ..tts.kokoro_engine import KokoroEngine

    shared: dict = {}

    def factory(entry: VoiceEntry):
        inner = KokoroEngine(params=entry.params)
        if "pipeline" in shared:
            inner._pipeline = shared["pipeline"]
        else:
            inner._load()
            shared["pipeline"] = inner._pipeline
        return KokoroApproxEngine(inner_engine=inner)

    return factory


def _assemble_chapter_wav(chunk_wavs: list, out_path: Path) -> int:
    """Stream chunk WAVs (+pauses) into one chapter WAV; returns duration ms.

    Same constant-memory pattern as the book pipeline: never holds a whole
    chapter of float audio in RAM.
    """
    import numpy as np
    import soundfile as sf

    total_frames = 0
    sample_rate = None
    out_handle = None
    try:
        for wav_path, pause_ms in chunk_wavs:
            data, sr = sf.read(str(wav_path), dtype="float32")
            if out_handle is None:
                sample_rate = sr
                out_handle = sf.SoundFile(str(out_path), mode="w",
                                          samplerate=sr, channels=1)
            out_handle.write(data)
            total_frames += len(data)
            gap_ms = pause_ms if pause_ms > 0 else 50
            silence = np.zeros(int(gap_ms / 1000 * sr), dtype="float32")
            out_handle.write(silence)
            total_frames += len(silence)
    finally:
        if out_handle is not None:
            out_handle.close()
    if sample_rate is None:
        return 0
    return int(total_frames / sample_rate * 1000)


def build_play(
    input_path: Path,
    output_stem: Optional[str] = None,
    chapters_mode: str = "act",
    stage_directions: str = "skip",
    cast_override: Optional[Dict[str, str]] = None,
    narrator_voice: str = DEFAULT_NARRATOR_VOICE,
    best_voice: Optional[str] = None,
    approve: bool = False,
    draft: bool = False,
    profile: str = "headphones",
    use_tone_hints: bool = True,
    engine_factory: Optional[Callable[[VoiceEntry], object]] = None,
    voices: Optional[Dict[str, VoiceEntry]] = None,
) -> dict:
    """Run the play pipeline.

    Returns a result dict:
      ``{"status": "review", "cast_sheet": …, "chapters": …, "work_dir": …}``
      when stopping at the review gate (``approve=False``), or
      ``{"status": "built", "output": Path, …}`` after a full build.

    ``voices`` / ``engine_factory`` are injection points for tests; defaults
    are the real castable registry and the shared-pipeline Kokoro factory.
    """
    input_path = Path(input_path)
    stem = output_stem or input_path.stem
    work_dir = Path(f"{stem}_workdir")
    work_dir.mkdir(parents=True, exist_ok=True)

    # ── 1. parse ──────────────────────────────────────────────────────────
    play = load_play(input_path)
    (work_dir / "play.json").write_text(
        json.dumps(play.to_dict(), indent=1, ensure_ascii=False),
        encoding="utf-8")

    # ── 2. cast ───────────────────────────────────────────────────────────
    cast = extract_cast(play)
    if not cast:
        raise ValueError(
            f"no speakers found in {input_path.name} — is this a play?")
    (work_dir / "cast.json").write_text(
        json.dumps([c.to_dict() for c in cast], indent=1, ensure_ascii=False),
        encoding="utf-8")

    # ── 3. voices ─────────────────────────────────────────────────────────
    if voices is None:
        voices = castable_voices(VOICE_REGISTRY)
    if narrator_voice not in voices:
        raise ValueError(f"unknown narrator voice {narrator_voice!r}")

    sheet_path = work_dir / "cast_sheet.json"
    if sheet_path.exists():
        # Operator-editable: a hand-tuned sheet survives re-runs.
        sheet = CastSheet.from_dict(
            json.loads(sheet_path.read_text(encoding="utf-8")))
        # Characters added since the sheet was written get fresh assignments.
        missing = [c for c in cast if c.name not in sheet.assignments]
        if missing:
            fresh = assign_voices(cast, voices, best_voice=best_voice,
                                  narrator_voice=sheet.narrator_voice)
            for c in missing:
                sheet.assignments[c.name] = fresh.assignments[c.name]
                sheet.notes.append(f"re-cast new character: {c.name}")
    else:
        sheet = assign_voices(cast, voices, best_voice=best_voice,
                              narrator_voice=narrator_voice)

    if cast_override:
        apply_overrides(sheet, cast_override, voices)

    sheet_path.write_text(
        json.dumps(sheet.to_dict(), indent=1, ensure_ascii=False),
        encoding="utf-8")

    # ── 4. chapters ───────────────────────────────────────────────────────
    chapters = build_play_chapters(play, mode=chapters_mode)
    if not chapters:
        raise ValueError("play has no narratable chapters")

    # ── 5. review gate ────────────────────────────────────────────────────
    if not approve:
        return {
            "status": "review",
            "play": play,
            "cast": cast,
            "cast_sheet": sheet,
            "chapters": chapters,
            "voices": voices,
            "work_dir": work_dir,
        }

    # ── 6. engines (one per distinct voice, shared model) ────────────────
    if engine_factory is None:
        engine_factory = default_engine_factory()
    needed_voice_ids = set(sheet.assignments.values())
    if stage_directions == "narrator":
        needed_voice_ids.add(sheet.narrator_voice)
    voice_engines = {vid: engine_factory(voices[vid])
                     for vid in sorted(needed_voice_ids)}

    # ── 7. per-chapter synthesis ──────────────────────────────────────────
    audio_dir = work_dir / "audio"
    cache_dir = audio_dir / "cache"
    chapters_dir = work_dir / "chapters"
    chapters_dir.mkdir(parents=True, exist_ok=True)

    sample_engine = next(iter(voice_engines.values()))
    max_chars = getattr(sample_engine, "max_chunk_chars", 400)

    chapter_results: List[dict] = []
    totals = {"done": 0, "cached": 0}
    for idx, chapter in enumerate(chapters):
        chunks = route_chunks(
            chapter["beats"], sheet,
            stage_directions=stage_directions,
            max_chars=max_chars,
            use_tone_hints=use_tone_hints,
        )
        if not chunks:
            continue
        print(f"  Chapter {idx+1}/{len(chapters)}: "
              f"{chapter['title'][:60]} — {len(chunks)} chunks")
        chunk_wavs, report = synthesize_routed_chunks(
            chunks, voice_engines, cache_dir)
        totals["done"] += report["done"]
        totals["cached"] += report["cached"]
        ch_wav = chapters_dir / (
            f"chapter_{idx+1:02d}_{safe_filename(chapter['title'])}.wav")
        duration_ms = _assemble_chapter_wav(chunk_wavs, ch_wav)
        chapter_results.append({
            "title": spoken_form(chapter["title"]),
            "wav": ch_wav,
            "duration_ms": duration_ms,
        })

    if not chapter_results:
        raise RuntimeError("no audio produced — all chapters were empty")
    print(f"  Synthesis: {totals['done']} synthesized, "
          f"{totals['cached']} from cache")

    # ── 8. master & package ───────────────────────────────────────────────
    if draft:
        output = _draft_concat(chapter_results, stem)
    else:
        from ..master import compile_m4b
        from ..profiles import get_profile
        prof = get_profile(profile)
        output = compile_m4b(
            chapter_results, stem,
            title=play.title or stem,
            author=play.author,
            narrator="Full cast",
            target_lufs=prof.target_lufs,
            target_lra=prof.target_lra,
            target_tp=prof.target_tp,
            work_dir=work_dir,
        )

    return {
        "status": "built",
        "output": output,
        "cast_sheet": sheet,
        "chapters": chapters,
        "chapter_results": chapter_results,
        "synth_totals": totals,
        "work_dir": work_dir,
    }


def _draft_concat(chapter_results: List[dict], stem: str,
                  silence_ms: int = 1500) -> Path:
    """Concatenate chapter WAVs into one draft WAV (no mastering, no ffmpeg)."""
    import numpy as np
    import soundfile as sf

    out_path = Path(f"{stem}_draft_play.wav")
    out_handle = None
    try:
        for i, r in enumerate(chapter_results):
            data, sr = sf.read(str(r["wav"]), dtype="float32")
            if out_handle is None:
                out_handle = sf.SoundFile(str(out_path), mode="w",
                                          samplerate=sr, channels=1)
            out_handle.write(data)
            if i < len(chapter_results) - 1:
                out_handle.write(
                    np.zeros(int(silence_ms / 1000 * sr), dtype="float32"))
    finally:
        if out_handle is not None:
            out_handle.close()
    return out_path


def format_review_surface(result: dict) -> str:
    """The review-gate printout: cast sheet + chapter list + instructions."""
    lines = [
        "",
        f"Play: {result['play'].title}",
        f"Author: {result['play'].author or '(unknown)'}",
        "",
        "Cast sheet:",
        format_cast_table(result["cast"], result["cast_sheet"],
                          result["voices"]),
        "",
        f"Chapters ({len(result['chapters'])}):",
    ]
    for ch in result["chapters"]:
        n_speech = sum(1 for b in ch["beats"] if b.type == "speech")
        lines.append(f"  {ch['title'][:70]}  ({n_speech} speeches)")
    lines += [
        "",
        "Review the cast above. To adjust: edit "
        f"{result['work_dir'] / 'cast_sheet.json'} or pass "
        "--cast-override <json>.",
        "Then re-run with --approve to synthesize.",
    ]
    return "\n".join(lines)
