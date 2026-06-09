"""Phase 32 — Character extraction + role classification.

Tests use the mini-play fixtures and inline Hamlet-like fixtures.
No network calls.
"""

import pytest

from vorpal.play.models import PlayDoc, Act, Scene, Beat
from vorpal.play.parser import parse_play
from vorpal.play.characters import (
    Character, extract_cast, _assign_role, _guess_gender, _GENDER_TABLE,
)


# ── inline fixtures ──────────────────────────────────────────────────────────

HAMLET_EXCERPT = """\
THE HAMLET EXCERPT

by William Shakespeare

ACT I.

SCENE I. Elsinore.

  Enter HAMLET.

HAMLET.
To be, or not to be — that is the question.
Whether 'tis nobler in the mind to suffer
The slings and arrows of outrageous fortune.

HORATIO.
Here, sweet lord.
Good my lord.

OPHELIA.
My lord.

HAMLET.
Get thee to a nunnery.

  [Exit OPHELIA, weeping.]

HORATIO.
My lord, I think I saw him yesternight.

HAMLET.
Saw who? Speak, I am bound to hear.

HORATIO.
My lord, the king your father.

SCENE II. A hall.

GERTRUDE.
How now, Ophelia?

HAMLET.
Mother, you have my father much offended.

GERTRUDE.
Come, come, you answer with an idle tongue.

HAMLET.
Go, go, you question with a wicked tongue.

ACT II.

SCENE I. A room.

HORATIO.
My lord, I came to see your father's funeral.

HAMLET.
I prithee do not mock me, fellow student.
I think it was to see my mother's wedding.

GERTRUDE.
Let not thy mother lose her prayers, Hamlet.
I pray thee stay with us, go not to Wittenberg.

HAMLET.
I shall in all my best obey you, madam.
"""

SMALL_CAST = """\
SMALL CAST PLAY

ACT I.

SCENE I. A room.

ALPHA.
I speak the most words here. I have many things to say
and I say them at length across many lines.

BETA.
I speak somewhat less. A decent amount but not the most.

GAMMA.
A few words.

DELTA.
One word.
"""


# ── extract_cast: structure ───────────────────────────────────────────────────

class TestExtractCastStructure:
    def test_returns_list_of_characters(self):
        play = parse_play(HAMLET_EXCERPT)
        cast = extract_cast(play)
        assert isinstance(cast, list)
        assert all(isinstance(c, Character) for c in cast)

    def test_hamlet_is_in_cast(self):
        play = parse_play(HAMLET_EXCERPT)
        names = {c.name for c in extract_cast(play)}
        assert "HAMLET" in names

    def test_all_speakers_in_cast(self):
        play = parse_play(HAMLET_EXCERPT)
        cast_names = {c.name for c in extract_cast(play)}
        for sp in play.speakers:
            assert sp in cast_names

    def test_sorted_descending_word_count(self):
        play = parse_play(HAMLET_EXCERPT)
        cast = extract_cast(play)
        counts = [c.word_count for c in cast]
        assert counts == sorted(counts, reverse=True)

    def test_empty_play_returns_empty(self):
        play = PlayDoc(title="Empty", author="")
        assert extract_cast(play) == []


# ── role classification ───────────────────────────────────────────────────────

