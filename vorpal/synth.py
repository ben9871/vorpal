"""Per-chapter TTS synthesis.

Phase 3 rewrite. Replaces the Phase-0 warn-and-skip loop with:
  - Prosody-aware chunks from normalize.normalize_chapter()
  - Chunk cache keyed by (text_hash, engine, voice, speed, tone) — survives
    chapter title edits; only the changed chapter's intro chunk re-synthesizes
  - Failure policy: on exception → retry once → retry with chunk split in half
    → if still failing, abort the build (or insert audible gap with --allow-gaps)
  - spoken_intro chapter announcements from the manifest
  - Synthesis report at the end (done / cached / retried / failed counts)
"""

import json
import re
import time
from pathlib import Path
from typing import Optional

from .normalize import (
    Chunk, normalize_chapter, lint_chunks, assert_no_loss,
    spoken_form, _sentences, _text_hash, PAUSE_PARAGRAPH_MS,
)
from .tts.base import TTSEngine


def safe_filename(s: str) -> str:
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"\s+", "_", s.strip())
    return s[:50]


# ── chunk cache ───────────────────────────────────────────────────────────

def _cache_key(chunk: Chunk, engine: TTSEngine) -> str:
    """Stable filename for a cached chunk WAV.

    Keyed on (text_hash, engine, voice, speed, tone) so edits to one chapter
    do not invalidate other chapters' cached audio, and a title edit re-synths
    only the intro chunk.
    """
    tone_part = chunk.tone or "none"
    voice = getattr(engine, "voice", "default")
    speed = getattr(engine, "speed", 1.0)
    raw = f"{chunk.text_hash}_{engine.name}_{voice}_{speed}_{tone_part}"
    # Sanitize for use as a filename
    raw = re.sub(r"[^\w\-]", "_", raw)
    return raw + ".wav"


# ── audible gap marker ────────────────────────────────────────────────────

