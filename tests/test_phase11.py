"""Phase 11 — tone effectiveness evaluation tests.

Uses MockEngine+KokoroApproxEngine so tests run without a real TTS model.
All tests are deterministic and fast.
"""

import json
import wave
from pathlib import Path

import numpy as np
import pytest

from vorpal.tts.mock_engine import MockEngine
from vorpal.tts.kokoro_approx import KokoroApproxEngine, TONE_SPEED
from vorpal.qa.tone_eval import (
    measure_audio,
    run_acoustic_gate,
    gate_summary,
    write_ab_kit,
    format_gate_report,
)


# ── measure_audio ─────────────────────────────────────────────────────────────


def test_measure_audio_silence():
    audio = np.zeros(2400, dtype="float32")
    m = measure_audio(audio, 24000)
    assert m["energy_rms"] == pytest.approx(0.0)
    assert m["duration_s"] == pytest.approx(0.1)
    assert m["dominant_freq_hz"] == pytest.approx(0.0)


def test_measure_audio_sine():
    """440 Hz sine: dominant_freq should be near 440 Hz."""
    sr = 24000
    t = np.arange(sr, dtype="float32") / sr  # 1 second
    audio = 0.5 * np.sin(2 * np.pi * 440 * t)
    m = measure_audio(audio, sr)
    assert m["duration_s"] == pytest.approx(1.0)
    assert abs(m["dominant_freq_hz"] - 440.0) < 50  # within 50 Hz
    assert m["energy_rms"] > 0


def test_measure_audio_empty():
    """Empty array returns zeros."""
    m = measure_audio(np.array([], dtype="float32"), 24000)
    assert m["energy_rms"] == 0.0
    assert m["duration_s"] == 0.0
    assert m["dominant_freq_hz"] == 0.0


# ── run_acoustic_gate + gate_summary ─────────────────────────────────────────


def _mock_approx(speed: float = 1.0) -> KokoroApproxEngine:
    mock = MockEngine(voice="mock_default", speed=speed)
    # patch _TONE_FREQ so non-neutral tones produce non-silent audio
    mock._TONE_FREQ = {
        None: 0, "neutral": 0,
        "somber": 110, "tense": 220, "warm": 330, "wry": 440,
        "excited": 550, "urgent": 660, "reflective": 770,
    }
    return KokoroApproxEngine(speed=speed, inner_engine=mock)


def test_run_acoustic_gate_returns_all_non_neutral_tones():
    eng = _mock_approx()
    text = "a" * 200  # long enough to exceed MockEngine min duration
    results = run_acoustic_gate(eng, text)
    expected = {t for t in TONE_SPEED if t != "neutral"}
    assert set(results.keys()) == expected


def test_run_acoustic_gate_non_unity_speed_passes():
    """Tones with speed ≠ 1.0 must produce a measurable duration difference."""
    eng = _mock_approx()
    text = "a" * 300
    results = run_acoustic_gate(eng, text)
    for tone, r in results.items():
        if TONE_SPEED[tone] != 1.0:
            assert r.passes, f"Expected {tone} (speed={TONE_SPEED[tone]}) to pass"


def test_run_acoustic_gate_wry_fails():
    """wry has speed=1.0 → no duration difference → fails the gate."""
    eng = _mock_approx()
    text = "a" * 200
    results = run_acoustic_gate(eng, text)
    assert not results["wry"].passes, "wry (speed=1.0) should fail the gate"


def test_gate_summary_verdict():
    eng = _mock_approx()
    text = "a" * 300
    results = run_acoustic_gate(eng, text)
    summary = gate_summary(results)
    # wry is the only expected failure; no unexpected failures
    assert "wry" in summary["expected_fail"]
    assert summary["unexpected_fail"] == []
    assert summary["verdict"] == "PASS"


def test_gate_summary_unexpected_fail_detected():
    """Simulate a tone with speed != 1.0 failing — verdict is FAIL."""
    from vorpal.qa.tone_eval import ToneDeltaResult
    fake_results = {
        "somber": ToneDeltaResult("somber", 0.88, 0.0, 0.0, False, 10.0, 10.8),
        "wry": ToneDeltaResult("wry", 1.00, 0.0, 0.0, False, 10.0, 10.0),
    }
    summary = gate_summary(fake_results)
    assert "somber" in summary["unexpected_fail"]
    assert summary["verdict"] == "FAIL"


# ── write_ab_kit ──────────────────────────────────────────────────────────────


def _make_audio(seconds: float, sr: int = 24000) -> np.ndarray:
    return (np.random.rand(int(seconds * sr)).astype("float32") - 0.5) * 0.1


def test_write_ab_kit_creates_files(tmp_path):
    sr = 24000
    neutral = _make_audio(90, sr)   # longer than 60s clip
    expressive = _make_audio(90, sr)
    manifest_path = write_ab_kit(neutral, expressive, sr,
                                  tmp_path / "ab_kit", "Chapter One")
    assert manifest_path.exists()
    assert (tmp_path / "ab_kit" / "neutral_chapter_one.wav").exists()
    assert (tmp_path / "ab_kit" / "expressive_chapter_one.wav").exists()


def test_write_ab_kit_clips_to_target_length(tmp_path):
    sr = 24000
    neutral = _make_audio(120, sr)
    expressive = _make_audio(120, sr)
    ab_dir = tmp_path / "ab_kit"
    write_ab_kit(neutral, expressive, sr, ab_dir, "Test", clip_seconds=60.0)
    wav_path = ab_dir / "neutral_test.wav"
    with wave.open(str(wav_path), "rb") as wf:
        actual_s = wf.getnframes() / wf.getframerate()
    assert abs(actual_s - 60.0) < 0.5


def test_write_ab_kit_manifest_accumulates(tmp_path):
    sr = 24000
    ab_dir = tmp_path / "ab_kit"
    for title in ["Chapter One", "Chapter Two"]:
        write_ab_kit(_make_audio(30, sr), _make_audio(30, sr), sr, ab_dir, title)
    entries = json.loads((ab_dir / "manifest.json").read_text(encoding="utf-8"))
    assert len(entries) == 2
    assert entries[0]["chapter"] == "Chapter One"
    assert entries[1]["chapter"] == "Chapter Two"


# ── format_gate_report ────────────────────────────────────────────────────────


def test_format_gate_report_contains_all_tones():
    eng = _mock_approx()
    results = run_acoustic_gate(eng, "a" * 300)
    summary = gate_summary(results)
    report = format_gate_report(results, summary, title="Gate Test")
    for tone in TONE_SPEED:
        if tone != "neutral":
            assert tone in report
    assert "PASS" in report or "FAIL" in report