class TestRoleClassification:
    def test_hamlet_is_protagonist(self):
        play = parse_play(HAMLET_EXCERPT)
        cast = {c.name: c for c in extract_cast(play)}
        assert cast["HAMLET"].role == "protagonist"

    def test_horatio_is_major(self):
        play = parse_play(HAMLET_EXCERPT)
        cast = {c.name: c for c in extract_cast(play)}
        # Horatio has multiple speeches; should be major or higher
        assert cast["HORATIO"].role in ("major", "protagonist")

    def test_ophelia_below_hamlet(self):
        play = parse_play(HAMLET_EXCERPT)
        cast = {c.name: c for c in extract_cast(play)}
        # Ophelia has fewer words than Hamlet
        assert cast["OPHELIA"].word_count < cast["HAMLET"].word_count

    def test_small_cast_roles(self):
        play = parse_play(SMALL_CAST)
        cast = {c.name: c for c in extract_cast(play)}
        assert cast["ALPHA"].role == "protagonist"
        # DELTA speaks very little — should be minor or cameo
        assert cast["DELTA"].role in ("minor", "cameo")

    def test_assign_role_single_character(self):
        role = _assign_role(100, [100])
        assert role == "protagonist"

    def test_assign_role_clear_tiers(self):
        # 10 characters: [1000, 900, 500, 400, 300, 200, 100, 50, 20, 10]
        counts = [1000, 900, 500, 400, 300, 200, 100, 50, 20, 10]
        assert _assign_role(1000, counts) == "protagonist"
        assert _assign_role(900, counts) == "major"
        assert _assign_role(300, counts) == "minor"   # top 5/10, above cameo boundary
        assert _assign_role(10, counts) == "cameo"

    def test_assign_role_empty_counts(self):
        assert _assign_role(0, []) == "cameo"


# ── word / line counts ────────────────────────────────────────────────────────

class TestCounts:
    def test_word_count_positive(self):
        play = parse_play(HAMLET_EXCERPT)
        cast = {c.name: c for c in extract_cast(play)}
        assert cast["HAMLET"].word_count > 0

    def test_line_count_is_turn_count(self):
        play = parse_play(SMALL_CAST)
        cast = {c.name: c for c in extract_cast(play)}
        # ALPHA speaks once
        assert cast["ALPHA"].line_count == 1
        # BETA speaks once
        assert cast["BETA"].line_count == 1

    def test_hamlet_has_more_words_than_ophelia(self):
        play = parse_play(HAMLET_EXCERPT)
        cast = {c.name: c for c in extract_cast(play)}
        assert cast["HAMLET"].word_count > cast["OPHELIA"].word_count


# ── gender guessing ───────────────────────────────────────────────────────────

class TestGenderGuessing:
    def test_hamlet_is_male(self):
        play = parse_play(HAMLET_EXCERPT)
        cast = {c.name: c for c in extract_cast(play)}
        assert cast["HAMLET"].gender_guess == "m"

    def test_ophelia_is_female(self):
        play = parse_play(HAMLET_EXCERPT)
        cast = {c.name: c for c in extract_cast(play)}
        assert cast["OPHELIA"].gender_guess == "f"

    def test_horatio_is_male(self):
        play = parse_play(HAMLET_EXCERPT)
        cast = {c.name: c for c in extract_cast(play)}
        assert cast["HORATIO"].gender_guess == "m"

    def test_gertrude_is_female(self):
        play = parse_play(HAMLET_EXCERPT)
        cast = {c.name: c for c in extract_cast(play)}
        assert cast["GERTRUDE"].gender_guess == "f"

    def test_unknown_name_returns_unknown(self):
        play = PlayDoc(title="Test", author="")
        act = Act(name="Act I")
        sc = Scene(name="Scene I", location="")
        sc.beats.append(Beat(type="speech", speaker="ZXQRTL", text="Unknown speaker."))
        act.scenes.append(sc)
        play.acts.append(act)
        cast = extract_cast(play)
        assert cast[0].gender_guess == "unknown"

    def test_gender_table_covers_key_names(self):
        for name in ["HAMLET", "OPHELIA", "HORATIO", "GERTRUDE", "LAERTES"]:
            assert name in _GENDER_TABLE

    def test_laertes_is_male(self):
        assert _GENDER_TABLE["LAERTES"] == "m"


# ── round-trip ────────────────────────────────────────────────────────────────

class TestCharacterRoundTrip:
    def test_to_from_dict(self):
        c = Character(name="HAMLET", line_count=20, word_count=500,
                      role="protagonist", gender_guess="m")
        c2 = Character.from_dict(c.to_dict())
        assert c2 == c

    def test_all_cast_members_round_trip(self):
        play = parse_play(HAMLET_EXCERPT)
        cast = extract_cast(play)
        for c in cast:
            c2 = Character.from_dict(c.to_dict())
            assert c2.name == c.name
            assert c2.role == c.role
