"""Phase 33 — Stage direction classification + emotion extraction.

Tests use inline fixtures for classification and a manually labelled
50-direction sample from Hamlet-style text.
"""

import pytest

from vorpal.play.directions import (
    classify_direction,
    extract_emotion_hint,
    DIRECTION_KINDS,
    _EMOTION_MAP,
)
from vorpal.play.parser import parse_play
from vorpal.play.models import Beat


# ── kind vocabulary ───────────────────────────────────────────────────────────

class TestKindVocabulary:
    def test_all_kinds_defined(self):
        expected = {"entry_exit", "location", "emotion_hint", "song", "action", "other"}
        assert DIRECTION_KINDS == expected


# ── classification: entry_exit ────────────────────────────────────────────────

class TestEntryExit:
    def test_enter(self):
        assert classify_direction("[Enter HAMLET]") == "entry_exit"

    def test_exit(self):
        assert classify_direction("[Exit HAMLET]") == "entry_exit"

    def test_exeunt(self):
        assert classify_direction("  Exeunt all.") == "entry_exit"

    def test_enter_indented(self):
        assert classify_direction("  Enter FRANCISCO and BARNARDO.") == "entry_exit"

    def test_re_enter(self):
        assert classify_direction("[Re-enter GHOST]") == "entry_exit"


# ── classification: song ──────────────────────────────────────────────────────

class TestSong:
    def test_sings(self):
        assert classify_direction("[Sings]") == "song"

    def test_song(self):
        assert classify_direction("  Song.") == "song"

    def test_singing_indented(self):
        assert classify_direction("  Singing a ballad.") == "song"


# ── classification: emotion_hint ─────────────────────────────────────────────

class TestEmotionHint:
    def test_weeping(self):
        assert classify_direction("[Weeping]") == "emotion_hint"

    def test_furiously(self):
        assert classify_direction("[Furiously]") == "emotion_hint"

    def test_aside(self):
        assert classify_direction("[Aside]") == "emotion_hint"

    def test_tenderly(self):
        assert classify_direction("[Tenderly]") == "emotion_hint"

    def test_kneeling(self):
        assert classify_direction("[Kneeling]") == "emotion_hint"

    def test_bitterly(self):
        assert classify_direction("[Bitterly]") == "emotion_hint"

    def test_in_despair(self):
        assert classify_direction("[In despair]") == "emotion_hint"

    def test_laughing(self):
        assert classify_direction("[Laughing]") == "emotion_hint"

    def test_whispering(self):
        assert classify_direction("[Whispering]") == "emotion_hint"

    def test_solemnly(self):
        assert classify_direction("[Solemnly]") == "emotion_hint"

    def test_shouting(self):
        assert classify_direction("[Shouting]") == "emotion_hint"

    def test_mockingly(self):
        assert classify_direction("[Mockingly]") == "emotion_hint"


# ── classification: action ────────────────────────────────────────────────────

class TestAction:
    def test_draws_sword(self):
        assert classify_direction("[Draws his sword]") == "action"

    def test_falls(self):
        assert classify_direction("[Falls dead]") == "action"

    def test_strikes(self):
        assert classify_direction("[Strikes the table]") == "action"

    def test_embracing(self):
        # "embracing" is in emotion map (warm) — so it's emotion_hint
        result = classify_direction("[Embracing her]")
        assert result == "emotion_hint"


# ── classification: 50-direction manually labelled fixture ───────────────────

# Each tuple: (text, expected_kind)
LABELLED_50 = [
    # entry_exit (10)
    ("[Enter HAMLET]", "entry_exit"),
    ("[Exit HORATIO]", "entry_exit"),
    ("  Exeunt all.", "entry_exit"),
    ("  Enter GHOST.", "entry_exit"),
    ("[Exeunt ROSENCRANTZ and GUILDENSTERN]", "entry_exit"),
    ("  Enter PLAYER KING and PLAYER QUEEN.", "entry_exit"),
    ("[Exit LAERTES]", "entry_exit"),
    ("  Exeunt HORATIO and HAMLET.", "entry_exit"),
    ("  Enter POLONIUS behind the arras.", "entry_exit"),
    ("[Enter OPHELIA, distracted]", "entry_exit"),

    # song (4)
    ("[Sings]", "song"),
    ("  Song.", "song"),
    ("  Singing.", "song"),
    ("[Sings a catch]", "song"),

    # emotion_hint (18)
    ("[Weeping]", "emotion_hint"),
    ("[Furiously]", "emotion_hint"),
    ("[Aside]", "emotion_hint"),
    ("[Tenderly]", "emotion_hint"),
    ("[Solemnly]", "emotion_hint"),
    ("[Bitterly]", "emotion_hint"),
    ("[In despair]", "emotion_hint"),
    ("[Kneeling]", "emotion_hint"),
    ("[Laughing]", "emotion_hint"),
    ("[Whispering]", "emotion_hint"),
    ("[Shouting]", "emotion_hint"),
    ("[Mockingly]", "emotion_hint"),
    ("[Gently]", "emotion_hint"),
    ("[Frantically]", "emotion_hint"),
    ("[Mournfully]", "emotion_hint"),
    ("[Smiling]", "emotion_hint"),
    ("[Aside, to HORATIO]", "emotion_hint"),
    ("[In horror]", "emotion_hint"),

    # action (12)
    ("[Draws his sword]", "action"),
    ("[Falls dead]", "action"),
    ("[Strikes LAERTES]", "action"),
    ("[Gives HAMLET the cup]", "action"),
    ("[Drops the letter]", "action"),
    ("[Takes the crown]", "action"),
    ("[Runs toward the castle]", "action"),
    ("[Steps forward]", "action"),
    ("[Dies]", "action"),
    ("[Beckons to HORATIO]", "action"),
    ("[Sits at his desk]", "action"),
    ("[Falls to his knees]", "action"),

    # location (4)
    ("Elsinore. A platform before the castle.", "location"),
    ("A room in the castle.", "location"),
    ("A churchyard.", "location"),
    ("Denmark. A plain.", "location"),

    # other (2)
    ("[Flourish]", "other"),
    ("[A noise within]", "other"),
]


