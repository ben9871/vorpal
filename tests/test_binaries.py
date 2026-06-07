import pytest

from audiobooker import binaries


def test_env_override_wins(monkeypatch, tmp_path):
    fake = tmp_path / "tesseract.exe"
    fake.write_text("")
    monkeypatch.setenv(binaries.TESSERACT_ENV, str(fake))
    assert binaries.find_tesseract() == str(fake)


def test_missing_binary_returns_none(monkeypatch):
    monkeypatch.delenv(binaries.FFMPEG_ENV, raising=False)
    monkeypatch.setattr(binaries.shutil, "which", lambda name: None)
    monkeypatch.setattr(binaries, "_FFMPEG_FALLBACKS", ["X:\\does\\not\\exist.exe"])
    assert binaries.find_ffmpeg() is None


def test_require_raises_with_guidance(monkeypatch):
    monkeypatch.delenv(binaries.FFMPEG_ENV, raising=False)
    monkeypatch.setattr(binaries.shutil, "which", lambda name: None)
    monkeypatch.setattr(binaries, "_FFMPEG_FALLBACKS", [])
    with pytest.raises(binaries.MissingBinaryError, match="ffmpeg"):
        binaries.require_ffmpeg()
