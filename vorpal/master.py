"""Audiobook mastering and packaging — Phase 4.

Constant-memory assembly via ffmpeg concat demuxer:
  1. Per-chapter loudness normalization (two-pass loudnorm to target LUFS)
  2. Per-chapter AAC encode (one chapter at a time, never whole-book in RAM)
  3. ffmpeg concat-demuxer assembly with chapter markers & inter-chapter silence
  4. Embedded cover art (page-1 PDF render via fitz/PyMuPDF)
  5. chapters_mp3/ side product
  6. report.md QA summary
"""

import hashlib
import json
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .binaries import require_ffmpeg
from .synth import safe_filename

# Chapter shorter than this (seconds) triggers a duration warning.
SHORT_CHAPTER_THRESHOLD_S = 60


@dataclass
class LoudnessResult:
    chapter_title: str
    input_i: float
    output_i: float
    within_gate: bool


# ── ffmpeg helpers ────────────────────────────────────────────────────────

def _run_ffmpeg(cmd: list, step_name: str) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed at '{step_name}':\n{result.stderr[-600:]}"
        )
    return result


def _parse_loudnorm_json(stderr: str) -> dict:
    """Extract the loudnorm JSON stats block from ffmpeg stderr output."""
    idx = stderr.rfind("{")
    if idx == -1:
        raise ValueError(f"No loudnorm JSON found in ffmpeg output:\n{stderr[-400:]}")
    end = stderr.find("}", idx)
    if end == -1:
        raise ValueError("Unterminated JSON in ffmpeg loudnorm output")
    return json.loads(stderr[idx: end + 1])


def _wav_sample_rate(wav_path: Path) -> tuple:
    """Return (sample_rate, channels) by reading only the WAV header."""
    with wave.open(str(wav_path), "rb") as wf:
        return wf.getframerate(), wf.getnchannels()


# ── per-chapter loudness normalization ───────────────────────────────────

def _loudnorm_measure(wav_path: Path, ffmpeg: str,
                      target_lufs: float, target_tp: float,
                      target_lra: float) -> dict:
    """Pass 1: measure input loudness; return stats dict."""
    filter_str = (
        f"loudnorm=I={target_lufs}:TP={target_tp}:LRA={target_lra}"
        ":print_format=json"
    )
    result = subprocess.run(
        [ffmpeg, "-y", "-nostdin", "-i", str(wav_path),
         "-filter:a", filter_str, "-f", "null", "-"],
        capture_output=True, text=True,
    )
    return _parse_loudnorm_json(result.stderr)


def _loudnorm_encode(wav_path: Path, out_m4a: Path, ffmpeg: str,
                     stats: dict, target_lufs: float, target_tp: float,
                     target_lra: float, aac_bitrate: str) -> float:
    """Pass 2: apply loudnorm (linear) + encode to AAC. Returns output_i LUFS."""
    filter_str = (
        f"loudnorm=I={target_lufs}:TP={target_tp}:LRA={target_lra}"
        f":measured_I={stats['input_i']}"
        f":measured_LRA={stats['input_lra']}"
        f":measured_TP={stats['input_tp']}"
        f":measured_thresh={stats['input_thresh']}"
        f":offset={stats['target_offset']}"
        ":linear=true:print_format=json"
    )
    result = _run_ffmpeg(
        [ffmpeg, "-y", "-nostdin", "-i", str(wav_path),
         "-filter:a", filter_str,
         "-c:a", "aac", "-b:a", aac_bitrate, str(out_m4a)],
        f"loudnorm encode {wav_path.name}",
    )
    stats2 = _parse_loudnorm_json(result.stderr)
    return float(stats2["output_i"])


def loudnorm_chapter(
    wav_path: Path,
    out_m4a: Path,
    chapter_title: str,
    ffmpeg: str,
    target_lufs: float = -18.0,
    target_tp: float = -1.5,
    target_lra: float = 11.0,
    aac_bitrate: str = "64k",
) -> LoudnessResult:
    """Two-pass loudnorm normalization + AAC encode for one chapter WAV."""
    stats = _loudnorm_measure(wav_path, ffmpeg, target_lufs, target_tp, target_lra)
    output_i = _loudnorm_encode(
        wav_path, out_m4a, ffmpeg, stats,
        target_lufs, target_tp, target_lra, aac_bitrate,
    )
    within_gate = abs(output_i - target_lufs) <= 1.0
    return LoudnessResult(
        chapter_title=chapter_title,
        input_i=float(stats["input_i"]),
        output_i=output_i,
        within_gate=within_gate,
    )


