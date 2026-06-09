"""Phase 38 — `vorpal play` end-to-end command.

MockEngine factory throughout — no GPU, no ffmpeg (draft mode), no network.
"""

import json

import pytest

from vorpal.cli import build_parser
from vorpal.play.pipeline import build_play, format_review_surface, load_play
from vorpal.tts.mock_engine import MockEngine
from vorpal.tts.voices import VoiceEntry


MINI_PLAY = """\
THE POCKET TRAGEDY

by A. Fixture

ACT I.

SCENE I. A small stage.

  [Enter ALICE and BOB.]

ALICE.
The first line of the play is mine, and I shall make the most of it.
A protagonist is measured by her word count, after all.
There is so much to say and only two acts to say it in.

BOB.
And the reply is mine.

  [Weeping.]

ALICE.
This speech is sad because the direction above it says so.

SCENE II. Elsewhere.

BOB.
A second scene, a second chance.

ACT II.

SCENE I. The same stage, later.

ALICE.
All plays end. This one simply ends sooner than most.

BOB.
Farewell.
"""


def _mock_voices():
    return {
        "v_alpha": VoiceEntry(id="v_alpha", display_name="Alpha",
                              engine="kokoro", params={"voice": "v_alpha"},
                              description="mock", gender="f"),
        "v_beta": VoiceEntry(id="v_beta", display_name="Beta",
                             engine="kokoro", params={"voice": "v_beta"},
                             description="mock", gender="m"),
        "v_narr": VoiceEntry(id="v_narr", display_name="Narr",
                             engine="kokoro", params={"voice": "v_narr"},
                             description="mock", gender="m"),
    }


def _mock_factory(record=None):
    def factory(entry):
        engine = MockEngine(voice=entry.id)
        if record is not None:
            record.append(entry.id)
        return engine
    return factory


@pytest.fixture
def play_txt(tmp_path):
    p = tmp_path / "pocket.txt"
    p.write_text(MINI_PLAY, encoding="utf-8")
    return p


@pytest.fixture
def run_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


# ── review gate ──────────────────────────────────────────────────────────────

def test_review_gate_default(play_txt, run_dir):
    result = build_play(play_txt, voices=_mock_voices(),
                        narrator_voice="v_narr")
    assert result["status"] == "review"
    assert result["cast_sheet"].assignments.keys() == {"ALICE", "BOB"}
    assert (run_dir / "pocket_workdir" / "play.json").exists()
    assert (run_dir / "pocket_workdir" / "cast.json").exists()
    assert (run_dir / "pocket_workdir" / "cast_sheet.json").exists()


def test_review_surface_contents(play_txt, run_dir):
    result = build_play(play_txt, voices=_mock_voices(),
                        narrator_voice="v_narr")
    surface = format_review_surface(result)
    assert "ALICE" in surface and "BOB" in surface
    assert "Act I" in surface
    assert "--approve" in surface


def test_no_audio_before_approve(play_txt, run_dir):
    build_play(play_txt, voices=_mock_voices(), narrator_voice="v_narr")
    assert not (run_dir / "pocket_workdir" / "chapters").exists()


# ── full build (draft mode — no ffmpeg) ──────────────────────────────────────

def test_full_draft_build(play_txt, run_dir):
    result = build_play(
        play_txt, voices=_mock_voices(), narrator_voice="v_narr",
        approve=True, draft=True, engine_factory=_mock_factory(),
    )
    assert result["status"] == "built"
    assert result["output"].exists()
    assert result["output"].name == "pocket_draft_play.wav"
    # act mode default: 2 chapters
    assert len(result["chapter_results"]) == 2
    for cr in result["chapter_results"]:
        assert cr["wav"].exists()
        assert cr["duration_ms"] > 0


def test_distinct_voices_engaged(play_txt, run_dir):
    created = []
    build_play(
        play_txt, voices=_mock_voices(), narrator_voice="v_narr",
        approve=True, draft=True, engine_factory=_mock_factory(created),
    )
    # ALICE and BOB get distinct voices; narrator engine not built under skip
    assert len(created) == 2
    assert len(set(created)) == 2
    assert "v_narr" not in created


def test_narrator_engine_built_when_directions_narrated(play_txt, run_dir):
    created = []
    build_play(
        play_txt, voices=_mock_voices(), narrator_voice="v_narr",
        stage_directions="narrator",
        approve=True, draft=True, engine_factory=_mock_factory(created),
    )
    assert "v_narr" in created


def test_scene_mode_chapter_count(play_txt, run_dir):
    result = build_play(
        play_txt, voices=_mock_voices(), narrator_voice="v_narr",
        chapters_mode="scene",
        approve=True, draft=True, engine_factory=_mock_factory(),
    )
    assert len(result["chapter_results"]) == 3


def test_second_build_hits_cache(play_txt, run_dir):
    kwargs = dict(voices=_mock_voices(), narrator_voice="v_narr",
                  approve=True, draft=True)
    first = build_play(play_txt, engine_factory=_mock_factory(), **kwargs)
    # chapter WAVs already assembled; remove them to force re-assembly from cache
    for cr in first["chapter_results"]:
        cr["wav"].unlink()
    second = build_play(play_txt, engine_factory=_mock_factory(), **kwargs)
    assert first["synth_totals"]["done"] > 0
    assert second["synth_totals"] == {"done": 0,
                                      "cached": first["synth_totals"]["done"]}


