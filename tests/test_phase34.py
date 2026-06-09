"""Phase 34 — Voice casting algorithm.

Tests use a 10-voice mock registry and synthetic Character lists.
No network calls, no synthesis.
"""

import json

import pytest

from vorpal.cli import build_parser
from vorpal.play.casting import (
    DEFAULT_NARRATOR_VOICE,
    UNIQUE_LINE_THRESHOLD,
    CastSheet,
    apply_overrides,
    assign_voices,
    castable_voices,
    format_cast_table,
)
from vorpal.play.characters import Character
from vorpal.tts.voices import VOICE_REGISTRY, VoiceEntry


# ── fixtures ─────────────────────────────────────────────────────────────────

def _voice(vid, gender):
    return VoiceEntry(
        id=vid,
        display_name=vid.split("_", 1)[-1].title(),
        engine="kokoro",
        params={"voice": vid},
        description=f"mock voice {vid}",
        gender=gender,
    )


@pytest.fixture
def mock_registry():
    """10 voices: 5 male, 4 female, 1 unknown."""
    voices = {}
    for vid in ["bm_george", "bm_lewis", "am_alpha", "am_beta", "am_gamma"]:
        voices[vid] = _voice(vid, "m")
    for vid in ["af_heart", "af_one", "bf_two", "bf_three"]:
        voices[vid] = _voice(vid, "f")
    voices["x_neutral"] = _voice("x_neutral", None)
    return voices


def _char(name, words, lines, role, gender):
    return Character(
        name=name, line_count=lines, word_count=words,
        role=role, gender_guess=gender,
    )


@pytest.fixture
def cast_20():
    """20-character cast: 1 protagonist, 4 major, 7 minor, 8 cameo."""
    cast = [_char("HAMLET", 12000, 350, "protagonist", "m")]
    cast += [
        _char("CLAUDIUS", 4000, 110, "major", "m"),
        _char("POLONIUS", 3500, 100, "major", "m"),
        _char("OPHELIA", 3000, 90, "major", "f"),
        _char("GERTRUDE", 2500, 80, "major", "f"),
    ]
    cast += [
        _char(f"MINOR_{i}", 800 - i * 50, 30 - i, "minor", g)
        for i, g in enumerate(["m", "m", "f", "unknown", "m", "f", "m"])
    ]
    cast += [
        _char(f"CAMEO_{i}", 60 - i * 5, 4, "cameo", g)
        for i, g in enumerate(
            ["m", "unknown", "f", "m", "unknown", "m", "f", "unknown"])
    ]
    return cast


# ── castable_voices ─────────────────────────────────────────────────────────

def test_castable_voices_excludes_openai():
    voices = castable_voices(VOICE_REGISTRY)
    assert voices, "real registry must yield castable voices"
    assert all(v.engine == "kokoro" for v in voices.values())
    assert not any(vid.startswith("oa_") for vid in voices)


def test_real_registry_has_narrator_default():
    assert DEFAULT_NARRATOR_VOICE in VOICE_REGISTRY
    assert VOICE_REGISTRY[DEFAULT_NARRATOR_VOICE].engine == "kokoro"


def test_real_registry_gender_coverage():
    voices = castable_voices(VOICE_REGISTRY)
    genders = {v.gender for v in voices.values()}
    assert "m" in genders and "f" in genders


# ── assign_voices: protagonist ───────────────────────────────────────────────

def test_protagonist_gets_default_best_male_voice(cast_20, mock_registry):
    sheet = assign_voices(cast_20, mock_registry)
    assert sheet.assignments["HAMLET"] == "bm_george"


def test_protagonist_gets_configured_best_voice(cast_20, mock_registry):
    sheet = assign_voices(cast_20, mock_registry, best_voice="am_alpha")
    assert sheet.assignments["HAMLET"] == "am_alpha"


def test_female_protagonist_gets_af_heart(mock_registry):
    cast = [
        _char("VIOLA", 9000, 250, "protagonist", "f"),
        _char("ORSINO", 4000, 100, "major", "m"),
    ]
    sheet = assign_voices(cast, mock_registry)
    assert sheet.assignments["VIOLA"] == "af_heart"


