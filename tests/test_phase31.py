"""Phase 31 — Gutenberg play downloader + plain-text play parser.

Tests use inline mini-play fixtures — NO network calls required.
"""

import json
import re

import pytest

from vorpal.play.models import Act, Beat, PlayDoc, Scene
from vorpal.play.parser import parse_play
from vorpal.play.fetcher import strip_pg_boilerplate, CATALOGUE, _resolve_id, _slug


# ── inline play fixtures ─────────────────────────────────────────────────────

MINI_PLAY = """\
THE TEST PLAY

by Test Author


ACT I.

SCENE I. A dark room.

  Enter ALICE and BOB.

ALICE.
Hello, Bob. How are you?

BOB.
Hello, Alice. I am well.

  [They shake hands.]

SCENE II. A bright room.

  Enter ALICE.

ALICE.
Where is everyone?

  [Aside.]

BOB.
[Weeping]
I am here, weeping.

ACT II.

SCENE I. Outside the palace.

  Exeunt all.

ALICE.
It is finally done.

BOB.
Indeed, my lady.

SCENE II. Inside the palace.

  Enter CHARLIE.

CHARLIE.
What has happened here?

ALICE.
Much, my friend.

ACT III.

SCENE I. The graveyard at midnight.

  Enter ALICE and CHARLIE.

ALICE.
Goodbye, old world.

BOB.
[Furiously]
I refuse to accept this!

CHARLIE.
Then you must leave.
"""

SIMPLE_PLAY = """\
THE SIMPLE PLAY

by Simple Author


ACT I.

SCENE I. A room.

HERO.
I am the hero.

VILLAIN.
I am the villain.

ACT II.

SCENE I. Another room.

HERO.
We meet again.

VILLAIN.
Indeed we do.
"""

PG_WRAPPED_PLAY = """\
Project Gutenberg's header text here
This is lots of boilerplate.

*** START OF THE PROJECT GUTENBERG EBOOK THE SIMPLE PLAY ***

THE PLAY STARTS HERE

by Test Author

ACT I.

SCENE I. A room.

HERO.
First speech.

*** END OF THE PROJECT GUTENBERG EBOOK THE SIMPLE PLAY ***

Footer text and license info here.
More footer text.
"""


# ── models round-trip ────────────────────────────────────────────────────────

class TestModels:
    def test_beat_round_trip(self):
        b = Beat(type="speech", speaker="HAMLET", text="To be or not to be.", tone_hint="somber")
        assert Beat.from_dict(b.to_dict()) == b

    def test_beat_direction_round_trip(self):
        b = Beat(type="direction", speaker=None, text="[Exit HAMLET]", tone_hint=None)
        d = b.to_dict()
        b2 = Beat.from_dict(d)
        assert b2.type == "direction"
        assert b2.speaker is None

    def test_scene_round_trip(self):
        s = Scene(name="Scene I", location="A dark room")
        s.beats.append(Beat(type="speech", speaker="HERO", text="Hello."))
        s2 = Scene.from_dict(s.to_dict())
        assert s2.name == "Scene I"
        assert s2.location == "A dark room"
        assert len(s2.beats) == 1
        assert s2.beats[0].speaker == "HERO"

    def test_act_round_trip(self):
        a = Act(name="Act I")
        sc = Scene(name="Scene I", location="")
        sc.beats.append(Beat(type="speech", speaker="HERO", text="Hello."))
        a.scenes.append(sc)
        a2 = Act.from_dict(a.to_dict())
        assert a2.name == "Act I"
        assert len(a2.scenes) == 1

    def test_playdoc_round_trip(self):
        p = PlayDoc(title="Hamlet", author="Shakespeare")
        a = Act(name="Act I")
        sc = Scene(name="Scene I", location="Elsinore")
        sc.beats.append(Beat(type="speech", speaker="HAMLET", text="Who's there?"))
        a.scenes.append(sc)
        p.acts.append(a)
        p2 = PlayDoc.from_dict(p.to_dict())
        assert p2.title == "Hamlet"
        assert len(p2.acts) == 1
        assert p2.acts[0].scenes[0].location == "Elsinore"

    def test_playdoc_speakers(self):
        p = PlayDoc(title="Test", author="")
        a = Act(name="Act I")
        sc = Scene(name="Scene I", location="")
        sc.beats.append(Beat(type="speech", speaker="ALICE", text="Hi."))
        sc.beats.append(Beat(type="speech", speaker="BOB", text="Hi."))
        sc.beats.append(Beat(type="speech", speaker="ALICE", text="Again."))
        a.scenes.append(sc)
        p.acts.append(a)
        speakers = p.speakers
        assert "ALICE" in speakers
        assert "BOB" in speakers
        assert speakers.count("ALICE") == 1  # deduplicated


# ── boilerplate stripping ────────────────────────────────────────────────────

class TestStripBoilerplate:
    def test_strips_header_and_footer(self):
        result = strip_pg_boilerplate(PG_WRAPPED_PLAY)
        assert "THE PLAY STARTS HERE" in result
        assert "Project Gutenberg" not in result
        assert "Footer text" not in result

    def test_strip_leaves_content(self):
        result = strip_pg_boilerplate(PG_WRAPPED_PLAY)
        assert "HERO." in result
        assert "First speech." in result

    def test_strip_noop_without_markers(self):
        plain = "No boilerplate here.\nJust a play."
        assert strip_pg_boilerplate(plain) == plain.strip()

    def test_strip_case_insensitive(self):
        text = "*** start of the project gutenberg ebook ***\nContent\n*** end of the project gutenberg ebook ***"
        result = strip_pg_boilerplate(text)
        assert "Content" in result
        assert "project gutenberg" not in result.lower()


