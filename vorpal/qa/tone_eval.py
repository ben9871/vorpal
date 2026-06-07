"""Tone effectiveness evaluation — Phase 11.

Provides:
  measure_audio(audio, sample_rate)         → energy, duration, dominant_freq_hz
  run_acoustic_gate(engine, text)           → per-tone delta vs neutral
  write_ab_kit(neutral, expressive, sr, out_dir, chapter_title) → kit manifest path

All synthesis-dependent functions require a working TTSEngine (KokoroApproxEngine
for the approximation path, APIEngine for the real-API path). The measurement
functions are pure numpy+scipy and can run in any environment.

Dependencies: scipy (listed under [audio] extra in pyproject.toml).
Imported lazily so the deterministic pipeline never requires it.
"""

import json
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

from ..tts.kokoro_approx import TONE_SPEED, acoustic_delta


# ── audio feature measurement ────────────────────────────────────────────────


def measure_audio(audio: np.ndarray, sample_rate: int) -> dict:
    """Measure energy, duration, and dominant frequency of an audio array.

    Returns:
      energy_rms:       RMS amplitude (0–1 for normalised float32)
      duration_s:       duration in seconds
      dominant_freq_hz: frequency of the strongest spectral component (Hz);
                        0.0 for silent audio
    """
    duration_s = len(audio) / max(sample_rate, 1)
    rms = float(np.sqrt(np.mean(audio ** 2))) if len(audio) > 0 else 0.0

    dominant_freq = 0.0
    if len(audio) > 0 and rms > 1e-6:
        try:
            from scipy.signal import welch
            freqs, psd = welch(audio.astype("float64"), fs=sample_rate,
                               nperseg=min(1024, len(audio)))
            dominant_freq = float(freqs[np.argmax(psd)])
        except ImportError:
            # Fallback to numpy FFT if scipy unavailable
            fft = np.fft.rfft(audio)
            freq_bins = np.fft.rfftfreq(len(audio), d=1.0 / sample_rate)
            dominant_freq = float(freq_bins[np.argmax(np.abs(fft))])

    return {
        "energy_rms": round(rms, 6),
        "duration_s": round(duration_s, 4),
        "dominant_freq_hz": round(dominant_freq, 2),
    }


# ── acoustic delta gate ───────────────────────────────────────────────────────


@dataclass
class ToneDeltaResult:
    tone: str
    speed_multiplier: float
    dur_diff: float
    rms_diff: float
    passes: bool
    neutral_duration_s: float
    tonal_duration_s: float


def run_acoustic_gate(engine, text: str) -> dict:
    """Synthesize text under every non-neutral tone and measure delta vs neutral.

    Returns a dict mapping tone → ToneDeltaResult.  The engine should be a
    KokoroApproxEngine (or any TTSEngine with supported_tones declared).

    Tones with speed_multiplier == 1.0 (wry) will always fail since KokoroApprox
    realizes tone only through speed/pause adjustments.
    """
    sample_rate = engine.sample_rate

    neutral_audio = engine.synthesize(text, tone="neutral")
    if neutral_audio is None or len(neutral_audio) == 0:
        raise RuntimeError("Engine returned empty audio for neutral tone")

    results = {}
    for tone in sorted(TONE_SPEED.keys()):
        if tone == "neutral":
            continue
        tonal_audio = engine.synthesize(text, tone=tone)
        if tonal_audio is None or len(tonal_audio) == 0:
            results[tone] = ToneDeltaResult(
                tone=tone,
                speed_multiplier=TONE_SPEED[tone],
                dur_diff=0.0, rms_diff=0.0, passes=False,
                neutral_duration_s=len(neutral_audio) / sample_rate,
                tonal_duration_s=0.0,
            )
            continue
        delta = acoustic_delta(neutral_audio, tonal_audio, sample_rate)
        results[tone] = ToneDeltaResult(
            tone=tone,
            speed_multiplier=TONE_SPEED[tone],
            dur_diff=delta["dur_diff"],
            rms_diff=delta["rms_diff"],
            passes=delta["passes"],
            neutral_duration_s=len(neutral_audio) / sample_rate,
            tonal_duration_s=len(tonal_audio) / sample_rate,
        )

    return results