def test_protagonist_fallback_when_best_voice_absent(cast_20):
    # Registry without bm_george: protagonist falls back to an unused male voice
    voices = {
        "am_alpha": _voice("am_alpha", "m"),
        "am_beta": _voice("am_beta", "m"),
        "af_one": _voice("af_one", "f"),
    }
    sheet = assign_voices(cast_20, voices)
    assert sheet.assignments["HAMLET"] in ("am_alpha", "am_beta")


# ── assign_voices: major characters ──────────────────────────────────────────

def test_no_major_shares_a_voice_when_registry_has_room(cast_20, mock_registry):
    sheet = assign_voices(cast_20, mock_registry)
    big_parts = [c.name for c in cast_20
                 if c.role in ("protagonist", "major")]
    assigned = [sheet.assignments[name] for name in big_parts]
    assert len(assigned) == len(set(assigned)), "major characters share voices"


def test_majors_gender_matched(cast_20, mock_registry):
    sheet = assign_voices(cast_20, mock_registry)
    for c in cast_20:
        if c.role not in ("protagonist", "major"):
            continue
        entry = mock_registry[sheet.assignments[c.name]]
        if c.gender_guess in ("m", "f"):
            assert entry.gender == c.gender_guess, (
                f"{c.name} ({c.gender_guess}) got {entry.id} ({entry.gender})")


def test_high_line_count_minor_gets_unique_voice(mock_registry):
    """A 'minor' with > 50 lines must not share while voices remain."""
    cast = [
        _char("HAMLET", 12000, 350, "protagonist", "m"),
        _char("BUSY_MINOR", 900, UNIQUE_LINE_THRESHOLD + 1, "minor", "m"),
        _char("QUIET_MINOR", 100, 5, "minor", "m"),
    ]
    sheet = assign_voices(cast, mock_registry)
    assert sheet.assignments["BUSY_MINOR"] != sheet.assignments["HAMLET"]


# ── assign_voices: overflow / shared pool ────────────────────────────────────

def test_20_characters_all_assigned(cast_20, mock_registry):
    sheet = assign_voices(cast_20, mock_registry)
    assert len(sheet.assignments) == 20
    assert all(vid in mock_registry for vid in sheet.assignments.values())


def test_overflow_is_logged(cast_20, mock_registry):
    """20 characters on 10 voices: sharing must appear in notes."""
    sheet = assign_voices(cast_20, mock_registry)
    assert sheet.shared_voices(), "10 voices for 20 characters must share"
    assert any(note.startswith("shared:") for note in sheet.notes)


def test_tiny_registry_overflow_on_major():
    cast = [
        _char("A", 5000, 200, "protagonist", "m"),
        _char("B", 4000, 150, "major", "m"),
        _char("C", 3000, 120, "major", "m"),
    ]
    voices = {
        "am_alpha": _voice("am_alpha", "m"),
        "am_beta": _voice("am_beta", "m"),
    }
    sheet = assign_voices(cast, voices)
    assert len(sheet.assignments) == 3
    assert any("OVERFLOW" in note for note in sheet.notes)


def test_empty_registry_raises():
    with pytest.raises(ValueError):
        assign_voices([_char("A", 100, 10, "protagonist", "m")], {})


def test_narrator_voice_avoided_for_characters_when_possible(mock_registry):
    cast = [
        _char("A", 5000, 200, "protagonist", "m"),
        _char("B", 4000, 150, "major", "m"),
        _char("C", 3000, 120, "major", "m"),
    ]
    sheet = assign_voices(cast, mock_registry, narrator_voice="bm_lewis")
    assert "bm_lewis" not in sheet.assignments.values()


# ── CastSheet round-trip ─────────────────────────────────────────────────────

def test_cast_sheet_round_trip(cast_20, mock_registry):
    sheet = assign_voices(cast_20, mock_registry)
    restored = CastSheet.from_dict(sheet.to_dict())
    assert restored.assignments == sheet.assignments
    assert restored.narrator_voice == sheet.narrator_voice
    assert restored.notes == sheet.notes


def test_cast_sheet_json_serializable(cast_20, mock_registry):
    sheet = assign_voices(cast_20, mock_registry)
    blob = json.dumps(sheet.to_dict())
    assert CastSheet.from_dict(json.loads(blob)).assignments == sheet.assignments


# ── overrides ────────────────────────────────────────────────────────────────

