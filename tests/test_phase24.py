"""Phase 24 — dialogue-aware delivery.

Tests:
  - detect_dialogue_fraction: ASCII quotes, curly quotes, scare quotes,
    unclosed quotes, empty input
  - is_dialogue_chunk: threshold boundary
  - Chunk.is_dialogue propagation through normalize_chapter
  - Cache key has _dlg suffix iff engine.dialogue_style is set AND chunk.is_dialogue
  - KokoroApproxEngine: dialogue_style="subtle" applies DIALOGUE_SPEED shift;
    None keeps identical speed to pre-Phase-24
  - VoiceEntry accepts dialogue_style field (default None)
"""

import numpy as np
import pytest

from vorpal.segment.dialogue import detect_dialogue_fraction, is_dialogue_chunk
from vorpal.normalize import normalize_chapter, Chunk
from vorpal.synth import _cache_key
from vorpal.tts.kokoro_approx import KokoroApproxEngine, DIALOGUE_SPEED, TONE_SPEED
from vorpal.tts.mock_engine import MockEngine
from vorpal.tts.voices import VoiceEntry


# ── dialogue detection ─────────────────────────────────────────────────────

class TestDetectDialogueFraction:
    def test_empty(self):
        assert detect_dialogue_fraction("") == 0.0

    def test_whitespace_only(self):
        assert detect_dialogue_fraction("   \t\n  ") == 0.0

    def test_no_quotes(self):
        result = detect_dialogue_fraction("He walked into the room and sat down.")
        assert result == 0.0

    def test_scare_quotes_low(self):
        # Only 2 short quoted words in a long sentence → low fraction
        result = detect_dialogue_fraction(
            'The so-called "experts" disagreed with the "facts".'
        )
        assert result < 0.5

    def test_short_dialogue_high(self):
        # "Where are you going?" = 19/27 non-ws → ~70% dialogue
        result = detect_dialogue_fraction('"Where are you going?" he asked.')
        assert result >= 0.5

    def test_full_dialogue(self):
        result = detect_dialogue_fraction('"Where are you going?" he asked.')
        assert result >= 0.5

    def test_ascii_quotes(self):
        result = detect_dialogue_fraction('"Hello, world!"')
        assert result == 1.0

    def test_curly_quotes(self):
        result = detect_dialogue_fraction('“Hello, world!”')
        assert result == 1.0

    def test_unclosed_quotes_ignored(self):
        # Unclosed opening quote — should not count
        result = detect_dialogue_fraction('"Hello, and he walked on without finishing')
        assert result == 0.0

    def test_mixed_narration_dialogue(self):
        # Short quoted reply inside longer narration
        result = detect_dialogue_fraction(
            'He paused and then said "No" before leaving the room quickly.'
        )
        assert result < 0.5

    def test_range(self):
        val = detect_dialogue_fraction('"Test"')
        assert 0.0 <= val <= 1.0


class TestIsDialogueChunk:
    def test_default_threshold(self):
        assert is_dialogue_chunk('"Where are you going?" he asked.')
        assert not is_dialogue_chunk('He walked into the room.')

    def test_custom_threshold(self):
        text = '"Yes," she said.'
        frac = detect_dialogue_fraction(text)
        assert is_dialogue_chunk(text, threshold=frac - 0.01)
        assert not is_dialogue_chunk(text, threshold=frac + 0.01)


# ── normalize_chapter propagation ─────────────────────────────────────────

class TestChunkIsDialogue:
    def test_dialogue_chunk_flagged(self):
        chapter = '"Where are you going?" he asked. "Nowhere," she replied. '
        chunks = normalize_chapter(chapter)
        # At least one chunk should be dialogue
        assert any(c.is_dialogue for c in chunks)

    def test_narration_not_flagged(self):
        chapter = (
            'He walked slowly down the corridor. '
            'The doors were all closed. '
            'Nobody was waiting for him.'
        )
        chunks = normalize_chapter(chapter)
        assert all(not c.is_dialogue for c in chunks)

    def test_is_dialogue_default_false(self):
        # Chunk constructed without is_dialogue uses False
        c = Chunk(0, "Hello", 0, None, "abc123")
        assert c.is_dialogue is False


# ── cache key _dlg suffix ──────────────────────────────────────────────────

