"""Per-chapter TTS synthesis.

Phase 0: port of the v0 loop against the TTSEngine interface (F5/voice-clone
path removed). Failure policy is still v0's warn-and-skip, but the total is
now reported at the end of the run; Phase 3 replaces this with the
retry → split → abort policy (docs/03-architecture.md, stage 6).
"""

import re
import time
from pathlib import Path

from .normalize import split_into_chunks
from .tts.base import TTSEngine


def safe_filename(s: str) -> str:
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"\s+", "_", s.strip())
    return s[:50]


def tts_all_chapters(chapters: list, audio_dir: Path, chapters_dir: Path,
                     engine: TTSEngine) -> list:
    """
    Returns list of dicts: [{title, wav, duration_ms}, ...]
    One WAV file per chapter.
    """
    import numpy as np
    import soundfile as sf

    active_chapters = [c for c in chapters if not c["skip"]]
    max_chars = engine.max_chunk_chars

    def announcement_for(ch_idx, chapter):
        # Manifest-provided spoken intro ("Conclusion.") beats the numbered
        # default, which is wrong for prefaces/conclusions (audit §2).
        return chapter.get("spoken_intro") or f"Chapter {ch_idx + 1}. {chapter['title']}."

    # Count total chunks upfront for global progress
    chapter_chunk_counts = []
    for ch_idx, chapter in enumerate(active_chapters):
        ann = split_into_chunks(announcement_for(ch_idx, chapter), max_chars)
        body = split_into_chunks(chapter["body"], max_chars)
        chapter_chunk_counts.append(len(ann) + len(body))
    total_chunks = sum(chapter_chunk_counts)
    already_done = sum(
        1 for ch_idx, chapter in enumerate(active_chapters)
        for i in range(chapter_chunk_counts[ch_idx])
        if (audio_dir / f"ch{ch_idx:03d}_chunk{i:05d}.wav").exists()
    )

    print(f"\n[4/5] TTS — {len(active_chapters)} chapters, ~{total_chunks} chunks total")
    print(f"  {already_done} chunks already done, {total_chunks - already_done} remaining")
    print()

    results = []
    global_done = already_done
    total_failed = 0
    chunk_times = []   # rolling window of recent chunk durations for ETA
    tts_start = time.time()

    for ch_idx, chapter in enumerate(active_chapters):
        ch_wav = chapters_dir / f"chapter_{ch_idx+1:02d}_{safe_filename(chapter['title'])}.wav"

        if ch_wav.exists():
            data, sr = sf.read(str(ch_wav))
            duration_ms = int(len(data) / sr * 1000)
            results.append({"title": chapter["title"], "wav": ch_wav, "duration_ms": duration_ms})
            continue

        announcement = announcement_for(ch_idx, chapter)
        announce_chunks = split_into_chunks(announcement, max_chars)
        body_chunks = split_into_chunks(chapter["body"], max_chars)
        all_chunks = announce_chunks + body_chunks
        n_chunks = len(all_chunks)

        print(f"  Chapter {ch_idx+1}/{len(active_chapters)}: {chapter['title'][:50]}")
        print(f"  {'─' * 52}")

        chunk_files = []

        for i, chunk in enumerate(all_chunks):
            audio_path = audio_dir / f"ch{ch_idx:03d}_chunk{i:05d}.wav"

            if audio_path.exists():
                chunk_files.append(audio_path)
                global_done += 1
                continue

            t0 = time.time()
            try:
                audio = engine.synthesize(chunk)
                if audio is not None and len(audio) > 0:
                    sf.write(str(audio_path), audio, engine.sample_rate)
                    chunk_files.append(audio_path)
            except Exception as e:
                total_failed += 1
                print(f"\n    WARNING: chunk {i} skipped ({e})")

            elapsed = time.time() - t0
            chunk_times.append(elapsed)
            if len(chunk_times) > 30:
                chunk_times.pop(0)

            global_done += 1
            remaining = total_chunks - global_done
            avg_time = sum(chunk_times) / len(chunk_times)
            eta_sec = int(remaining * avg_time)
            eta_str = f"{eta_sec//3600}h {(eta_sec%3600)//60}m" if eta_sec > 3600 else f"{eta_sec//60}m {eta_sec%60}s"

            pct = global_done / total_chunks * 100
            bar_w = 30
            filled = int(bar_w * (i + 1) / n_chunks)
            bar = "█" * filled + "░" * (bar_w - filled)

            print(
                f"  \r  [{bar}] {i+1}/{n_chunks} chunks  |  "
                f"Book: {pct:.0f}%  |  ETA: {eta_str}  |  {elapsed:.1f}s/chunk   ",
                end="", flush=True
            )

        print()  # newline after progress bar

        if not chunk_files:
            print("  !! No audio generated for this chapter — skipping")
            continue

        # Merge chunks into one chapter WAV
        all_audio = []
        sample_rate = None
        for cf in sorted(chunk_files):
            data, sr = sf.read(str(cf), dtype="float32")
            sample_rate = sr
            all_audio.append(data)
            all_audio.append(np.zeros(int(0.05 * sr), dtype=np.float32))

        combined = np.concatenate(all_audio)
        sf.write(str(ch_wav), combined, sample_rate)
        duration_ms = int(len(combined) / sample_rate * 1000)
        total_elapsed = int(time.time() - tts_start)
        results.append({"title": chapter["title"], "wav": ch_wav, "duration_ms": duration_ms})
        print(f"  ✓ Chapter done: {duration_ms//1000//60}m {duration_ms//1000%60}s audio  "
              f"(session elapsed: {total_elapsed//60}m {total_elapsed%60}s)\n")

    if total_failed:
        print(f"\n  !! {total_failed} chunks FAILED and are missing from the audio.")
        print(f"  !! The corresponding sentences are not narrated. Re-run to retry them.")

    return results