# ── parser: structure ────────────────────────────────────────────────────────

class TestParserStructure:
    def test_act_count_mini(self):
        play = parse_play(MINI_PLAY)
        assert len(play.acts) == 3

    def test_scene_count_mini(self):
        play = parse_play(MINI_PLAY)
        total_scenes = sum(len(a.scenes) for a in play.acts)
        assert total_scenes == 5

    def test_act_names(self):
        play = parse_play(MINI_PLAY)
        names = [a.name for a in play.acts]
        assert "Act I" in names
        assert "Act II" in names
        assert "Act III" in names

    def test_scene_names(self):
        play = parse_play(MINI_PLAY)
        scene_names = [sc.name for act in play.acts for sc in act.scenes]
        assert "Scene I" in scene_names
        assert "Scene II" in scene_names

    def test_scene_locations(self):
        play = parse_play(MINI_PLAY)
        act1_scene1 = play.acts[0].scenes[0]
        assert "dark room" in act1_scene1.location.lower()

    def test_title_extracted(self):
        play = parse_play(MINI_PLAY)
        assert "TEST PLAY" in play.title.upper()

    def test_author_extracted(self):
        play = parse_play(MINI_PLAY)
        assert "Test Author" in play.author


# ── parser: speakers ─────────────────────────────────────────────────────────

class TestParserSpeakers:
    def test_speaker_set_mini(self):
        play = parse_play(MINI_PLAY)
        speakers = set(play.speakers)
        assert "ALICE" in speakers
        assert "BOB" in speakers
        assert "CHARLIE" in speakers

    def test_no_act_scene_as_speaker(self):
        play = parse_play(MINI_PLAY)
        speakers = set(play.speakers)
        for name in speakers:
            assert not name.startswith("ACT")
            assert not name.startswith("SCENE")

    def test_simple_play_speakers(self):
        play = parse_play(SIMPLE_PLAY)
        speakers = set(play.speakers)
        assert "HERO" in speakers
        assert "VILLAIN" in speakers

    def test_speech_text_preserved(self):
        play = parse_play(SIMPLE_PLAY)
        speeches = [
            b.text for a in play.acts for sc in a.scenes
            for b in sc.beats if b.type == "speech" and b.speaker == "HERO"
        ]
        assert any("hero" in t.lower() for t in speeches)


# ── parser: beat types ───────────────────────────────────────────────────────

class TestParserBeats:
    def test_directions_present(self):
        play = parse_play(MINI_PLAY)
        all_beats = [b for a in play.acts for sc in a.scenes for b in sc.beats]
        directions = [b for b in all_beats if b.type == "direction"]
        assert len(directions) >= 3  # [They shake hands.], [Aside.], [Weeping], etc.

    def test_directions_have_no_speaker(self):
        play = parse_play(MINI_PLAY)
        for a in play.acts:
            for sc in a.scenes:
                for b in sc.beats:
                    if b.type == "direction":
                        assert b.speaker is None

    def test_speeches_have_speakers(self):
        play = parse_play(MINI_PLAY)
        for a in play.acts:
            for sc in a.scenes:
                for b in sc.beats:
                    if b.type == "speech":
                        assert b.speaker is not None
                        assert len(b.speaker) >= 2

    def test_indented_direction_parsed(self):
        play = parse_play(MINI_PLAY)
        all_dirs = [b.text for a in play.acts for sc in a.scenes
                    for b in sc.beats if b.type == "direction"]
        assert any("Enter" in d or "Exeunt" in d or "shake" in d for d in all_dirs)

    def test_bracket_direction_in_speech(self):
        play = parse_play(MINI_PLAY)
        all_dirs = [b.text for a in play.acts for sc in a.scenes
                    for b in sc.beats if b.type == "direction"]
        assert any("Weeping" in d or "Furiously" in d for d in all_dirs)


# ── catalogue & slug resolution ──────────────────────────────────────────────

class TestCatalogue:
    def test_hamlet_in_catalogue(self):
        assert "hamlet" in CATALOGUE
        assert CATALOGUE["hamlet"] == 1524

    def test_all_six_plays_present(self):
        ids = set(CATALOGUE.values())
        for expected_id in [1524, 1514, 1533, 1523, 23042, 1882]:
            assert expected_id in ids

    def test_resolve_by_name(self):
        bid, slug = _resolve_id("hamlet")
        assert bid == 1524
        assert slug == "hamlet"

    def test_resolve_by_numeric_id(self):
        bid, slug = _resolve_id("1524")
        assert bid == 1524
        assert slug == "hamlet"

    def test_resolve_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown play"):
            _resolve_id("nonexistent-play-xyz")

    def test_slug_normalisation(self):
        assert _slug("Hamlet") == "hamlet"
        assert _slug("A Midsummer Night's Dream") == "a-midsummer-night-s-dream"
        assert _slug("The Tempest") == "the-tempest"


# ── CLI subcommand registration ───────────────────────────────────────────────

class TestCLIFetchPlay:
    def test_fetch_play_command_registered(self):
        from vorpal.cli import build_parser
        p = build_parser()
        # Should parse without error
        args = p.parse_args(["fetch-play", "hamlet"])
        assert args.title_or_id == "hamlet"
        assert args.corpus_dir == "corpus/plays"

    def test_fetch_play_custom_corpus_dir(self):
        from vorpal.cli import build_parser
        p = build_parser()
        args = p.parse_args(["fetch-play", "macbeth", "--corpus-dir", "/tmp/plays"])
        assert args.corpus_dir == "/tmp/plays"

    def test_fetch_play_numeric_id(self):
        from vorpal.cli import build_parser
        p = build_parser()
        args = p.parse_args(["fetch-play", "1524"])
        assert args.title_or_id == "1524"
