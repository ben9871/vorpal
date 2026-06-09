"""Phase 40 — play corpus hardening: minimized fixtures for every breakage
found while parsing the 6-play Gutenberg corpus (Hamlet, A Midsummer Night's
Dream, Macbeth, Twelfth Night, The Importance of Being Earnest, plus
As You Like It). No network calls — each corpus bug is reproduced inline.
"""

import pytest

from vorpal.play.casting import assign_voices, castable_voices
from vorpal.play.characters import _guess_gender, extract_cast
from vorpal.play.fetcher import CATALOGUE
from vorpal.play.models import PlayDoc
from vorpal.play.parser import parse_play
from vorpal.tts.voices import VOICE_REGISTRY


# ── 1. TOC "ACT I" lines at column 0 (Macbeth, MND editions) ─────────────────

TOC_PLAY = """\
A PLAY WITH A CONTENTS BLOCK

by W. S.

Contents

ACT I
Scene I. An open Place.
Scene II. A Camp.

ACT II
Scene I. A Castle.


ACT I

SCENE I. An open Place.

ALPHA.
The real first line.

SCENE II. A Camp.

BETA.
The real second scene.

ACT II

SCENE I. A Castle.

ALPHA.
The second act.
"""


def test_toc_acts_dropped():
    """The Contents block's ACT lines must not produce phantom acts."""
    play = parse_play(TOC_PLAY)
    assert [a.name for a in play.acts] == ["Act I", "Act II"]
    assert sum(len(a.scenes) for a in play.acts) == 3


def test_toc_scene_lines_not_speeches():
    play = parse_play(TOC_PLAY)
    texts = [b.text for a in play.acts for s in a.scenes for b in s.beats
             if b.type == "speech"]
    assert not any("Camp" in t for t in texts)


# ── 2. Dramatis Personæ after the TOC (Macbeth, Twelfth Night) ───────────────

PERSONAE_PLAY = """\
A PLAY WITH A CAST LIST

by W. S.

Contents

ACT I
Scene I. Somewhere.

Dramatis Personæ

DUNCAN, King of Scotland.
MALCOLM, his Son.
LADY MACDUFF, Wife to Macduff.

ACT I

SCENE I. Somewhere.

DUNCAN.
What bloody man is that?
"""


def test_personae_entries_not_speakers():
    """Cast-list entries must not become speakers with 'speeches'."""
    play = parse_play(PERSONAE_PLAY)
    assert play.speakers == ["DUNCAN"]
    assert len(play.acts) == 1


def test_personae_descriptions_not_speech_text():
    play = parse_play(PERSONAE_PLAY)
    all_text = " ".join(b.text for a in play.acts for s in a.scenes
                        for b in s.beats)
    assert "his Son" not in all_text


# ── 3. Wilde format (The Importance of Being Earnest, PG #844) ───────────────

WILDE_PLAY = """\
The Importance of Being Tested

by Oscar Wilde

FIRST ACT


SCENE

Morning-room in Algernon's flat. The room is luxuriously and
artistically furnished.

[Lane is arranging afternoon tea on the table, and after the music has
ceased, Algernon enters.]

ALGERNON.
Did you hear what I was playing, Lane?

LANE.
I didn't think it polite to listen, sir.

ACT DROP

SECOND ACT


SCENE

Garden at the Manor House.

CECILY.
I don't like novels that end happily.
"""


def test_wilde_ordinal_act_headers():
    play = parse_play(WILDE_PLAY)
    assert [a.name for a in play.acts] == ["Act I", "Act II"]


def test_wilde_bare_scene_headers():
    play = parse_play(WILDE_PLAY)
    assert len(play.acts[0].scenes) == 1
    assert play.acts[0].scenes[0].name == "Scene 1"


def test_wilde_scene_description_preserved_as_direction():
    """The prose after a bare SCENE header is never silently dropped."""
    play = parse_play(WILDE_PLAY)
    directions = [b.text for s in play.acts[0].scenes for b in s.beats
                  if b.type == "direction"]
    assert any("Morning-room" in d for d in directions)


def test_wilde_multiline_bracket_direction():
    play = parse_play(WILDE_PLAY)
    directions = [b.text for s in play.acts[0].scenes for b in s.beats
                  if b.type == "direction"]
    joined = [d for d in directions if "Lane is arranging" in d]
    assert len(joined) == 1
    assert "Algernon enters.]" in joined[0]  # both lines merged


def test_act_drop_not_a_speaker():
    play = parse_play(WILDE_PLAY)
    assert "ACT DROP" not in play.speakers
    assert set(play.speakers) == {"ALGERNON", "LANE", "CECILY"}


# ── 4. Songs (Twelfth Night) ─────────────────────────────────────────────────

