"""Audiobook assembly: concatenate chapter WAVs and mux into .m4b with chapters.

Phase 0: verbatim port of the v0 logic, including its known scaling flaw
(whole-book concatenation in RAM — docs/01-audit.md §4). Phase 4 replaces this
with streaming ffmpeg concat + loudness normalization.
"""

import shutil
import subprocess
from pathlib import Path

from .binaries import find_ffmpeg
from .synth import safe_filename


def compile_m4b(chapter_results: list, output_stem: str,
                title: str = "", author: str = "") -> Path:
    """
    Concatenate chapter WAVs and mux into a .m4b with chapter markers.
    Falls back to a folder of WAVs if ffmpeg is unavailable.
    """
    import numpy as np
    import soundfile as sf

    print("\n[5/5] Compiling audiobook...")

    if not chapter_results:
        raise RuntimeError("No chapters to compile.")

    ffmpeg_cmd = find_ffmpeg()

    if not ffmpeg_cmd:
        print("  ffmpeg not found — saving individual chapter WAVs instead.")
        print("  Install ffmpeg to get a single .m4b:  https://www.gyan.dev/ffmpeg/builds/")
        out_dir = Path(f"{output_stem}_chapters")
        out_dir.mkdir(exist_ok=True)
        for i, ch in enumerate(chapter_results):
            dest = out_dir / f"{i+1:02d}_{safe_filename(ch['title'])}.wav"
            shutil.copy(ch["wav"], dest)
        print(f"  Chapters saved in: {out_dir}")
        return out_dir

    # ── Concatenate all chapter WAVs into one big WAV ──
    print("  Merging chapter audio...")
    sample_rate = None
    all_audio = []
    chapter_start_ms = []
    cursor_ms = 0

    silence_between = 1.5  # seconds of silence between chapters

    for ch in chapter_results:
        data, sr = sf.read(str(ch["wav"]), dtype="float32")
        sample_rate = sr
        chapter_start_ms.append(cursor_ms)
        all_audio.append(data)
        dur_ms = int(len(data) / sr * 1000)
        cursor_ms += dur_ms
        # Add inter-chapter silence
        sil = np.zeros(int(silence_between * sr), dtype=np.float32)
        all_audio.append(sil)
        cursor_ms += int(silence_between * 1000)

    combined = np.concatenate(all_audio)
    combined_wav = Path(f"{output_stem}_combined.wav")
    sf.write(str(combined_wav), combined, sample_rate)
    total_min = len(combined) / sample_rate / 60
    print(f"  Total duration: {total_min:.1f} minutes")

    # ── Write ffmetadata chapter file ──
    meta_path = Path(f"{output_stem}_chapters.txt")
    with open(meta_path, "w", encoding="utf-8") as f:
        f.write(";FFMETADATA1\n")
        if title:
            f.write(f"title={title}\n")
        if author:
            f.write(f"artist={author}\n")
        f.write("genre=Audiobook\n\n")
        for i, (ch, start_ms) in enumerate(zip(chapter_results, chapter_start_ms)):
            end_ms = chapter_start_ms[i + 1] if i + 1 < len(chapter_results) else cursor_ms
            f.write("[CHAPTER]\n")
            f.write("TIMEBASE=1/1000\n")
            f.write(f"START={start_ms}\n")
            f.write(f"END={end_ms}\n")
            f.write(f"title={ch['title']}\n\n")

    # ── Encode to M4B ──
    m4b_path = Path(f"{output_stem}.m4b")
    print(f"  Encoding to M4B (this may take a few minutes)...")
    result = subprocess.run([
        ffmpeg_cmd, "-y",
        "-i", str(combined_wav),
        "-i", str(meta_path),
        "-map_metadata", "1",
        "-c:a", "aac",
        "-b:a", "64k",
        "-f", "mp4",
        str(m4b_path)
    ], capture_output=True, text=True)

    combined_wav.unlink(missing_ok=True)
    meta_path.unlink(missing_ok=True)

    if result.returncode == 0:
        size_mb = m4b_path.stat().st_size / 1024 / 1024
        print(f"  M4B saved: {m4b_path}  ({size_mb:.0f} MB)")
        print(f"  {len(chapter_results)} chapters with navigation markers.")
        return m4b_path
    else:
        print("  WARNING: M4B encoding failed. Saving chapter WAVs instead.")
        print(result.stderr[-500:])
        return Path(f"{output_stem}_chapters")
