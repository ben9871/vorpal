"""Discovery of external binaries (Tesseract, ffmpeg).

Resolution order, per binary:
  1. Environment variable override (VORPAL_TESSERACT / VORPAL_FFMPEG)
  2. PATH lookup via shutil.which
  3. Known platform-specific install locations

Returns None when not found; callers raise a MissingBinaryError with install
guidance so the user gets one clear message instead of a stack trace.
"""

import os
import shutil

TESSERACT_ENV = "VORPAL_TESSERACT"
FFMPEG_ENV = "VORPAL_FFMPEG"

_TESSERACT_FALLBACKS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]

_FFMPEG_FALLBACKS = [
    r"C:\ffmpeg\bin\ffmpeg.exe",
]


class MissingBinaryError(RuntimeError):
    pass


def _find(name: str, env_var: str, fallbacks: list) -> str | None:
    override = os.environ.get(env_var)
    if override and os.path.exists(override):
        return override
    on_path = shutil.which(name)
    if on_path:
        return on_path
    for candidate in fallbacks:
        if os.path.exists(candidate):
            return candidate
    return None


def find_tesseract() -> str | None:
    return _find("tesseract", TESSERACT_ENV, _TESSERACT_FALLBACKS)


def find_ffmpeg() -> str | None:
    return _find("ffmpeg", FFMPEG_ENV, _FFMPEG_FALLBACKS)


def require_tesseract() -> str:
    path = find_tesseract()
    if not path:
        raise MissingBinaryError(
            "Tesseract OCR not found.\n"
            "  Install: https://github.com/UB-Mannheim/tesseract/wiki (Windows)\n"
            f"  Or set {TESSERACT_ENV} to the tesseract executable path."
        )
    return path


def require_ffmpeg() -> str:
    path = find_ffmpeg()
    if not path:
        raise MissingBinaryError(
            "ffmpeg not found.\n"
            "  Install: https://www.gyan.dev/ffmpeg/builds/ (Windows)\n"
            f"  Or set {FFMPEG_ENV} to the ffmpeg executable path."
        )
    return path


FFPROBE_ENV = "VORPAL_FFPROBE"

_FFPROBE_FALLBACKS = [
    r"C:\ffmpeg\bin\ffprobe.exe",
]


def find_ffprobe() -> str | None:
    return _find("ffprobe", FFPROBE_ENV, _FFPROBE_FALLBACKS)


def require_ffprobe() -> str:
    path = find_ffprobe()
    if not path:
        raise MissingBinaryError(
            "ffprobe not found.\n"
            "  Install: https://www.gyan.dev/ffmpeg/builds/ (Windows)\n"
            f"  Or set {FFPROBE_ENV} to the ffprobe executable path."
        )
    return path
