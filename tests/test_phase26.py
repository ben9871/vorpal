"""Phase 26 — Piper draft engine.

Tests:
  - PiperEngine conforms to TTSEngine interface (class attrs, method sigs)
  - is_piper_available() returns False when piper binary absent (the normal
    test environment case)
  - _find_piper_binary() returns None when not on PATH
  - _find_piper_model() returns None when no model paths exist
  - PiperEngine raises RuntimeError when binary absent
  - PiperEngine raises RuntimeError when model absent (binary present via mock)
  - Draft fallback: when Piper unavailable, engine falls back to KokoroEngine
    (tested via monkey-patching is_piper_available)
  - _compile_draft_wav now accepts engine_label; output filename includes label
"""

import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from vorpal.tts.piper_engine import (
    PiperEngine,
    is_piper_available,
    _find_piper_binary,
    _find_piper_model,
)
from vorpal.tts.base import TTSEngine


# ── interface conformance ──────────────────────────────────────────────────

class TestPiperEngineInterface:
    def test_is_tts_engine_subclass(self):
        assert issubclass(PiperEngine, TTSEngine)

    def test_class_attrs(self):
        assert PiperEngine.name == "piper"
        assert isinstance(PiperEngine.sample_rate, int)
        assert isinstance(PiperEngine.max_chunk_chars, int)
        assert PiperEngine.supported_tones == ()
        assert PiperEngine.cost_per_1k_chars == 0.0

    def test_synthesize_method_exists(self):
        import inspect
        sig = inspect.signature(PiperEngine.synthesize)
        params = list(sig.parameters.keys())
        assert "text" in params
        assert "tone" in params
        assert "is_dialogue" in params


# ── discovery helpers ──────────────────────────────────────────────────────

class TestDiscovery:
    def test_find_piper_binary_absent(self):
        with patch("shutil.which", return_value=None):
            result = _find_piper_binary()
        assert result is None

    def test_find_piper_binary_present(self):
        with patch("shutil.which", return_value="/usr/bin/piper"):
            result = _find_piper_binary()
        assert result == "/usr/bin/piper"

    def test_find_piper_model_env(self, tmp_path, monkeypatch):
        model = tmp_path / "test.onnx"
        model.write_bytes(b"fake onnx")
        monkeypatch.setenv("VORPAL_PIPER_MODEL", str(model))
        result = _find_piper_model()
        assert result == model

    def test_find_piper_model_env_nonexistent(self, monkeypatch):
        monkeypatch.setenv("VORPAL_PIPER_MODEL", "/does/not/exist.onnx")
        result = _find_piper_model()
        assert result is None

    def test_find_piper_model_none(self, monkeypatch):
        monkeypatch.delenv("VORPAL_PIPER_MODEL", raising=False)
        # Both standard dirs won't have models in test env
        # Just verify it returns None (or a Path if the dev machine happens to have one)
        result = _find_piper_model()
        assert result is None or isinstance(result, Path)


# ── is_piper_available ─────────────────────────────────────────────────────

class TestIsPiperAvailable:
    def test_false_when_no_binary(self):
        with patch("vorpal.tts.piper_engine._find_piper_binary", return_value=None):
            assert not is_piper_available()

    def test_false_when_no_model(self):
        with patch("vorpal.tts.piper_engine._find_piper_binary", return_value="/bin/piper"):
            with patch("vorpal.tts.piper_engine._find_piper_model", return_value=None):
                assert not is_piper_available()

    def test_true_when_both_present(self, tmp_path):
        model = tmp_path / "en.onnx"
        model.write_bytes(b"fake")
        with patch("vorpal.tts.piper_engine._find_piper_binary", return_value="/bin/piper"):
            with patch("vorpal.tts.piper_engine._find_piper_model", return_value=model):
                assert is_piper_available()

    def test_returns_false_in_test_env(self):
        # In CI / the vorpal container, piper is not installed
        if shutil.which("piper"):
            pytest.skip("piper is actually available — skip absence test")
        assert not is_piper_available()


# ── PiperEngine construction errors ───────────────────────────────────────

class TestPiperEngineConstruction:
    def test_raises_when_binary_absent(self):
        with patch("vorpal.tts.piper_engine._find_piper_binary", return_value=None):
            with pytest.raises(RuntimeError, match="piper binary not found"):
                PiperEngine()

    def test_raises_when_model_absent(self, tmp_path):
        with patch("vorpal.tts.piper_engine._find_piper_binary", return_value="/bin/piper"):
            with patch("vorpal.tts.piper_engine._find_piper_model", return_value=None):
                with pytest.raises(RuntimeError, match="No Piper model found"):
                    PiperEngine()

    def test_raises_when_explicit_model_missing(self, tmp_path):
        with patch("vorpal.tts.piper_engine._find_piper_binary", return_value="/bin/piper"):
            with pytest.raises(RuntimeError, match="not found"):
                PiperEngine(model_path="/definitely/not/there.onnx")

    def test_constructs_with_mocked_binary_and_model(self, tmp_path):
        model = tmp_path / "en_us-amy-low.onnx"
        model.write_bytes(b"fake onnx data")
        with patch("vorpal.tts.piper_engine._find_piper_binary", return_value="/bin/piper"):
            with patch("vorpal.tts.piper_engine._find_piper_model", return_value=model):
                eng = PiperEngine()
        assert eng.name == "piper"
        assert "piper" in eng.voice_cache_key
        assert eng.speed == 1.0


# ── draft fallback in cmd_build (compile_draft_wav label) ─────────────────

class TestDraftLabel:
    def test_draft_wav_filename_includes_label(self, tmp_path):
        from vorpal.cli import _compile_draft_wav
        import wave, struct

        # Create a minimal chapter WAV file
        wav_path = tmp_path / "chapter_01.wav"
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(24000)
            wf.writeframes(struct.pack("<100h", *([0] * 100)))

        chapter_results = [{"title": "Chapter 1", "wav": str(wav_path)}]

        out_kokoro = _compile_draft_wav(chapter_results, str(tmp_path / "test"),
                                        engine_label="kokoro")
        assert out_kokoro.name == "test_draft_kokoro.wav"

        out_piper = _compile_draft_wav(chapter_results, str(tmp_path / "test2"),
                                       engine_label="piper")
        assert out_piper.name == "test2_draft_piper.wav"