def test_override_applies(cast_20, mock_registry):
    sheet = assign_voices(cast_20, mock_registry)
    apply_overrides(sheet, {"HAMLET": "am_gamma"}, mock_registry)
    assert sheet.assignments["HAMLET"] == "am_gamma"
    assert any("override: HAMLET" in n for n in sheet.notes)


def test_override_unknown_voice_raises(cast_20, mock_registry):
    sheet = assign_voices(cast_20, mock_registry)
    with pytest.raises(ValueError):
        apply_overrides(sheet, {"HAMLET": "no_such_voice"}, mock_registry)


def test_override_unknown_character_skipped(cast_20, mock_registry):
    sheet = assign_voices(cast_20, mock_registry)
    before = dict(sheet.assignments)
    apply_overrides(sheet, {"YORICK": "am_gamma"}, mock_registry)
    assert sheet.assignments == before
    assert any("override skipped" in n for n in sheet.notes)


def test_override_round_trip_through_json(cast_20, mock_registry, tmp_path):
    """Roadmap acceptance: --cast-override tested round-trip."""
    sheet = assign_voices(cast_20, mock_registry)
    override_file = tmp_path / "cast_override.json"
    override_file.write_text(json.dumps({"OPHELIA": "bf_three"}),
                             encoding="utf-8")
    overrides = json.loads(override_file.read_text(encoding="utf-8"))
    apply_overrides(sheet, overrides, mock_registry)
    restored = CastSheet.from_dict(sheet.to_dict())
    assert restored.assignments["OPHELIA"] == "bf_three"


# ── format_cast_table ────────────────────────────────────────────────────────

def test_table_contains_all_characters(cast_20, mock_registry):
    sheet = assign_voices(cast_20, mock_registry)
    table = format_cast_table(cast_20, sheet, mock_registry)
    for c in cast_20:
        assert c.name in table
    assert "narrator (stage directions)" in table


def test_table_shows_roles_and_lines(cast_20, mock_registry):
    sheet = assign_voices(cast_20, mock_registry)
    table = format_cast_table(cast_20, sheet, mock_registry)
    assert "protagonist" in table
    assert "350" in table  # HAMLET's line count


# ── determinism ──────────────────────────────────────────────────────────────

def test_assignment_is_deterministic(cast_20, mock_registry):
    a = assign_voices(cast_20, mock_registry)
    b = assign_voices(cast_20, mock_registry)
    assert a.assignments == b.assignments
    assert a.notes == b.notes


# ── CLI parser ───────────────────────────────────────────────────────────────

def test_cast_subcommand_parses():
    args = build_parser().parse_args(["cast", "hamlet.txt"])
    assert args.command == "cast"
    assert args.input == "hamlet.txt"
    assert args.cast_override is None
    assert args.narrator == "bm_lewis"
    assert args.best_voice is None


def test_cast_subcommand_flags():
    args = build_parser().parse_args([
        "cast", "play.json",
        "--cast-override", "ov.json",
        "--narrator", "bm_george",
        "--best-voice", "bm_daniel",
    ])
    assert args.cast_override == "ov.json"
    assert args.narrator == "bm_george"
    assert args.best_voice == "bm_daniel"


# ── generic-label gender fallback (added for real-Hamlet casting) ───────────

def test_generic_labels_gender():
    """Gutenberg Hamlet labels Claudius/Gertrude as KING/QUEEN."""
    from vorpal.play.characters import _guess_gender
    from vorpal.play.models import PlayDoc

    empty = PlayDoc(title="t", author="a")
    assert _guess_gender("KING", empty) == "m"
    assert _guess_gender("QUEEN", empty) == "f"
    assert _guess_gender("FIRST CLOWN", empty) == "m"
    assert _guess_gender("SECOND GENTLEMAN", empty) == "m"
    assert _guess_gender("MESSENGER", empty) == "unknown"


# ── real registry end-to-end (no synthesis) ──────────────────────────────────

def test_real_registry_casting_smoke(cast_20):
    voices = castable_voices(VOICE_REGISTRY)
    sheet = assign_voices(cast_20, voices)
    assert sheet.assignments["HAMLET"] == "bm_george"
    big_parts = [c.name for c in cast_20 if c.role in ("protagonist", "major")]
    assigned = [sheet.assignments[n] for n in big_parts]
    assert len(assigned) == len(set(assigned))