# ── assembly helpers ──────────────────────────────────────────────────────

def _generate_silence_m4a(
    duration_ms: int, work_dir: Path, ffmpeg: str,
    aac_bitrate: str, sample_rate: int,
) -> Path:
    """Generate a single silence AAC file reused between chapters."""
    out = work_dir / "silence.m4a"
    duration_s = duration_ms / 1000
    channels = "mono"
    _run_ffmpeg(
        [ffmpeg, "-y", "-nostdin",
         "-f", "lavfi", "-i", f"anullsrc=r={sample_rate}:cl={channels}",
         "-t", str(duration_s),
         "-c:a", "aac", "-b:a", aac_bitrate, str(out)],
        "generate silence",
    )
    return out


def _compute_chapter_timestamps(chapter_results: list, silence_ms: int) -> list:
    """Return list of chapter start timestamps (ms) from chapter durations."""
    starts = []
    cursor = 0
    for ch in chapter_results:
        starts.append(cursor)
        cursor += ch["duration_ms"] + silence_ms
    return starts


def _write_ffmetadata(
    path: Path,
    chapter_results: list,
    timestamps_ms: list,
    title: str,
    author: str,
    narrator: str = "",
    year: str = "",
    language: str = "en",
    publisher: str = "",
) -> None:
    """Write ffmpeg chapter metadata file."""
    # Total duration = last start + last chapter duration (no trailing silence)
    total_ms = timestamps_ms[-1] + chapter_results[-1]["duration_ms"]
    with open(path, "w", encoding="utf-8") as f:
        f.write(";FFMETADATA1\n")
        if title:
            f.write(f"title={title}\n")
        if author:
            f.write(f"artist={author}\n")
        if narrator:
            f.write(f"composer={narrator}\n")  # composer = narrator in M4B convention
        if year:
            f.write(f"date={year}\n")
        if language:
            f.write(f"language={language}\n")
        if publisher:
            f.write(f"publisher={publisher}\n")
        f.write("genre=Audiobook\n\n")
        for i, (ch, start_ms) in enumerate(zip(chapter_results, timestamps_ms)):
            end_ms = (
                timestamps_ms[i + 1]
                if i + 1 < len(chapter_results)
                else total_ms
            )
            f.write("[CHAPTER]\n")
            f.write("TIMEBASE=1/1000\n")
            f.write(f"START={start_ms}\n")
            f.write(f"END={end_ms}\n")
            f.write(f"title={ch['title']}\n\n")


def _write_concat_list(path: Path, m4a_paths: list) -> None:
    """Write ffmpeg concat demuxer input file (absolute paths, single-quoted)."""
    with open(path, "w", encoding="utf-8") as f:
        for p in m4a_paths:
            posix = Path(p).resolve().as_posix().replace("'", "\\'")
            f.write(f"file '{posix}'\n")


# ── cover art ─────────────────────────────────────────────────────────────

def _score_cover_page(page, title: str) -> float:
    """Heuristic score for a fitz page as a cover candidate.

    Higher score = more likely to be the actual book cover.
    Rewards image-heavy pages and title presence.
    Penalises copyright/TOC pages (many short text fragments).
    """
    score = 0.0
    page_rect = page.rect
    page_area = max(page_rect.width * page_rect.height, 1)

    image_area = 0.0
    short_text_blocks = 0
    page_text_pieces = []
    for block in page.get_text("dict")["blocks"]:
        btype = block.get("type", -1)
        if btype == 1:  # image block
            r = block.get("bbox", [0, 0, 0, 0])
            w = r[2] - r[0]
            h = r[3] - r[1]
            image_area += w * h
        elif btype == 0:  # text block
            text = "".join(
                span.get("text", "")
                for line in block.get("lines", [])
                for span in line.get("spans", [])
            ).strip()
            page_text_pieces.append(text)
            if len(text) < 60:
                short_text_blocks += 1

    # Image coverage bonus (0–10 points)
    score += (image_area / page_area) * 10

    # Title presence bonus
    page_text = " ".join(page_text_pieces).lower()
    if title and title.lower() in page_text:
        score += 5.0

    # Many short fragments → probably copyright/TOC page → penalise
    if short_text_blocks > 6:
        score -= 2.0

    return score