class TestCacheKey:
    def _make_chunk(self, is_dialogue: bool) -> Chunk:
        return Chunk(0, "Test text", 0, None, "testhash", is_dialogue)

    def test_no_dialogue_style_no_suffix(self):
        engine = MockEngine()
        assert not hasattr(engine, "dialogue_style") or engine.dialogue_style is None
        chunk = self._make_chunk(is_dialogue=True)
        key = _cache_key(chunk, engine)
        assert "_dlg" not in key

    def test_dialogue_style_none_no_suffix(self):
        engine = KokoroApproxEngine(inner_engine=MockEngine(), dialogue_style=None)
        chunk = self._make_chunk(is_dialogue=True)
        key = _cache_key(chunk, engine)
        assert "_dlg" not in key

    def test_dialogue_style_set_narration_no_suffix(self):
        engine = KokoroApproxEngine(inner_engine=MockEngine(), dialogue_style="subtle")
        chunk = self._make_chunk(is_dialogue=False)
        key = _cache_key(chunk, engine)
        assert "_dlg" not in key

    def test_dialogue_style_set_dialogue_has_suffix(self):
        engine = KokoroApproxEngine(inner_engine=MockEngine(), dialogue_style="subtle")
        chunk = self._make_chunk(is_dialogue=True)
        key = _cache_key(chunk, engine)
        assert "_dlg" in key

    def test_different_keys_for_dlg_vs_narration(self):
        engine = KokoroApproxEngine(inner_engine=MockEngine(), dialogue_style="subtle")
        dlg_chunk = self._make_chunk(is_dialogue=True)
        nar_chunk = self._make_chunk(is_dialogue=False)
        assert _cache_key(dlg_chunk, engine) != _cache_key(nar_chunk, engine)


# ── KokoroApproxEngine dialogue speed shift ────────────────────────────────

class TestKokoroApproxDialogue:
    """Verify dialogue_style="subtle" applies DIALOGUE_SPEED shift to inner engine speed."""

    def _recorded_speed(self, engine: KokoroApproxEngine, is_dialogue: bool) -> float:
        """Synthesize and return the inner engine speed used during synthesis."""
        speeds_seen = []
        original_synth = engine._inner.synthesize

        def capturing_synth(text, tone=None, is_dialogue=False):
            speeds_seen.append(engine._inner.speed)
            return original_synth(text, tone=tone, is_dialogue=is_dialogue)

        engine._inner.synthesize = capturing_synth
        engine.synthesize("Test.", tone="neutral", is_dialogue=is_dialogue)
        engine._inner.synthesize = original_synth
        return speeds_seen[0] if speeds_seen else 1.0

    def test_no_dialogue_style_no_shift(self):
        inner = MockEngine()
        engine = KokoroApproxEngine(inner_engine=inner, speed=1.0, dialogue_style=None)
        speed_dlg = self._recorded_speed(engine, is_dialogue=True)
        speed_nar = self._recorded_speed(engine, is_dialogue=False)
        # Both should be same (neutral tone speed = 1.0 * 1.0 * 1.0)
        assert abs(speed_dlg - speed_nar) < 1e-6

    def test_subtle_style_applies_shift(self):
        inner = MockEngine()
        engine = KokoroApproxEngine(inner_engine=inner, speed=1.0, dialogue_style="subtle")
        speed_dlg = self._recorded_speed(engine, is_dialogue=True)
        speed_nar = self._recorded_speed(engine, is_dialogue=False)
        expected_nar = 1.0 * TONE_SPEED.get("neutral", 1.0)
        expected_dlg = expected_nar * DIALOGUE_SPEED
        assert abs(speed_nar - expected_nar) < 1e-6
        assert abs(speed_dlg - expected_dlg) < 1e-6

    def test_subtle_style_compound_with_tone(self):
        inner = MockEngine()
        engine = KokoroApproxEngine(inner_engine=inner, speed=1.0, dialogue_style="subtle")
        speeds_seen = []
        original = engine._inner.synthesize

        def capture(text, tone=None, is_dialogue=False):
            speeds_seen.append(engine._inner.speed)
            return original(text, tone=tone, is_dialogue=is_dialogue)

        engine._inner.synthesize = capture
        engine.synthesize("Test.", tone="somber", is_dialogue=True)
        engine._inner.synthesize = original

        expected = 1.0 * TONE_SPEED["somber"] * DIALOGUE_SPEED
        assert abs(speeds_seen[0] - expected) < 1e-6

    def test_byte_identical_default(self):
        """Default engine (no dialogue_style) produces identical audio for dlg vs narration."""
        inner = MockEngine()
        engine = KokoroApproxEngine(inner_engine=inner, speed=1.0)
        audio_nar = engine.synthesize("Same text.", tone="neutral", is_dialogue=False)
        audio_dlg = engine.synthesize("Same text.", tone="neutral", is_dialogue=True)
        np.testing.assert_array_equal(audio_nar, audio_dlg)

    def test_dialogue_style_stored(self):
        engine = KokoroApproxEngine(inner_engine=MockEngine(), dialogue_style="subtle")
        assert engine.dialogue_style == "subtle"

    def test_dialogue_style_default_none(self):
        engine = KokoroApproxEngine(inner_engine=MockEngine())
        assert engine.dialogue_style is None


# ── VoiceEntry dialogue_style field ───────────────────────────────────────

class TestVoiceEntryDialogueStyle:
    def test_default_none(self):
        entry = VoiceEntry(
            id="test", display_name="Test", engine="kokoro",
            params={"voice": "af_heart"}, description="Test voice"
        )
        assert entry.dialogue_style is None

    def test_explicit_subtle(self):
        entry = VoiceEntry(
            id="test", display_name="Test", engine="kokoro",
            params={"voice": "af_heart"}, description="Test voice",
            dialogue_style="subtle"
        )
        assert entry.dialogue_style == "subtle"
