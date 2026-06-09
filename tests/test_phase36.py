"""Phase 36 — Act/scene chapter structure for plays."""

import pytest

from vorpal.normalize import spoken_form
from vorpal.play.chapters import (
    _roman_to_int,
    build_play_chapters,
    scene_location,
)
from vorpal.play.models import Act, Beat, PlayDoc, Scene


# ── fixtures ─────────────────────────────────────────────────────────────────

def _speech(speaker, text):
    return Beat(type="speech", speaker=speaker, text=text)


def _direction(text):
    return Beat(type="direction", speaker=None, text=text)


@pytest.fixture
def play_3x2():
    """3 acts × 2 scenes, locations on the scene headers."""
    play = PlayDoc(title="THE FIXTURE", author="Nobody")
    for a in range(1, 4):
        act = Act(name=f"Act {'I' * a}")
        for s, numeral in enumerate(["I", "II"], start=1):
            scene = Scene(
                name=f"Scene {numeral}",
                location=f"A room, number {a}{s}.",
            )
            scene.beats = [
                _direction("[Enter ALICE.]"),
                _speech("ALICE", f"Speech in act {a} scene {s}."),
            ]
            act.scenes.append(scene)
        play.acts.append(act)
    return play


# ── act mode ─────────────────────────────────────────────────────────────────

def test_act_mode_chapter_count(play_3x2):
    chapters = build_play_chapters(play_3x2, mode="act")
    assert len(chapters) == 3
    assert [c["title"] for c in chapters] == ["Act I", "Act II", "Act III"]


def test_act_mode_is_default(play_3x2):
    assert build_play_chapters(play_3x2) == build_play_chapters(play_3x2, mode="act")


def test_act_mode_collects_all_scene_beats(play_3x2):
    chapters = build_play_chapters(play_3x2, mode="act")
    for ch in chapters:
        assert len(ch["beats"]) == 4  # 2 scenes × (direction + speech)
        assert ch["kind"] == "act"
        assert ch["skip"] is False


def test_act_mode_beat_order_preserved(play_3x2):
    chapters = build_play_chapters(play_3x2, mode="act")
    texts = [b.text for b in chapters[0]["beats"] if b.type == "speech"]
    assert texts == ["Speech in act 1 scene 1.", "Speech in act 1 scene 2."]


# ── scene mode ───────────────────────────────────────────────────────────────

def test_scene_mode_chapter_count(play_3x2):
    chapters = build_play_chapters(play_3x2, mode="scene")
    assert len(chapters) == 6
    assert all(c["kind"] == "scene" for c in chapters)


def test_scene_mode_titles_with_location(play_3x2):
    chapters = build_play_chapters(play_3x2, mode="scene")
    assert chapters[0]["title"] == "Act I, Scene 1 — A room, number 11."
    assert chapters[5]["title"] == "Act III, Scene 2 — A room, number 32."


def test_scene_mode_roman_numeral_converted(play_3x2):
    chapters = build_play_chapters(play_3x2, mode="scene")
    # Scene II → "Scene 2"
    assert "Scene 2" in chapters[1]["title"]


def test_scene_without_location_no_suffix():
    play = PlayDoc(title="T", author="A")
    act = Act(name="Act I")
    scene = Scene(name="Scene I", location="")
    scene.beats = [_speech("X Y", "Hello there.")]
    act.scenes.append(scene)
    play.acts.append(act)
    chapters = build_play_chapters(play, mode="scene")
    assert chapters[0]["title"] == "Act I, Scene 1"
    assert "—" not in chapters[0]["title"]


def test_location_falls_back_to_location_direction():
    """No header location → first location-classified direction is used."""
    scene = Scene(name="Scene I", location="")
    scene.beats = [
        _direction("Elsinore. A platform before the castle."),
        _speech("HAMLET", "Who's there?"),
    ]
    assert scene_location(scene) == "Elsinore. A platform before the castle."


def test_location_fallback_ignores_entry_exit():
    scene = Scene(name="Scene I", location="")
    scene.beats = [
        _direction("[Enter HAMLET and HORATIO.]"),
        _speech("HAMLET", "Who's there?"),
    ]
    assert scene_location(scene) == ""


def test_header_location_preferred_over_direction():
    scene = Scene(name="Scene I", location="The battlements.")
    scene.beats = [_direction("A dark hall in the castle.")]
    assert scene_location(scene) == "The battlements."


# ── empty chapters dropped ───────────────────────────────────────────────────

def test_empty_scene_dropped(play_3x2):
    play_3x2.acts[0].scenes.append(Scene(name="Scene III", location="Empty."))
    chapters = build_play_chapters(play_3x2, mode="scene")
    assert len(chapters) == 6  # still 6, the beat-less scene is dropped


def test_empty_act_dropped():
    play = PlayDoc(title="T", author="A")
    play.acts.append(Act(name="Act I"))  # no scenes at all
    act2 = Act(name="Act II")
    scene = Scene(name="Scene I", location="")
    scene.beats = [_speech("AB", "Words.")]
    act2.scenes.append(scene)
    play.acts.append(act2)
    chapters = build_play_chapters(play, mode="act")
    assert [c["title"] for c in chapters] == ["Act II"]


def test_invalid_mode_raises(play_3x2):
    with pytest.raises(ValueError):
        build_play_chapters(play_3x2, mode="chapter")


# ── titles survive spoken_form ───────────────────────────────────────────────

def test_titles_pass_spoken_form(play_3x2):
    for mode in ("act", "scene"):
        for ch in build_play_chapters(play_3x2, mode=mode):
            result = spoken_form(ch["title"])
            assert isinstance(result, str)
            assert result.strip()


# ── roman numeral helper ─────────────────────────────────────────────────────

def test_roman_to_int():
    assert _roman_to_int("I") == 1
    assert _roman_to_int("IV") == 4
    assert _roman_to_int("IX") == 9
    assert _roman_to_int("XII") == 12
    assert _roman_to_int("XL") == 40
    assert _roman_to_int("nope") is None
    assert _roman_to_int("") is None


# ── real-parser integration (inline fixture, no network) ─────────────────────

MINI_PLAY = """\
A MINI PLAY

by A. Fixture

ACT I.

SCENE I. A garden of talking flowers.

ROSE.
You can talk?

ALICE.
So can you.

SCENE II.

  A dark wood with no names.

ALICE.
This must be the wood.

ACT II.

SCENE I. The Queen's croquet-ground.

QUEEN.
Off with her head!
"""


def test_parsed_mini_play_act_mode():
    from vorpal.play.parser import parse_play
    play = parse_play(MINI_PLAY)
    chapters = build_play_chapters(play, mode="act")
    assert [c["title"] for c in chapters] == ["Act I", "Act II"]


def test_parsed_mini_play_scene_mode():
    from vorpal.play.parser import parse_play
    play = parse_play(MINI_PLAY)
    chapters = build_play_chapters(play, mode="scene")
    titles = [c["title"] for c in chapters]
    assert titles[0] == "Act I, Scene 1 — A garden of talking flowers."
    # Scene II has no header location; falls back to the location direction
    assert titles[1] == "Act I, Scene 2 — A dark wood with no names."
    assert titles[2] == "Act II, Scene 1 — The Queen's croquet-ground."