def _render_cover(pdf_path: Optional[Path], work_dir: Path,
                  title: str = "") -> Optional[Path]:
    """Render the best-scored cover candidate from the first 5 PDF pages.

    Scores pages 0–4 by image density and title-text proximity; picks the
    highest-scoring candidate.  Falls back to page 0 if scoring fails.
    Returns None on any error.
    """
    if not pdf_path or not pdf_path.exists():
        return None
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        n_candidates = min(5, len(doc))
        best_page_idx = 0
        best_score = -999.0
        for i in range(n_candidates):
            try:
                s = _score_cover_page(doc[i], title)
                if s > best_score:
                    best_score = s
                    best_page_idx = i
            except Exception:
                pass
        page = doc[best_page_idx]
        mat = fitz.Matrix(72 / 72, 72 / 72)  # 72 dpi
        pix = page.get_pixmap(matrix=mat)
        cover_path = work_dir / "cover.jpg"
        pix.save(str(cover_path))
        doc.close()
        if best_page_idx > 0:
            print(f"  Cover: using page {best_page_idx + 1} "
                  f"(score {best_score:.1f}, vs page 1 default)")
        return cover_path
    except Exception as e:
        print(f"  WARNING: cover art render failed ({e}), skipping cover")
        return None


def extract_epub_cover(epub_path: Path, work_dir: Path) -> Optional[Path]:
    """Extract the cover image from an EPUB file.

    Looks for an OPF manifest item with properties="cover-image" or
    id containing "cover". Returns the path to the extracted JPEG/PNG,
    or None if no cover is found.
    """
    import zipfile
    try:
        with zipfile.ZipFile(str(epub_path), "r") as zf:
            # Find OPF
            container = zf.read("META-INF/container.xml").decode("utf-8", errors="replace")
            import xml.etree.ElementTree as ET
            root = ET.fromstring(container)
            opf_path = None
            for rf in root.iter():
                if rf.tag.rsplit("}", 1)[-1] == "rootfile":
                    opf_path = rf.get("full-path")
                    break
            if not opf_path:
                return None

            opf_dir = opf_path[:opf_path.rfind("/") + 1] if "/" in opf_path else ""
            opf_xml = zf.read(opf_path).decode("utf-8", errors="replace")
            opf_root = ET.fromstring(opf_xml)

            # Find cover image in manifest
            cover_href = None
            for item in opf_root.iter():
                local = item.tag.rsplit("}", 1)[-1] if "}" in item.tag else item.tag
                if local == "item":
                    props = item.get("properties", "")
                    item_id = item.get("id", "").lower()
                    media_type = item.get("media-type", "")
                    if ("cover-image" in props or "cover" in item_id) \
                            and "image" in media_type:
                        cover_href = opf_dir + item.get("href", "")
                        break

            if not cover_href or cover_href not in zf.namelist():
                return None

            img_bytes = zf.read(cover_href)
            ext = Path(cover_href).suffix or ".jpg"
            cover_path = work_dir / f"cover{ext}"
            cover_path.write_bytes(img_bytes)
            return cover_path
    except Exception as e:
        print(f"  WARNING: EPUB cover extraction failed ({e}), skipping cover")
        return None


# ── MP3 side product ──────────────────────────────────────────────────────

def _write_mp3_side_product(
    chapter_m4as: list,
    chapter_results: list,
    out_dir: Path,
    ffmpeg: str,
) -> None:
    """Encode each chapter M4A to MP3 in out_dir."""
    out_dir.mkdir(exist_ok=True)
    for i, (m4a, ch) in enumerate(zip(chapter_m4as, chapter_results)):
        name = f"{i + 1:02d}_{safe_filename(ch['title'])}.mp3"
        dest = out_dir / name
        _run_ffmpeg(
            [ffmpeg, "-y", "-nostdin", "-i", str(m4a),
             "-c:a", "libmp3lame", "-b:a", "128k", str(dest)],
            f"MP3 encode {name}",
        )


# ── report.md ─────────────────────────────────────────────────────────────