SONG_PLAY = """\
A PLAY WITH A SONG

by W. S.

ACT I

SCENE I. A street.

SIR ANDREW.
Shall we hear a song?

CLOWN. [_sings._]
  _O mistress mine, where are you roaming?
  O stay and hear, your true love's coming,
    That can sing both high and low._

SIR ANDREW.
Excellent good, i' faith.
"""


def test_song_attributed_to_singer():
    """Sung lines belong to the CLOWN's speech, not the previous speaker
    and not stage directions (they'd be dropped under skip)."""
    play = parse_play(SONG_PLAY)
    beats = [b for a in play.acts for s in a.scenes for b in s.beats]
    songs = [b for b in beats if "mistress mine" in b.text]
    assert len(songs) == 1
    assert songs[0].type == "speech"
    assert songs[0].speaker == "CLOWN"


def test_song_underscores_stripped():
    play = parse_play(SONG_PLAY)
    beats = [b for a in play.acts for s in a.scenes for b in s.beats]
    song = next(b for b in beats if "mistress mine" in b.text)
    assert "_" not in song.text


def test_sings_cue_becomes_direction():
    play = parse_play(SONG_PLAY)
    directions = [b.text for a in play.acts for s in a.scenes
                  for b in s.beats if b.type == "direction"]
    assert any("sings" in d for d in directions)


def test_previous_speaker_speech_clean():
    play = parse_play(SONG_PLAY)
    andrew = [b.text for a in play.acts for s in a.scenes for b in s.beats
              if b.type == "speech" and b.speaker == "SIR ANDREW"]
    assert not any("CLOWN" in t or "mistress" in t for t in andrew)


# ── 5. Group + numbered speakers (Macbeth witches, Hamlet ALL/BOTH) ──────────

GROUP_PLAY = """\
A PLAY WITH GROUP SPEAKERS

by W. S.

ACT I

SCENE I. A heath.

FIRST WITCH.
When shall we three meet again?

SECOND WITCH.
When the hurlyburly's done.

THIRD WITCH.
That will be ere the set of sun.

ALL.
Fair is foul, and foul is fair.

BOTH.
We agree, in pairs.
"""


def test_group_and_numbered_speakers_parse():
    play = parse_play(GROUP_PLAY)
    assert set(play.speakers) == {
        "FIRST WITCH", "SECOND WITCH", "THIRD WITCH", "ALL", "BOTH"}


def test_group_speakers_castable():
    """ALL/BOTH cast like any character — no crash, every speaker voiced."""
    play = parse_play(GROUP_PLAY)
    cast = extract_cast(play)
    sheet = assign_voices(cast, castable_voices(VOICE_REGISTRY))
    assert set(sheet.assignments) == set(play.speakers)


def test_witch_gender_from_generic_label():
    play = parse_play(GROUP_PLAY)
    assert _guess_gender("FIRST WITCH", play) == "f"


# ── 6. Gendered title prefixes + disguise-proof table (Phase 40 finds) ──────

def test_sir_prefix_decisive():
    empty = PlayDoc(title="t", author="a")
    assert _guess_gender("SIR TOBY", empty) == "m"
    assert _guess_gender("SIR ANDREW AGUECHEEK", empty) == "m"
    assert _guess_gender("LADY CAPULET", empty) == "f"


def test_rosalind_female_despite_disguise():
    """Pronoun scans see Ganymede; the canonical table must win."""
    empty = PlayDoc(title="t", author="a")
    assert _guess_gender("ROSALIND", empty) == "f"
    assert _guess_gender("CELIA", empty) == "f"


# ── 7. Catalogue correction ──────────────────────────────────────────────────

def test_twelfth_night_id_corrected():
    """PG #1523 is As You Like It; Twelfth Night is #1526."""
    assert CATALOGUE["twelfth-night"] == 1526
    assert CATALOGUE["as-you-like-it"] == 1523


# ── 8. Long speech split across blank-line paragraphs ────────────────────────

LONG_SPEECH_PLAY = """\
A PLAY WITH A LONG SPEECH

by W. S.

ACT I

SCENE I. A stage.

ORATOR.
The first paragraph of a very long speech, which continues.

And after a blank line, the same speaker is still speaking,
because no new label has appeared.

BYSTANDER.
Finally, a reply.
"""


def test_long_speech_spans_paragraphs():
    play = parse_play(LONG_SPEECH_PLAY)
    orator = [b for a in play.acts for s in a.scenes for b in s.beats
              if b.type == "speech" and b.speaker == "ORATOR"]
    assert len(orator) == 1
    assert "first paragraph" in orator[0].text
    assert "still speaking" in orator[0].text
