"""Phase 37 — Tone/emotion from stage direction context.

The parser (Phase 33) stamps tone_hint on speech beats following emotion-hint
directions; this phase verifies the synthesis router propagates those hints
to chunk tones. MockEngine only.
"""

import pytest

from vorpal.play.casting import CastSheet
from vorpal.play.models import Beat
from vorpal.play.parser import parse_play
from vorpal.play.synth_router import route_chunks
from vorpal.synth import _cache_key
from vorpal.tts.mock_engine import MockEngine


@pytest.fixture
def sheet():
    return CastSheet(
        assignments={"OPHELIA": "af_one", "HAMLET": "am_two"},
        narrator_voice="bm_narr",
    )


# ── tone propagation from pre-stamped beats ──────────────────────────────────

def test_tone_hint_propagates_to_chunk(sheet):
    beats = [
        Beat(type="speech", speaker="OPHELIA",
             text="There's rosemary, that's for remembrance.",
             tone_hint="somber"),
    ]
    chunks = route_chunks(beats, sheet)
    assert chunks[0].tone == "somber"


def test_no_hint_means_neutral(sheet):
    beats = [
        Beat(type="speech", speaker="HAMLET", text="Words, words, words."),
    ]
    chunks = route_chunks(beats, sheet)
    assert chunks[0].tone is None


def test_hint_applies_to_all_chunks_of_the_speech(sheet):
    long_text = " ".join(
        f"Sorrowful sentence number {i} stretches this speech well past one chunk."
        for i in range(12)
    )
    beats = [Beat(type="speech", speaker="OPHELIA", text=long_text,
                  tone_hint="somber")]
    chunks = route_chunks(beats, sheet, max_chars=200)
    assert len(chunks) > 1
    assert all(c.tone == "somber" for c in chunks)


def test_hint_does_not_leak_to_next_speech(sheet):
    beats = [
        Beat(type="speech", speaker="OPHELIA", text="Pray you, love, remember.",
             tone_hint="somber"),
        Beat(type="speech", speaker="HAMLET", text="I did love you once."),
    ]
    chunks = route_chunks(beats, sheet)
    assert chunks[0].tone == "somber"
    assert chunks[1].tone is None


def test_use_tone_hints_false_routes_neutral(sheet):
    beats = [
        Beat(type="speech", speaker="OPHELIA", text="O, woe is me.",
             tone_hint="somber"),
    ]
    chunks = route_chunks(beats, sheet, use_tone_hints=False)
    assert chunks[0].tone is None


def test_narrated_direction_has_no_tone(sheet):
    beats = [
        Beat(type="direction", speaker=None, text="[Exit, weeping.]"),
        Beat(type="speech", speaker="HAMLET", text="Farewell."),
    ]
    chunks = route_chunks(beats, sheet, stage_directions="narrator")
    narr = [c for c in chunks if c.voice_id == "bm_narr"]
    assert narr and narr[0].tone is None


# ── end-to-end: parser stamps, router propagates ─────────────────────────────

PLAY_WITH_HINTS = """\
A SAD PLAY

by A. Fixture

ACT I.

SCENE I. A chamber.

  [Enter OPHELIA.]

  [Weeping.]

OPHELIA.
They bore him barefaced on the bier.

HAMLET.
What is the matter?

  [Aside.]

HAMLET.
Though this be madness, yet there is method in it.

OPHELIA.
And will he not come again?
"""


def test_parsed_play_weeping_to_somber(sheet):
    play = parse_play(PLAY_WITH_HINTS)
    beats = [b for act in play.acts for sc in act.scenes for b in sc.beats]
    chunks = route_chunks(beats, sheet)
    by_text = {c.text: c.tone for c in chunks}
    somber = [t for txt, t in by_text.items() if "bier" in txt]
    assert somber == ["somber"]


def test_parsed_play_aside_to_wry(sheet):
    play = parse_play(PLAY_WITH_HINTS)
    beats = [b for act in play.acts for sc in act.scenes for b in sc.beats]
    chunks = route_chunks(beats, sheet)
    wry = [c.tone for c in chunks if "madness" in c.text]
    assert wry == ["wry"]


def test_parsed_play_unhinted_speeches_neutral(sheet):
    play = parse_play(PLAY_WITH_HINTS)
    beats = [b for act in play.acts for sc in act.scenes for b in sc.beats]
    chunks = route_chunks(beats, sheet)
    assert [c.tone for c in chunks if "matter" in c.text] == [None]
    assert [c.tone for c in chunks if "come again" in c.text] == [None]


# ── cache key separation ─────────────────────────────────────────────────────

def test_cache_key_differs_for_toned_chunk(sheet):
    beats_toned = [Beat(type="speech", speaker="OPHELIA",
                        text="Goodnight, ladies.", tone_hint="somber")]
    beats_plain = [Beat(type="speech", speaker="OPHELIA",
                        text="Goodnight, ladies.")]
    engine = MockEngine(voice="af_one")
    toned = route_chunks(beats_toned, sheet)[0]
    plain = route_chunks(beats_plain, sheet)[0]
    assert _cache_key(toned, engine) != _cache_key(plain, engine)