def _write_report_md(
    path: Path,
    manifest_qa: dict,
    synth_report,           # SynthReport | None
    loudness_results: list,
    output_path: Path,
    chapter_results: list,
    target_lufs: float = -18.0,
    chapter_gate: Optional[dict] = None,
) -> None:
    """Write report.md consolidating all QA data from the pipeline."""
    lines = ["# Audiobook Build Report\n"]

    # ── Source / extraction ───────────────────────────────────────────────
    lines.append("## Extraction\n")
    pages_flagged = manifest_qa.get("pages_flagged", [])
    mean_conf = manifest_qa.get("mean_ocr_confidence")
    if mean_conf is not None:
        lines.append(f"- Mean OCR confidence: {mean_conf:.2f}")
    if pages_flagged:
        indices = ", ".join(str(p) for p in pages_flagged[:20])
        more = f" … +{len(pages_flagged) - 20} more" if len(pages_flagged) > 20 else ""
        lines.append(f"- Flagged pages: {len(pages_flagged)} (indices: {indices}{more})")
    else:
        lines.append("- Flagged pages: none")

    # ── Segmentation ──────────────────────────────────────────────────────
    lines.append("\n## Segmentation\n")
    header_rm = manifest_qa.get("header_lines_removed")
    footnotes  = manifest_qa.get("footnotes_separated")
    if header_rm is not None:
        lines.append(f"- Header lines removed: {header_rm}")
    if footnotes is not None:
        lines.append(f"- Footnotes separated: {footnotes}")

    # ── Synthesis ─────────────────────────────────────────────────────────
    lines.append("\n## Synthesis\n")
    if synth_report is not None:
        lines.append(
            f"- Chunks: done {synth_report.done}  "
            f"cached {synth_report.cached}  "
            f"retried {synth_report.retried}  "
            f"failed {synth_report.failed}"
        )
        if synth_report.lint_issues:
            lines.append(f"- Lint warnings: {len(synth_report.lint_issues)}\n")
            lines.append("| Chapter | Pattern | Snippet |")
            lines.append("|---------|---------|---------|")
            for issue in synth_report.lint_issues:
                snippet = issue.get("snippet", "")[:60].replace("|", "\\|")
                lines.append(
                    f"| {issue.get('chapter', '')[:30]} "
                    f"| {issue.get('pattern', '')} "
                    f"| {snippet} |"
                )
        else:
            lines.append("- Lint warnings: none")
        if synth_report.failed_chunks:
            lines.append(f"\n- **Failed chunks:** {len(synth_report.failed_chunks)}\n")
            lines.append("| Chapter | Chunk | Text |")
            lines.append("|---------|-------|------|")
            for fc in synth_report.failed_chunks:
                text = fc.get("text", "")[:60].replace("|", "\\|")
                lines.append(
                    f"| {fc.get('chapter', '')[:30]} "
                    f"| {fc.get('chunk_idx', '')} "
                    f"| {text} |"
                )
    else:
        lines.append("- Synthesis stats not available (build reused existing audio)")

    # ── Loudness ──────────────────────────────────────────────────────────
    lines.append(f"\n## Mastering — Loudness\n")
    lines.append(f"**Target:** {target_lufs:+.1f} LUFS  **Tolerance:** ±1.0 LU\n")
    if loudness_results:
        lines.append("| # | Chapter | Input LUFS | Output LUFS | Gate |")
        lines.append("|---|---------|-----------|------------|------|")
        for i, lr in enumerate(loudness_results):
            gate = "PASS" if lr.within_gate else "**FAIL**"
            lines.append(
                f"| {i + 1} | {lr.chapter_title[:40]} "
                f"| {lr.input_i:+.1f} "
                f"| {lr.output_i:+.1f} "
                f"| {gate} |"
            )
        n_pass = sum(1 for lr in loudness_results if lr.within_gate)
        n_fail = len(loudness_results) - n_pass
        if n_fail == 0:
            lines.append(f"\nAll {len(loudness_results)} chapters within ±1 LU: **PASS**")
        else:
            lines.append(f"\n{n_fail} chapter(s) outside ±1 LU tolerance: **FAIL**")
    else:
        lines.append("No loudness measurements available.")

    # ── Chapter gate ──────────────────────────────────────────────────────
    lines.append("\n## Chapter Gate\n")
    if chapter_gate:
        if chapter_gate.get("error"):
            lines.append(f"- {chapter_gate['error']}")
        elif chapter_gate.get("ok") is True:
            lines.append(f"- Chapter count: {chapter_gate['chapter_count']} **PASS**")
            short = chapter_gate.get("short_chapters", [])
            if short:
                for sc in short:
                    lines.append(f"- WARNING: short chapter '{sc['title'][:40]}' "
                                 f"({sc['duration_s']:.0f} s < {SHORT_CHAPTER_THRESHOLD_S} s)")
            else:
                lines.append("- No suspiciously short chapters detected")
        else:
            lines.append(
                f"- Chapter count: expected {chapter_gate.get('expected_count')}, "
                f"got {chapter_gate.get('chapter_count')} **FAIL**"
            )
    else:
        lines.append("- Gate not run")

    # ── Output summary ────────────────────────────────────────────────────
    lines.append("\n## Output\n")
    total_ms = sum(ch["duration_ms"] for ch in chapter_results)
    h = total_ms // 3_600_000
    m = (total_ms % 3_600_000) // 60_000
    s = (total_ms % 60_000) // 1000
    dur_str = f"{h} h {m:02d} m {s:02d} s" if h else f"{m} m {s:02d} s"
    lines.append(f"- **Duration:** {dur_str}")
    lines.append(f"- **Chapters:** {len(chapter_results)}")
    if output_path.exists():
        mb = output_path.stat().st_size / 1024 / 1024
        lines.append(f"- **File:** `{output_path}`  ({mb:.0f} MB)")
    else:
        lines.append(f"- **File:** `{output_path}`")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── mastering cache ───────────────────────────────────────────────────────