# ── cast sheet persistence + overrides ───────────────────────────────────────

def test_hand_edited_cast_sheet_survives(play_txt, run_dir):
    build_play(play_txt, voices=_mock_voices(), narrator_voice="v_narr")
    sheet_path = run_dir / "pocket_workdir" / "cast_sheet.json"
    data = json.loads(sheet_path.read_text(encoding="utf-8"))
    data["assignments"]["BOB"] = "v_narr"
    sheet_path.write_text(json.dumps(data), encoding="utf-8")

    result = build_play(play_txt, voices=_mock_voices(),
                        narrator_voice="v_narr")
    assert result["cast_sheet"].assignments["BOB"] == "v_narr"


def test_cast_override_applies(play_txt, run_dir):
    result = build_play(
        play_txt, voices=_mock_voices(), narrator_voice="v_narr",
        cast_override={"ALICE": "v_beta"},
    )
    assert result["cast_sheet"].assignments["ALICE"] == "v_beta"


def test_unknown_override_voice_raises(play_txt, run_dir):
    with pytest.raises(ValueError):
        build_play(play_txt, voices=_mock_voices(), narrator_voice="v_narr",
                   cast_override={"ALICE": "nope"})


def test_unknown_narrator_raises(play_txt, run_dir):
    with pytest.raises(ValueError, match="narrator"):
        build_play(play_txt, voices=_mock_voices(), narrator_voice="nope")


def test_non_play_input_raises(tmp_path, run_dir):
    p = tmp_path / "notaplay.txt"
    p.write_text("Just some prose with no speakers at all.\n", encoding="utf-8")
    with pytest.raises(ValueError, match="speakers"):
        build_play(p, voices=_mock_voices(), narrator_voice="v_narr")


# ── tone hints reach synthesis ───────────────────────────────────────────────

def test_tone_hint_audible_in_draft(play_txt, run_dir):
    """MockEngine renders somber as a 110 Hz tone — non-silent audio."""
    result = build_play(
        play_txt, voices=_mock_voices(), narrator_voice="v_narr",
        approve=True, draft=True, engine_factory=_mock_factory(),
    )
    import numpy as np
    import soundfile as sf
    # Act I chapter contains the somber speech → some non-zero samples
    act1 = result["chapter_results"][0]["wav"]
    data, _ = sf.read(str(act1))
    assert np.abs(data).max() > 0


def test_no_tone_hints_flag_silences_tones(play_txt, run_dir):
    result = build_play(
        play_txt, voices=_mock_voices(), narrator_voice="v_narr",
        approve=True, draft=True, engine_factory=_mock_factory(),
        use_tone_hints=False,
    )
    import numpy as np
    import soundfile as sf
    # MockEngine renders neutral as silence → all-zero audio everywhere
    for cr in result["chapter_results"]:
        data, _ = sf.read(str(cr["wav"]))
        assert np.abs(data).max() == 0


# ── play.json round-trip input ───────────────────────────────────────────────

def test_play_json_input(play_txt, run_dir, tmp_path):
    from vorpal.play.parser import parse_play
    play = parse_play(MINI_PLAY)
    json_path = tmp_path / "pocket.json"
    json_path.write_text(json.dumps(play.to_dict()), encoding="utf-8")
    loaded = load_play(json_path)
    assert loaded.speakers == ["ALICE", "BOB"]
    result = build_play(json_path, voices=_mock_voices(),
                        narrator_voice="v_narr")
    assert result["status"] == "review"


# ── CLI parser ───────────────────────────────────────────────────────────────

def test_play_subcommand_defaults():
    args = build_parser().parse_args(["play", "hamlet.txt"])
    assert args.command == "play"
    assert args.chapters == "act"
    assert args.stage_directions == "skip"
    assert args.voice == "bm_lewis"
    assert args.approve is False
    assert args.draft is False
    assert args.profile == "headphones"
    assert args.no_tone_hints is False


def test_play_subcommand_flags():
    args = build_parser().parse_args([
        "play", "hamlet.txt", "--chapters", "scene",
        "--stage-directions", "narrator", "--cast-override", "ov.json",
        "--voice", "bm_george", "--approve", "--draft",
        "--profile", "car", "--no-tone-hints", "--output", "ham",
    ])
    assert args.chapters == "scene"
    assert args.stage_directions == "narrator"
    assert args.cast_override == "ov.json"
    assert args.voice == "bm_george"
    assert args.approve and args.draft
    assert args.profile == "car"
    assert args.no_tone_hints is True
    assert args.output == "ham"


def test_build_subcommand_unchanged():
    """`vorpal build` on a non-play file: parser surface unaffected."""
    args = build_parser().parse_args(["build", "book.pdf"])
    assert args.command == "build"
    assert not hasattr(args, "stage_directions")