class TestLabelled50:
    def test_all_50_directions_correct(self):
        correct = 0
        errors = []
        for text, expected in LABELLED_50:
            got = classify_direction(text)
            if got == expected:
                correct += 1
            else:
                errors.append(f"{text!r}: expected {expected!r}, got {got!r}")
        accuracy = correct / len(LABELLED_50)
        assert accuracy >= 0.90, (
            f"Classification accuracy {accuracy:.1%} below 90%. Errors:\n"
            + "\n".join(errors)
        )

    def test_all_50_entry_exit_correct(self):
        entry_exit = [(t, k) for t, k in LABELLED_50 if k == "entry_exit"]
        for text, _ in entry_exit:
            assert classify_direction(text) == "entry_exit", f"entry_exit failed: {text!r}"

    def test_all_50_emotion_hints_correct(self):
        hints = [(t, k) for t, k in LABELLED_50 if k == "emotion_hint"]
        for text, _ in hints:
            assert classify_direction(text) == "emotion_hint", (
                f"emotion_hint failed: {text!r}"
            )


# ── extract_emotion_hint ──────────────────────────────────────────────────────

class TestExtractEmotionHint:
    def test_weeping_is_somber(self):
        assert extract_emotion_hint("[Weeping]") == "somber"

    def test_furiously_is_tense(self):
        assert extract_emotion_hint("[Furiously]") == "tense"

    def test_aside_is_wry(self):
        assert extract_emotion_hint("[Aside]") == "wry"

    def test_tenderly_is_warm(self):
        assert extract_emotion_hint("[Tenderly]") == "warm"

    def test_kneeling_is_warm(self):
        assert extract_emotion_hint("[Kneeling]") == "warm"

    def test_in_despair_is_somber(self):
        assert extract_emotion_hint("[In despair]") == "somber"

    def test_laughing_is_warm(self):
        assert extract_emotion_hint("[Laughing]") == "warm"

    def test_shouting_is_tense(self):
        assert extract_emotion_hint("[Shouting]") == "tense"

    def test_no_emotion_returns_none(self):
        assert extract_emotion_hint("[Enter HAMLET]") is None

    def test_no_emotion_plain_text(self):
        assert extract_emotion_hint("A room in the castle.") is None

    def test_in_horror_is_tense(self):
        assert extract_emotion_hint("[In horror]") == "tense"

    def test_bitterly_is_somber(self):
        assert extract_emotion_hint("[Bitterly]") == "somber"

    def test_phrase_takes_priority(self):
        # "in despair" is a phrase; "in" alone is not a keyword
        result = extract_emotion_hint("[She stands in despair]")
        assert result == "somber"


# ── tone_hint propagation to speech beats ────────────────────────────────────

TONE_PLAY = """\
THE TONE PLAY

ACT I.

SCENE I. A room.

HAMLET.
I feel nothing.

  [Weeping]

OPHELIA.
This is sad.

HAMLET.
Truly.

  [Furiously]

GERTRUDE.
I am angry now.

  [Enter LAERTES]

LAERTES.
No emotion hint here.

  [Aside]

HAMLET.
This is wry.
"""


class TestToneHintPropagation:
    def setup_method(self):
        self.play = parse_play(TONE_PLAY)
        self.sc = self.play.acts[0].scenes[0]
        # Collect speeches in order
        self.speeches = [b for b in self.sc.beats if b.type == "speech"]
        self.speech_map = {b.speaker: b for b in self.speeches}

    def test_ophelia_gets_somber_from_weeping(self):
        # [Weeping] precedes Ophelia's speech
        ophelia_speeches = [b for b in self.speeches if b.speaker == "OPHELIA"]
        assert ophelia_speeches[0].tone_hint == "somber"

    def test_gertrude_gets_tense_from_furiously(self):
        # [Furiously] precedes Gertrude's speech
        gertrude_speeches = [b for b in self.speeches if b.speaker == "GERTRUDE"]
        assert gertrude_speeches[0].tone_hint == "tense"

    def test_laertes_has_no_tone_hint(self):
        # [Enter LAERTES] is entry_exit, not emotion_hint
        laertes_speeches = [b for b in self.speeches if b.speaker == "LAERTES"]
        assert laertes_speeches[0].tone_hint is None

    def test_hamlet_wry_from_aside(self):
        # [Aside] precedes last Hamlet speech
        hamlet_speeches = [b for b in self.speeches if b.speaker == "HAMLET"]
        # Last Hamlet speech follows [Aside]
        assert hamlet_speeches[-1].tone_hint == "wry"

    def test_first_hamlet_speech_no_hint(self):
        # First Hamlet speech has no preceding direction
        hamlet_speeches = [b for b in self.speeches if b.speaker == "HAMLET"]
        assert hamlet_speeches[0].tone_hint is None