def _wav_sha256(wav_path: Path) -> str:
    h = hashlib.sha256()
    with open(wav_path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def _master_cache_path(m4a_path: Path) -> Path:
    return m4a_path.with_suffix(".cache.json")


def _master_cache_hit(m4a_path: Path, wav_sha: str,
                      target_lufs: float, aac_bitrate: str,
                      target_lra: float = 11.0) -> Optional[float]:
    """Return cached output_i LUFS if the M4A is fresh, else None."""
    if not m4a_path.exists():
        return None
    cache_path = _master_cache_path(m4a_path)
    if not cache_path.exists():
        return None
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        if (data.get("wav_sha256") == wav_sha
                and data.get("target_lufs") == target_lufs
                and data.get("target_lra", 11.0) == target_lra
                and data.get("aac_bitrate") == aac_bitrate):
            return float(data["output_i"])
    except Exception:
        pass
    return None


def _master_cache_write(m4a_path: Path, wav_sha: str,
                        target_lufs: float, aac_bitrate: str, output_i: float,
                        target_lra: float = 11.0) -> None:
    cache_path = _master_cache_path(m4a_path)
    cache_path.write_text(
        json.dumps({"wav_sha256": wav_sha, "target_lufs": target_lufs,
                    "target_lra": target_lra,
                    "aac_bitrate": aac_bitrate, "output_i": output_i}),
        encoding="utf-8",
    )


# ── duration / marker-count gates ────────────────────────────────────────

def _check_m4b_chapters(m4b_path: Path, expected_count: int) -> dict:
    """Verify chapter count and flag suspiciously short chapters via ffprobe.

    Returns {ok, chapter_count, short_chapters, error}.
    """
    try:
        from .binaries import find_ffprobe
        ffprobe = find_ffprobe()
        if not ffprobe:
            return {"ok": None, "error": "ffprobe not found; skipping chapter gate"}
    except Exception:
        return {"ok": None, "error": "ffprobe not available; skipping chapter gate"}

    result = subprocess.run(
        [ffprobe, "-v", "quiet", "-print_format", "json",
         "-show_chapters", str(m4b_path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return {"ok": False, "error": f"ffprobe failed: {result.stderr[-200:]}"}

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        return {"ok": False, "error": f"ffprobe JSON parse error: {e}"}

    chapters = data.get("chapters", [])
    actual_count = len(chapters)

    short = []
    for ch in chapters:
        try:
            duration_s = float(ch.get("end_time", 0)) - float(ch.get("start_time", 0))
            title = ch.get("tags", {}).get("title", f"Chapter {ch.get('id', '?')}")
            if duration_s < SHORT_CHAPTER_THRESHOLD_S:
                short.append({"title": title, "duration_s": round(duration_s, 1)})
        except (ValueError, TypeError):
            pass

    ok = actual_count == expected_count
    return {
        "ok": ok,
        "chapter_count": actual_count,
        "expected_count": expected_count,
        "short_chapters": short,
        "error": None,
    }


# ── main entry point ──────────────────────────────────────────────────────

def compile_m4b(
    chapter_results: list,
    output_stem: str,
    title: str = "",
    author: str = "",
    narrator: str = "",
    year: str = "",
    language: str = "en",
    publisher: str = "",
    target_lufs: float = -18.0,
    target_lra: float = 11.0,
    target_tp: float = -1.5,
    inter_chapter_silence_ms: int = 1500,
    aac_bitrate: str = "64k",
    pdf_path: Optional[Path] = None,
    cover_path: Optional[Path] = None,   # explicit override; supersedes pdf_path render
    work_dir: Optional[Path] = None,
    synth_report=None,
    manifest_qa: Optional[dict] = None,
) -> Path:
    """Normalize, assemble, and package chapter WAVs into a .m4b audiobook.

    Constant-memory: never loads whole-book audio into Python RAM.
    """
    if not chapter_results:
        raise RuntimeError("No chapters to compile.")

    ffmpeg = require_ffmpeg()

    if work_dir is None:
        work_dir = Path(f"{output_stem}_workdir")

    normalized_dir = work_dir / "normalized"
    normalized_dir.mkdir(parents=True, exist_ok=True)

    m4b_path = Path(f"{output_stem}.m4b")

    print("\n[5/5] Mastering & packaging...")

    # Probe sample rate from the first chapter WAV
    first_wav = chapter_results[0]["wav"]
    try:
        sample_rate, _ = _wav_sample_rate(first_wav)
    except Exception:
        sample_rate = 24000  # Kokoro default

    # ── Per-chapter loudnorm + AAC encode (with mastering cache) ─────────
    chapter_m4as = []
    loudness_results = []

    for i, ch in enumerate(chapter_results):
        out_m4a = normalized_dir / f"{i + 1:02d}_{safe_filename(ch['title'])}.m4a"
        print(f"  [{i + 1}/{len(chapter_results)}] {ch['title'][:50]}", end="", flush=True)

        # Check mastering cache: if WAV unchanged and settings match, reuse M4A
        wav_sha = _wav_sha256(ch["wav"])
        cached_i = _master_cache_hit(out_m4a, wav_sha, target_lufs, aac_bitrate,
                                       target_lra=target_lra)
        if cached_i is not None:
            within_gate = abs(cached_i - target_lufs) <= 1.0
            gate_str = "PASS" if within_gate else "FAIL"
            print(f"  {cached_i:+.1f} LUFS  [{gate_str}]  (cached)")
            loudness_results.append(LoudnessResult(
                chapter_title=ch["title"],
                input_i=cached_i,
                output_i=cached_i,
                within_gate=within_gate,
            ))
        else:
            lr = loudnorm_chapter(
                ch["wav"], out_m4a, ch["title"], ffmpeg,
                target_lufs=target_lufs, target_tp=target_tp,
                target_lra=target_lra, aac_bitrate=aac_bitrate,
            )
            gate_str = "PASS" if lr.within_gate else "FAIL"
            print(f"  {lr.input_i:+.1f} → {lr.output_i:+.1f} LUFS  [{gate_str}]")
            _master_cache_write(out_m4a, wav_sha, target_lufs, aac_bitrate, lr.output_i,
                                target_lra=target_lra)
            loudness_results.append(lr)

        chapter_m4as.append(out_m4a)

    n_fail = sum(1 for lr in loudness_results if not lr.within_gate)
    if n_fail:
        print(f"  WARNING: {n_fail} chapter(s) outside ±1 LU tolerance")

    # ── Silence file (reused between all chapters) ───────────────────────
    silence_m4a = _generate_silence_m4a(
        inter_chapter_silence_ms, normalized_dir, ffmpeg, aac_bitrate, sample_rate,
    )

    # ── Chapter timestamps & metadata ────────────────────────────────────
    timestamps_ms = _compute_chapter_timestamps(
        chapter_results, inter_chapter_silence_ms,
    )
    meta_path = work_dir / f"{Path(output_stem).name}_chapters.ffmeta"
    _write_ffmetadata(meta_path, chapter_results, timestamps_ms, title, author,
                      narrator=narrator, year=year,
                      language=language, publisher=publisher)

    # ── Concat list (chapters interleaved with silence) ───────────────────
    concat_items = []
    for i, m4a in enumerate(chapter_m4as):
        concat_items.append(m4a)
        if i < len(chapter_m4as) - 1:   # no trailing silence
            concat_items.append(silence_m4a)
    concat_path = work_dir / f"{Path(output_stem).name}_concat.txt"
    _write_concat_list(concat_path, concat_items)

    # ── Cover art ─────────────────────────────────────────────────────────
    # cover_path param takes precedence (CLI --cover override or EPUB-extracted cover)
    if not cover_path:
        cover_path = _render_cover(pdf_path, work_dir, title=title)

    # ── Assemble M4B via concat demuxer ──────────────────────────────────
    print("  Assembling M4B...")

    if cover_path:
        # Two-step: assemble audio, then embed cover
        temp_m4b = work_dir / f"{Path(output_stem).name}_temp.m4b"
        _run_ffmpeg(
            [ffmpeg, "-y", "-nostdin",
             "-f", "concat", "-safe", "0", "-i", str(concat_path),
             "-i", str(meta_path),
             "-map_metadata", "1",
             "-c:a", "copy",
             "-f", "mp4", str(temp_m4b)],
            "M4B concat assembly",
        )
        _run_ffmpeg(
            [ffmpeg, "-y", "-nostdin",
             "-i", str(temp_m4b),
             "-i", str(cover_path),
             "-map", "0", "-map", "1",
             "-c:a", "copy",
             "-c:v:0", "mjpeg",
             "-metadata:s:v:0", "comment=Cover (front)",
             "-disposition:v:0", "attached_pic",
             "-f", "mp4", str(m4b_path)],
            "M4B cover embedding",
        )
        temp_m4b.unlink(missing_ok=True)
    else:
        _run_ffmpeg(
            [ffmpeg, "-y", "-nostdin",
             "-f", "concat", "-safe", "0", "-i", str(concat_path),
             "-i", str(meta_path),
             "-map_metadata", "1",
             "-c:a", "copy",
             "-f", "mp4", str(m4b_path)],
            "M4B concat assembly",
        )

    # ── Chapter-count and duration sanity gate ───────────────────────────
    gate = _check_m4b_chapters(m4b_path, len(chapter_results))
    if gate.get("error"):
        print(f"  Chapter gate: {gate['error']}")
    elif not gate["ok"]:
        print(f"  WARNING: expected {gate['expected_count']} chapters in M4B, "
              f"got {gate['chapter_count']}")
    else:
        print(f"  Chapter gate: {gate['chapter_count']} chapters verified")
    for sc in gate.get("short_chapters", []):
        print(f"  WARNING: short chapter '{sc['title'][:40]}' "
              f"({sc['duration_s']:.0f} s < {SHORT_CHAPTER_THRESHOLD_S} s)")

    # ── MP3 side product ──────────────────────────────────────────────────
    mp3_dir = Path(f"{output_stem}_chapters_mp3")
    print(f"  Writing MP3 side product → {mp3_dir}/")
    _write_mp3_side_product(chapter_m4as, chapter_results, mp3_dir, ffmpeg)

    # ── report.md ─────────────────────────────────────────────────────────
    report_path = Path(f"{output_stem}_report.md")
    _write_report_md(
        report_path,
        manifest_qa or {},
        synth_report,
        loudness_results,
        m4b_path,
        chapter_results,
        target_lufs=target_lufs,
        chapter_gate=gate,
    )
    print(f"  QA report → {report_path}")

    # ── Cleanup temp files ────────────────────────────────────────────────
    concat_path.unlink(missing_ok=True)
    meta_path.unlink(missing_ok=True)
    silence_m4a.unlink(missing_ok=True)

    size_mb = m4b_path.stat().st_size / 1024 / 1024
    print(f"  M4B saved: {m4b_path}  ({size_mb:.0f} MB)")
    print(f"  {len(chapter_results)} chapters with navigation markers.")

    return m4b_path