def gate_summary(results: dict) -> dict:
    """Summarise gate results: counts, pass list, fail list, overall verdict."""
    passes = [t for t, r in results.items() if r.passes]
    fails = [t for t, r in results.items() if not r.passes]
    expected_fails = {t for t, r in results.items() if r.speed_multiplier == 1.0}
    unexpected_fails = [t for t in fails if t not in expected_fails]
    return {
        "total": len(results),
        "pass": passes,
        "fail": fails,
        "expected_fail": sorted(expected_fails),
        "unexpected_fail": unexpected_fails,
        "verdict": "PASS" if not unexpected_fails else "FAIL",
    }


# ── A/B kit generation ────────────────────────────────────────────────────────


def _write_wav(path: Path, audio: np.ndarray, sample_rate: int) -> None:
    """Write a float32 numpy array to a 16-bit WAV file."""
    pcm = np.clip(audio * 32767, -32768, 32767).astype("<i2")
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())


def write_ab_kit(
    neutral_audio: np.ndarray,
    expressive_audio: np.ndarray,
    sample_rate: int,
    output_dir: Path,
    chapter_title: str = "sample",
    clip_seconds: float = 60.0,
) -> Path:
    """Write a paired A/B kit to output_dir.

    Clips both arrays to clip_seconds, writes:
      ab_kit/neutral_<slug>.wav
      ab_kit/expressive_<slug>.wav
      ab_kit/manifest.json  (cumulative — appended on each call)

    Returns the manifest path.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    clip_samples = int(clip_seconds * sample_rate)

    slug = "".join(c if c.isalnum() else "_" for c in chapter_title.lower())[:40]
    neutral_clip = neutral_audio[:clip_samples]
    expressive_clip = expressive_audio[:clip_samples]

    neutral_path = output_dir / f"neutral_{slug}.wav"
    expressive_path = output_dir / f"expressive_{slug}.wav"

    _write_wav(neutral_path, neutral_clip, sample_rate)
    _write_wav(expressive_path, expressive_clip, sample_rate)

    manifest_path = output_dir / "manifest.json"
    entries = []
    if manifest_path.exists():
        try:
            entries = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            entries = []

    entries.append({
        "chapter": chapter_title,
        "neutral": neutral_path.name,
        "expressive": expressive_path.name,
        "duration_s": round(len(neutral_clip) / sample_rate, 1),
    })
    manifest_path.write_text(json.dumps(entries, indent=2, ensure_ascii=False),
                              encoding="utf-8")
    return manifest_path


# ── report generation ─────────────────────────────────────────────────────────


def format_gate_report(results: dict, summary: dict, title: str = "") -> str:
    """Format a human-readable gate report."""
    lines = []
    if title:
        lines.append(f"## {title}\n")
    lines.append("| Tone | Speed | dur_diff | rms_diff | Gate |")
    lines.append("|------|-------|----------|----------|------|")
    for tone, r in sorted(results.items()):
        gate = "PASS" if r.passes else ("FAIL (expected)" if r.speed_multiplier == 1.0 else "**FAIL**")
        lines.append(
            f"| {tone:12s} | {r.speed_multiplier:.2f} "
            f"| {r.dur_diff:.4f} | {r.rms_diff:.4f} | {gate} |"
        )
    lines.append("")
    lines.append(f"**Overall:** {summary['verdict']}  "
                 f"({len(summary['pass'])}/{summary['total']} tones measurably distinct)")
    if summary["unexpected_fail"]:
        lines.append(f"⚠ Unexpected failures: {', '.join(summary['unexpected_fail'])}")
    return "\n".join(lines)