def _gap_marker(sample_rate: int, duration_ms: int = 1000):
    """A short sine-wave beep used when --allow-gaps is set and a chunk fails."""
    import math
    import numpy as np
    n = int(sample_rate * duration_ms / 1000)
    t = [math.sin(2 * math.pi * 880 * i / sample_rate) for i in range(n)]
    return 0.3 * (
        [0.0] * (sample_rate // 10) +
        t +
        [0.0] * (sample_rate // 10)
    )


# ── per-chunk synthesis with retry / split ────────────────────────────────

def _synth_with_retry(text: str, tone: Optional[str], engine: TTSEngine,
                      chapter_title: str, chunk_idx: int) -> tuple:
    """Attempt synthesis with retry → split-half → abort.

    Returns (audio_array, retried: bool).
    Raises RuntimeError if all attempts fail (caller handles allow-gaps).
    """
    import numpy as np

    def _attempt(t: str):
        return engine.synthesize(t, tone=tone)

    # Attempt 1
    try:
        audio = _attempt(text)
        if audio is not None and len(audio) > 0:
            return audio, False
    except Exception as e1:
        pass
    else:
        e1 = ValueError("synthesize returned empty audio")

    # Attempt 2 — retry same text
    try:
        audio = _attempt(text)
        if audio is not None and len(audio) > 0:
            return audio, True
    except Exception as e2:
        pass
    else:
        e2 = ValueError("synthesize returned empty audio on retry")

    # Attempt 3 — split chunk in half at a sentence boundary
    sents = _sentences(text)
    if len(sents) >= 2:
        mid = len(sents) // 2
        half_a = " ".join(sents[:mid]).strip()
        half_b = " ".join(sents[mid:]).strip()
        parts = []
        split_ok = True
        for half in (half_a, half_b):
            if not half:
                continue
            try:
                a = _attempt(half)
                if a is not None and len(a) > 0:
                    parts.append(a)
                else:
                    split_ok = False
                    break
            except Exception:
                split_ok = False
                break
        if split_ok and parts:
            return np.concatenate(parts), True

    raise RuntimeError(
        f"Chunk {chunk_idx} in chapter '{chapter_title}' failed after all retries.\n"
        f"Text: {text[:120]!r}"
    )


# ── main synthesis loop ───────────────────────────────────────────────────

def tts_all_chapters(
    chapters: list,
    audio_dir: Path,
    chapters_dir: Path,
    engine: TTSEngine,
    allow_gaps: bool = False,
) -> list:
    """Synthesize all chapters and return chapter result dicts.

    chapters: list of dicts with keys title, body, skip, spoken_intro.
    Returns: [{title, wav, duration_ms}, ...]

    Aborts (raises SystemExit) if any chunk fails and allow_gaps is False.
    With allow_gaps=True, inserts an audible beep gap and lists failed chunks
    in the synthesis report.
    """
    import numpy as np
    import soundfile as sf

    cache_dir = audio_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    active_chapters = [c for c in chapters if not c["skip"]]
    max_chars = engine.max_chunk_chars

    # ── Build chunk lists for all chapters upfront ──
    chapter_chunk_lists = []   # list of list[Chunk]
    chapter_lint_issues = []

    for ch in active_chapters:
        spoken_intro = ch.get("spoken_intro") or ""
        if spoken_intro:
            intro_chunks = normalize_chapter(spoken_intro, max_chars=max_chars,
                                            paragraph_pause_ms=PAUSE_PARAGRAPH_MS)
        else:
            intro_chunks = []

        body = ch.get("body", "")
        if body.strip():
            try:
                assert_no_loss(body, normalize_chapter(body, max_chars=max_chars))
            except AssertionError as e:
                import sys
                sys.exit(f"ERROR: No-loss invariant failed for '{ch['title']}':\n{e}")
            body_chunks = normalize_chapter(body, max_chars=max_chars)
        else:
            body_chunks = []

        # Re-index so intro + body form a single sequence
        all_chunks: list[Chunk] = []
        for i, c in enumerate(intro_chunks + body_chunks):
            all_chunks.append(Chunk(i, c.text, c.pause_after_ms, c.tone, c.text_hash))

        # Junk lint — warn but don't abort (lint violations noted in report)
        lints = lint_chunks([c.to_dict() for c in all_chunks], ch["title"])
        chapter_lint_issues.append(lints)
        chapter_chunk_lists.append(all_chunks)

    total_chunks = sum(len(cl) for cl in chapter_chunk_lists)
    cached_count = sum(
        1 for cl in chapter_chunk_lists
        for chunk in cl
        if (cache_dir / _cache_key(chunk, engine)).exists()
    )

    print(f"\n[4/5] TTS — {len(active_chapters)} chapters, {total_chunks} chunks total")
    print(f"  {cached_count} cached, {total_chunks - cached_count} to synthesize")
    if any(chapter_lint_issues):
        total_lints = sum(len(l) for l in chapter_lint_issues)
        print(f"  {total_lints} lint warning(s) — check report for details")
    print()

    results = []
    report_done = 0
    report_cached = 0
    report_retried = 0
    report_failed = 0
    failed_chunks = []   # for the synthesis report
    tts_start = time.time()
    chunk_times = []

    for ch_idx, (chapter, all_chunks) in enumerate(
            zip(active_chapters, chapter_chunk_lists)):

        ch_wav = chapters_dir / f"chapter_{ch_idx+1:02d}_{safe_filename(chapter['title'])}.wav"

        if ch_wav.exists():
            data, sr = sf.read(str(ch_wav))
            duration_ms = int(len(data) / sr * 1000)
            results.append({"title": chapter["title"], "wav": ch_wav,
                             "duration_ms": duration_ms})
            report_cached += len(all_chunks)
            continue

        n_chunks = len(all_chunks)
        print(f"  Chapter {ch_idx+1}/{len(active_chapters)}: {chapter['title'][:50]}")
        print(f"  {'─' * 52}")

        chunk_wavs = []   # (path, pause_after_ms)

        for chunk in all_chunks:
            cache_path = cache_dir / _cache_key(chunk, engine)

            if cache_path.exists():
                chunk_wavs.append((cache_path, chunk.pause_after_ms))
                report_cached += 1
                report_done += 1
                # Update progress display
                i = chunk.idx
                pct = (report_done + report_cached) / max(total_chunks, 1) * 100
                filled = int(30 * (i + 1) / max(n_chunks, 1))
                bar = "█" * filled + "░" * (30 - filled)
                print(f"  \r  [{bar}] {i+1}/{n_chunks}  Book: {pct:.0f}%  ",
                      end="", flush=True)
                continue

            t0 = time.time()
            try:
                audio, retried = _synth_with_retry(
                    chunk.text, chunk.tone, engine,
                    chapter["title"], chunk.idx,
                )
                sf.write(str(cache_path), audio, engine.sample_rate)
                chunk_wavs.append((cache_path, chunk.pause_after_ms))
                if retried:
                    report_retried += 1
                report_done += 1
            except RuntimeError as e:
                report_failed += 1
                failed_chunks.append({
                    "chapter": chapter["title"],
                    "chunk_idx": chunk.idx,
                    "text": chunk.text[:120],
                    "error": str(e)[:200],
                })
                if allow_gaps:
                    import numpy as np
                    gap = np.array(_gap_marker(engine.sample_rate), dtype="float32")
                    gap_path = cache_path.with_suffix(".gap.wav")
                    sf.write(str(gap_path), gap, engine.sample_rate)
                    chunk_wavs.append((gap_path, 0))
                    print(f"\n    [gap] chunk {chunk.idx} failed — audible marker inserted")
                else:
                    # Abort immediately — don't synthesize more
                    import sys
                    print(f"\n\nERROR: {e}")
                    print("\nBuild aborted. Fix the normalization issue or pass "
                          "--allow-gaps to insert audible markers and continue.")
                    sys.exit(1)

            elapsed = time.time() - t0
            chunk_times.append(elapsed)
            if len(chunk_times) > 30:
                chunk_times.pop(0)

            i = chunk.idx
            global_done = report_done + report_cached
            remaining = total_chunks - global_done
            avg_time = sum(chunk_times) / len(chunk_times) if chunk_times else 0
            eta_sec = int(remaining * avg_time)
            eta_str = (f"{eta_sec//3600}h {(eta_sec%3600)//60}m"
                       if eta_sec > 3600 else f"{eta_sec//60}m {eta_sec%60}s")
            pct = global_done / max(total_chunks, 1) * 100
            filled = int(30 * (i + 1) / max(n_chunks, 1))
            bar = "█" * filled + "░" * (30 - filled)
            print(
                f"  \r  [{bar}] {i+1}/{n_chunks}  Book: {pct:.0f}%  "
                f"ETA: {eta_str}  {elapsed:.1f}s/chunk   ",
                end="", flush=True,
            )

        print()  # newline after progress bar

        if not chunk_wavs:
            print("  !! No audio for this chapter — skipping")
            continue

        # Assemble chapter WAV from cached chunk files + pauses
        all_audio = []
        sample_rate = None
        for wav_path, pause_ms in chunk_wavs:
            data, sr = sf.read(str(wav_path), dtype="float32")
            sample_rate = sr
            all_audio.append(data)
            if pause_ms > 0:
                silence = np.zeros(int(pause_ms / 1000 * sr), dtype="float32")
                all_audio.append(silence)
            else:
                # Short inter-chunk gap (50 ms) for natural breath
                all_audio.append(np.zeros(int(0.05 * sr), dtype="float32"))

        combined = np.concatenate(all_audio)
        sf.write(str(ch_wav), combined, sample_rate)
        duration_ms = int(len(combined) / sample_rate * 1000)
        total_elapsed = int(time.time() - tts_start)
        results.append({"title": chapter["title"], "wav": ch_wav,
                        "duration_ms": duration_ms})
        print(f"  ✓ {duration_ms//1000//60}m {duration_ms//1000%60}s audio  "
              f"(session: {total_elapsed//60}m {total_elapsed%60}s)\n")

    # ── Synthesis report ──────────────────────────────────────────────────
    total_elapsed = int(time.time() - tts_start)
    print(f"\n  Synthesis report:")
    print(f"    done: {report_done}  cached: {report_cached}  "
          f"retried: {report_retried}  failed: {report_failed}")
    if failed_chunks:
        print(f"\n  Failed chunks:")
        for fc in failed_chunks:
            print(f"    Chapter '{fc['chapter']}' chunk {fc['chunk_idx']}: "
                  f"{fc['text'][:60]!r}")
    if any(chapter_lint_issues):
        print(f"\n  Lint warnings (residual OCR artifacts — verify these segments):")
        for issues in chapter_lint_issues:
            for issue in issues:
                print(f"    [{issue['chapter']}] chunk {issue['chunk_idx']} "
                      f"({issue['pattern']}): {issue['snippet'][:60]!r}")

    return results
