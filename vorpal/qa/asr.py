"""ASR round-trip QA — Phase 12.

Transcribes a sampled fraction of synthesized chunks with a small local Whisper
model and computes word-error rate (WER) against the source text. Catches
mispronunciation, dropped-word, and derailment classes that nothing else catches.

Off by default: enabled with ``--asr-check`` on the build command.
GPU-accelerated when torch.cuda.is_available().

Unit tests exercise compute_wer() and sample_chunks() without any model.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np


# ── word-error rate ────────────────────────────────────────────────────────────


def _tokenize(text: str) -> list:
    """Lowercase, strip punctuation, split on whitespace."""
    text = text.lower()
    text = re.sub(r"[^\w\s']", " ", text)
    return text.split()


def compute_wer(reference: str, hypothesis: str) -> float:
    """Word error rate: (S + D + I) / len(reference_words).

    Uses the standard dynamic-programming edit distance at the word level.
    Returns 0.0 for identical strings, 1.0 or greater when hypothesis differs
    significantly, and exactly 0.0 when both are empty.
    """
    ref = _tokenize(reference)
    hyp = _tokenize(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0

    n = len(ref) + 1
    m = len(hyp) + 1
    # d[i][j] = edit distance between ref[:i] and hyp[:j]
    d = [[0] * m for _ in range(n)]
    for i in range(n):
        d[i][0] = i
    for j in range(m):
        d[0][j] = j
    for i in range(1, n):
        for j in range(1, m):
            cost = 0 if ref[i - 1] == hyp[j - 1] else 1
            d[i][j] = min(
                d[i - 1][j] + 1,        # deletion
                d[i][j - 1] + 1,        # insertion
                d[i - 1][j - 1] + cost, # substitution
            )
    return d[len(ref)][len(hyp)] / len(ref)


# ── chunk sampling ─────────────────────────────────────────────────────────────


def sample_chunks(chunks: list, fraction: float = 0.10) -> list:
    """Return a representative sample of chunks.

    Picks roughly ``fraction`` of chunks, evenly spaced so the sample spans
    the whole chapter rather than clustering at the start.  Always returns at
    least one chunk (if chunks is non-empty) and at most all chunks.
    Chunks shorter than 20 characters are skipped (intros, chapter titles).

    Args:
        chunks:   list of dicts with at least {"text": str}.
        fraction: fraction to sample (0 < fraction ≤ 1.0).

    Returns:
        List of (original_index, chunk_dict) tuples.
    """
    eligible = [(i, c) for i, c in enumerate(chunks)
                if len(c.get("text", "").strip()) >= 20]
    if not eligible:
        return []
    n = max(1, round(len(eligible) * max(0.0, min(1.0, fraction))))
    step = max(1, len(eligible) // n)
    return eligible[::step][:n]


# ── transcription + WER ────────────────────────────────────────────────────────


@dataclass
class ChunkASRResult:
    chunk_idx: int
    chapter: str
    text_snippet: str          # first 80 chars of source text
    wer: float
    transcript: str
    outlier: bool              # WER > outlier_threshold


def _load_whisper(model_name: str = "base", device: Optional[str] = None):
    """Load the Whisper model (downloads on first use, ~74 MB for base)."""
    try:
        import whisper
    except ImportError:
        raise RuntimeError(
            "ASR check requires openai-whisper: pip install openai-whisper"
        )
    import torch
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
    return whisper.load_model(model_name, device=device)


def transcribe_audio(audio: np.ndarray, sample_rate: int, model) -> str:
    """Transcribe a numpy audio array using a loaded Whisper model.

    Resamples to 16 kHz (Whisper's native rate) via linear interpolation if
    the input sample rate differs.
    """
    if len(audio) == 0:
        return ""

    # Whisper needs float32 at 16 kHz mono
    if sample_rate != 16000:
        import scipy.signal as ss
        target_len = int(len(audio) * 16000 / sample_rate)
        audio = ss.resample(audio.astype("float64"), target_len).astype("float32")
    else:
        audio = audio.astype("float32")

    result = model.transcribe(audio, language="en", fp16=False)
    return result.get("text", "").strip()


def run_asr_check(
    chunk_results: list,
    model_name: str = "base",
    sample_fraction: float = 0.10,
    outlier_wer: float = 0.30,
    chapter_name: str = "unknown",
) -> list:
    """Run ASR round-trip QA on a chapter's synthesized chunks.

    Args:
        chunk_results:   list of dicts: {text, audio (np.ndarray), sample_rate}.
        model_name:      Whisper model ("tiny", "base", "small" — base is the default).
        sample_fraction: fraction of chunks to transcribe (default 10 %).
        outlier_wer:     WER above this threshold is flagged as an outlier.
        chapter_name:    used only in the returned result structs.

    Returns:
        List of ChunkASRResult (only sampled chunks, not every chunk).
    """
    sample = sample_chunks(chunk_results, sample_fraction)
    if not sample:
        return []

    model = _load_whisper(model_name)
    results = []
    for orig_idx, chunk in sample:
        audio = chunk.get("audio")
        text = chunk.get("text", "")
        sample_rate = chunk.get("sample_rate", 24000)

        if audio is None or len(audio) == 0:
            transcript = ""
            wer = 1.0
        else:
            transcript = transcribe_audio(audio, sample_rate, model)
            wer = compute_wer(text, transcript)

        results.append(ChunkASRResult(
            chunk_idx=orig_idx,
            chapter=chapter_name,
            text_snippet=text[:80],
            wer=round(wer, 4),
            transcript=transcript[:120],
            outlier=wer > outlier_wer,
        ))
    return results


def check_chapters(
    chapter_entries: list,
    model_name: str = "base",
    sample_fraction: float = 0.10,
    outlier_wer: float = 0.30,
) -> list:
    """Run ASR QA across a sampled set of full chapters.

    Simpler than per-chunk checking; avoids the need to know chunk WAV
    boundaries within a chapter WAV. Uses the chapter WAV path directly.

    Args:
        chapter_entries: list of dicts: {title, wav_path (Path), body_text (str)}.
        model_name:      Whisper model name.
        sample_fraction: fraction of chapters to sample.
        outlier_wer:     WER above this flags an outlier.

    Returns:
        List of ChunkASRResult (one per sampled chapter).
    """
    import wave as _wave
    eligible = [(i, e) for i, e in enumerate(chapter_entries)
                if len(e.get("body_text", "").strip()) >= 50
                and Path(e.get("wav_path", "")).exists()]
    if not eligible:
        return []

    n = max(1, round(len(eligible) * max(0.0, min(1.0, sample_fraction))))
    step = max(1, len(eligible) // n)
    sample = eligible[::step][:n]

    model = _load_whisper(model_name)
    results = []
    for orig_idx, entry in sample:
        wav_path = Path(entry["wav_path"])
        body_text = entry.get("body_text", "")
        title = entry.get("title", f"chapter_{orig_idx}")

        with _wave.open(str(wav_path), "rb") as wf:
            sr = wf.getframerate()
            frames = wf.readframes(wf.getnframes())
        audio = np.frombuffer(frames, dtype="<i2").astype("float32") / 32768.0

        transcript = transcribe_audio(audio, sr, model)
        wer = compute_wer(body_text, transcript)

        results.append(ChunkASRResult(
            chunk_idx=orig_idx,
            chapter=title,
            text_snippet=body_text[:80],
            wer=round(wer, 4),
            transcript=transcript[:120],
            outlier=wer > outlier_wer,
        ))
    return results


# ── report section ─────────────────────────────────────────────────────────────


def format_asr_report(results: list, sample_fraction: float, model_name: str) -> str:
    """Format ASR results as a Markdown section for report.md."""
    lines = [f"\n## ASR Round-Trip QA\n"]
    lines.append(f"Model: `{model_name}`  Sample: {sample_fraction:.0%} of chunks\n")
    if not results:
        lines.append("- No chunks sampled.")
        return "\n".join(lines)

    outliers = [r for r in results if r.outlier]
    mean_wer = sum(r.wer for r in results) / len(results)
    lines.append(f"- Sampled chunks: {len(results)}  "
                 f"Outliers (WER > 30 %): {len(outliers)}  "
                 f"Mean WER: {mean_wer:.1%}\n")

    if outliers:
        lines.append("### Outliers\n")
        lines.append("| Chapter | Chunk | WER | Source (80 chars) | Transcript |")
        lines.append("|---------|-------|-----|-------------------|------------|")
        for r in outliers:
            src = r.text_snippet.replace("|", "\\|")
            trs = r.transcript.replace("|", "\\|")
            lines.append(f"| {r.chapter[:30]} | {r.chunk_idx} "
                         f"| {r.wer:.0%} | {src} | {trs} |")
    else:
        lines.append("- No outliers detected.")

    return "\n".join(lines)
