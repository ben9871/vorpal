"""Phase 10 — Arc 2 hardening regression tests.

One test per bug found in the adversarial self-review pass.
"""

import io
import json
import struct

import numpy as np
import pytest


# ── Bug 1: api_engine._wav_bytes_to_array with data-before-fmt ───────────


def _make_wav(fmt_first: bool = True) -> bytes:
    """Build a minimal 16-bit mono PCM WAV.  fmt_first=False puts data before fmt."""
    sample = struct.pack("<h", 1000)  # one sample
    fmt_payload = struct.pack("<HHIIHH", 1, 1, 24000, 48000, 2, 16)
    data_payload = sample

    chunks_fmt_first = [
        b"fmt " + struct.pack("<I", len(fmt_payload)) + fmt_payload,
        b"data" + struct.pack("<I", len(data_payload)) + data_payload,
    ]
    chunks_data_first = list(reversed(chunks_fmt_first))
    chunks = chunks_fmt_first if fmt_first else chunks_data_first
    body = b"".join(chunks)
    return b"RIFF" + struct.pack("<I", 4 + len(body)) + b"WAVE" + body


def test_wav_bytes_to_array_normal():
    """Standard fmt-then-data WAV parses without error."""
    from vorpal.tts.api_engine import _wav_bytes_to_array
    arr = _wav_bytes_to_array(_make_wav(fmt_first=True))
    assert arr is not None
    assert len(arr) == 1


def test_wav_bytes_to_array_data_before_fmt_raises_valueerror():
    """data chunk before fmt chunk raises ValueError, not UnboundLocalError."""
    from vorpal.tts.api_engine import _wav_bytes_to_array
    with pytest.raises(ValueError, match="fmt chunk missing"):
        _wav_bytes_to_array(_make_wav(fmt_first=False))


def test_wav_bytes_to_array_invalid_riff():
    """Non-RIFF header raises ValueError."""
    from vorpal.tts.api_engine import _wav_bytes_to_array
    with pytest.raises(ValueError, match="not a valid WAV"):
        _wav_bytes_to_array(b"\x00" * 100)


# ── Bug 2: acoustic_delta with empty arrays ───────────────────────────────


def test_acoustic_delta_empty_first_raises():
    """Empty first array raises ValueError, not silent NaN."""
    from vorpal.tts.kokoro_approx import acoustic_delta
    with pytest.raises(ValueError, match="non-empty"):
        acoustic_delta(np.array([]), np.array([1.0, 2.0]), 24000)


def test_acoustic_delta_empty_second_raises():
    """Empty second array raises ValueError."""
    from vorpal.tts.kokoro_approx import acoustic_delta
    with pytest.raises(ValueError, match="non-empty"):
        acoustic_delta(np.array([1.0, 2.0]), np.array([]), 24000)


def test_acoustic_delta_both_empty_raises():
    """Both empty arrays raises ValueError."""
    from vorpal.tts.kokoro_approx import acoustic_delta
    with pytest.raises(ValueError, match="non-empty"):
        acoustic_delta(np.array([]), np.array([]), 24000)


def test_acoustic_delta_normal_still_works():
    """Normal non-empty arrays continue to return a dict."""
    from vorpal.tts.kokoro_approx import acoustic_delta
    a = np.ones(2400, dtype="float32") * 0.5
    b = np.ones(2000, dtype="float32") * 0.6
    result = acoustic_delta(a, b, 24000)
    assert "passes" in result
    assert isinstance(result["passes"], bool)


# ── Bug 3: tone.py cache OSError not caught ───────────────────────────────


def test_tag_chapter_cache_oserror_caught(tmp_path, monkeypatch):
    """OSError during tone cache read is caught; function falls through to tagger."""
    import pathlib
    from vorpal.tone import _chapter_cache_key, tag_chapter
    import vorpal.tone as tone_mod

    body = "para one.\n\npara two."
    ck = _chapter_cache_key(body, "claude-haiku-4-5", "cli")
    cache_file = tmp_path / f"tone_{ck}.json"
    cache_file.write_text('{}')  # exists, but we'll make the read fail

    # Patch read_text to raise FileNotFoundError on the first call
    call_count = [0]
    real_read_text = pathlib.Path.read_text

    def patched_read(self, *args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            raise FileNotFoundError("simulated race condition")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "read_text", patched_read)

    # Mock the backend so we don't need a real LLM
    def mock_backend(paragraphs, title, model, backend):
        return [{"idx": i, "tone": "neutral", "confidence": 0.9}
                for i in range(len(paragraphs))]

    monkeypatch.setattr(tone_mod, "_tag_via_backend", mock_backend)

    result = tag_chapter(body, "Test", tmp_path)
    # OSError was caught; re-tag was attempted and succeeded
    assert result["tones"] == ["neutral", "neutral"]
    assert not result["cache_hit"]


# ── Bug 4: epub._html_to_text decoding ───────────────────────────────────


def test_html_to_text_latin1_fallback():
    """Latin-1 encoded HTML (not valid UTF-8) falls back gracefully."""
    from vorpal.extract.epub import _html_to_text
    # Craft bytes that are valid latin-1 but invalid utf-8
    # 0x80-0xBF bytes are continuation bytes in UTF-8 — invalid as starters
    latin1_bytes = b"<p>caf\xe9</p>"  # "café" in latin-1
    text = _html_to_text(latin1_bytes)
    assert "caf" in text
    assert "�" not in text  # no replacement character — fell back to latin-1


def test_html_to_text_utf8_works():
    """Valid UTF-8 HTML parses cleanly."""
    from vorpal.extract.epub import _html_to_text
    utf8_bytes = "<p>café</p>".encode("utf-8")  # "café" in UTF-8
    text = _html_to_text(utf8_bytes)
    assert "café" in text
