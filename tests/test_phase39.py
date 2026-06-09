"""Phase 39 — Cast audition mode. MockEngine only."""

import pytest

from vorpal.cli import build_parser
from vorpal.play.audition import (
    MAX_AUDITION_WORDS,
    build_audition,
    select_audition_lines,
)
from vorpal.play.casting import CastSheet
from vorpal.play.characters import Character
from vorpal.play.models import Act, Beat, PlayDoc, Scene
from vorpal.tts.mock_engine import MockEngine
from vorpal.tts.voices import VoiceEntry


# ── fixtures ─────────────────────────────────────────────────────────────────

def _play(speeches):
    """speeches: list of (speaker, text, tone_hint)."""
    play = PlayDoc(title="T", author="A")
    act = Act(name="Act I")
    scene = Scene(name="Scene I", location="")
    for speaker, text, hint in speeches:
        scene.beats.append(
            Beat(type="speech", speaker=speaker, text=text, tone_hint=hint))
    act.scenes.append(scene)
    play.acts.append(act)
    return play


@pytest.fixture
def play():
    return _play([
        ("HERO", "Short line.", None),
        ("HERO", " ".join(["word"] * 60) + ".", None),
        ("HERO", " ".join(["mid"] * 30) + ".", "somber"),
        ("HERO", " ".join(["also"] * 20) + ".", None),
        ("SIDEKICK", "A single decent line for the sidekick to read aloud.", None),
        ("WALKON", "Hm.", None),
    ])


@pytest.fixture
def cast():
    return [
        Character("HERO", 4, 112, "protagonist", "m"),
        Character("SIDEKICK", 1, 10, "major", "f"),
        Character("WALKON", 1, 1, "cameo", "unknown"),
    ]


@pytest.fixture
def sheet():
    return CastSheet(
        assignments={"HERO": "v_a", "SIDEKICK": "v_b", "WALKON": "v_c"},
        narrator_voice="v_n",
    )


@pytest.fixture
def voices():
    out = {}
    for vid in ("v_a", "v_b", "v_c", "v_n"):
        out[vid] = VoiceEntry(id=vid, display_name=vid, engine="kokoro",
                              params={"voice": vid}, description="mock")
    return out


def _factory(entry):
    return MockEngine(voice=entry.id)


# ── line selection ───────────────────────────────────────────────────────────

def test_longest_speech_selected_first(play):
    lines = select_audition_lines(play, "HERO")
    assert lines[0].text.startswith("word")


def test_max_three_lines(play):
    lines = select_audition_lines(play, "HERO")
    assert len(lines) <= 3


def test_word_cap_respected(play):
    lines = select_audition_lines(play, "HERO", max_words=70)
    total = sum(len(b.text.split()) for b in lines)
    assert total <= 70


def test_single_overlong_speech_still_selected():
    p = _play([("ORATOR", " ".join(["long"] * 500) + ".", None)])
    lines = select_audition_lines(p, "ORATOR", max_words=MAX_AUDITION_WORDS)
    assert len(lines) == 1


def test_unknown_character_empty(play):
    assert select_audition_lines(play, "NOBODY") == []


def test_tone_hint_preserved_in_selection(play):
    lines = select_audition_lines(play, "HERO")
    hints = {b.tone_hint for b in lines}
    assert "somber" in hints


# ── build_audition ───────────────────────────────────────────────────────────

def test_one_wav_per_non_cameo(play, cast, sheet, voices, tmp_path):
    results = build_audition(play, sheet, cast, tmp_path, voices,
                             engine_factory=_factory)
    assert set(results) == {"HERO", "SIDEKICK"}  # WALKON is cameo
    for path in results.values():
        assert path.exists()
        assert path.stat().st_size > 44  # more than a WAV header


def test_filenames_safe_and_named(play, cast, sheet, voices, tmp_path):
    results = build_audition(play, sheet, cast, tmp_path, voices,
                             engine_factory=_factory)
    assert results["HERO"].name == "HERO.wav"
    assert results["SIDEKICK"].name == "SIDEKICK.wav"


def test_multiword_character_filename(voices, tmp_path):
    p = _play([("FIRST CLOWN", "A line long enough to audition with.", None)])
    cast = [Character("FIRST CLOWN", 1, 8, "protagonist", "m")]
    sheet = CastSheet(assignments={"FIRST CLOWN": "v_a"})
    results = build_audition(p, sheet, cast, tmp_path, voices,
                             engine_factory=_factory)
    assert results["FIRST CLOWN"].name == "FIRST_CLOWN.wav"


def test_missing_voice_raises(play, cast, voices, tmp_path):
    bad_sheet = CastSheet(assignments={"HERO": "v_unknown",
                                       "SIDEKICK": "v_b",
                                       "WALKON": "v_c"})
    with pytest.raises(ValueError, match="HERO"):
        build_audition(play, bad_sheet, cast, tmp_path, voices,
                       engine_factory=_factory)


def test_audio_is_nonempty_audio(play, cast, sheet, voices, tmp_path):
    import soundfile as sf
    results = build_audition(play, sheet, cast, tmp_path, voices,
                             engine_factory=_factory)
    data, sr = sf.read(str(results["HERO"]))
    assert sr == MockEngine.sample_rate
    assert len(data) > sr  # more than a second of audition audio


# ── CLI parser ───────────────────────────────────────────────────────────────

def test_cast_audition_subcommand():
    args = build_parser().parse_args(["cast-audition", "hamlet.txt"])
    assert args.command == "cast-audition"
    assert args.output is None
    assert args.cast_override is None


def test_cast_audition_flags():
    args = build_parser().parse_args([
        "cast-audition", "hamlet.txt", "--output", "aud",
        "--cast-override", "ov.json",
    ])
    assert args.output == "aud"
    assert args.cast_override == "ov.json"
