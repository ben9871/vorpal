"""Phase 35 — Multi-voice synthesis routing.

MockEngine only — no GPU, no network.
"""

import pytest

from vorpal.normalize import Chunk
from vorpal.play.casting import CastSheet
from vorpal.play.models import Beat
from vorpal.play.synth_router import (
    PAUSE_TURN_MS,
    route_chunks,
    synthesize_routed_chunks,
)
from vorpal.synth import _cache_key
from vorpal.tts.mock_engine import MockEngine


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def sheet():
    return CastSheet(
        assignments={"ALICE": "af_one", "BOB": "am_two"},
        narrator_voice="bm_narr",
    )


@pytest.fixture
def exchange():
    """2-character 4-beat exchange with a direction in the middle."""
    return [
        Beat(type="speech", speaker="ALICE", text="Where am I going?"),
        Beat(type="speech", speaker="BOB", text="That depends on where you want to get to."),
        Beat(type="direction", speaker=None, text="[BOB vanishes slowly.]"),
        Beat(type="speech", speaker="ALICE", text="I do not much care where."),
        Beat(type="speech", speaker="BOB", text="Then it does not matter which way you go."),
    ]


# ── route_chunks: speeches ───────────────────────────────────────────────────

def test_four_speeches_routed_to_correct_voices(exchange, sheet):
    chunks = route_chunks(exchange, sheet)  # default: skip directions
    assert len(chunks) == 4
    assert [c.voice_id for c in chunks] == ["af_one", "am_two", "af_one", "am_two"]


def test_chunk_text_preserved(exchange, sheet):
    chunks = route_chunks(exchange, sheet)
    assert chunks[0].text.startswith("Where am I going")


def test_chunks_reindexed_sequentially(exchange, sheet):
    chunks = route_chunks(exchange, sheet)
    assert [c.idx for c in chunks] == list(range(len(chunks)))


def test_turn_pause_applied(exchange, sheet):
    chunks = route_chunks(exchange, sheet)
    # Every beat here yields one chunk; each ends a speaking turn.
    assert all(c.pause_after_ms >= PAUSE_TURN_MS for c in chunks)


def test_long_speech_splits_into_multiple_chunks(sheet):
    long_text = " ".join(
        f"Sentence number {i} is here to make this speech very long indeed."
        for i in range(20)
    )
    beats = [Beat(type="speech", speaker="ALICE", text=long_text)]
    chunks = route_chunks(beats, sheet, max_chars=200)
    assert len(chunks) > 1
    assert all(c.voice_id == "af_one" for c in chunks)
    # Only the final chunk of the beat carries the turn pause
    assert chunks[-1].pause_after_ms >= PAUSE_TURN_MS


# ── route_chunks: stage directions ───────────────────────────────────────────

def test_directions_dropped_by_default(exchange, sheet):
    chunks = route_chunks(exchange, sheet, stage_directions="skip")
    assert not any(c.voice_id == "bm_narr" for c in chunks)
    assert not any("vanishes" in c.text for c in chunks)


def test_directions_narrated_with_narrator_voice(exchange, sheet):
    chunks = route_chunks(exchange, sheet, stage_directions="narrator")
    narr = [c for c in chunks if c.voice_id == "bm_narr"]
    assert len(narr) == 1
    assert "vanishes" in narr[0].text
    # Brackets stripped for narration
    assert "[" not in narr[0].text


def test_direction_order_preserved(exchange, sheet):
    chunks = route_chunks(exchange, sheet, stage_directions="narrator")
    voices = [c.voice_id for c in chunks]
    assert voices == ["af_one", "am_two", "bm_narr", "af_one", "am_two"]


def test_invalid_stage_directions_mode_raises(exchange, sheet):
    with pytest.raises(ValueError):
        route_chunks(exchange, sheet, stage_directions="mumble")


def test_unknown_speaker_raises(sheet):
    beats = [Beat(type="speech", speaker="CHESHIRE", text="We're all mad here.")]
    with pytest.raises(ValueError, match="CHESHIRE"):
        route_chunks(beats, sheet)


# ── cache keys ───────────────────────────────────────────────────────────────

def test_cache_key_without_voice_id_unchanged():
    """Zero drift: a voiceless chunk's key is byte-identical to pre-Phase-35."""
    engine = MockEngine(voice="bookvoice")
    chunk = Chunk(0, "Hello.", 0, None, "abc123")
    assert _cache_key(chunk, engine) == "abc123_mock_bookvoice_1_0_none.wav"


def test_cache_key_differs_between_characters():
    engine = MockEngine(voice="shared_engine")
    a = Chunk(0, "Hello.", 0, None, "abc123", voice_id="af_one")
    b = Chunk(0, "Hello.", 0, None, "abc123", voice_id="am_two")
    none = Chunk(0, "Hello.", 0, None, "abc123")
    keys = {_cache_key(a, engine), _cache_key(b, engine), _cache_key(none, engine)}
    assert len(keys) == 3


def test_cache_key_voice_suffix_format():
    engine = MockEngine(voice="v")
    chunk = Chunk(0, "Hi.", 0, None, "deadbeef", voice_id="af_one")
    assert _cache_key(chunk, engine).endswith("_vc_af_one.wav")


# ── synthesize_routed_chunks ─────────────────────────────────────────────────

@pytest.fixture
def engines():
    return {
        "af_one": MockEngine(voice="af_one"),
        "am_two": MockEngine(voice="am_two"),
        "bm_narr": MockEngine(voice="bm_narr"),
    }


def test_synthesis_routes_to_distinct_voices(exchange, sheet, engines, tmp_path):
    chunks = route_chunks(exchange, sheet, stage_directions="narrator")
    chunk_wavs, report = synthesize_routed_chunks(chunks, engines, tmp_path)
    assert len(chunk_wavs) == 5
    assert report == {"done": 5, "cached": 0}
    # Each chunk landed in a per-voice cache file
    names = [p.name for p, _pause in chunk_wavs]
    assert sum("_vc_af_one" in n for n in names) == 2
    assert sum("_vc_am_two" in n for n in names) == 2
    assert sum("_vc_bm_narr" in n for n in names) == 1
    assert all(p.exists() for p, _pause in chunk_wavs)


def test_second_run_is_all_cache_hits(exchange, sheet, engines, tmp_path):
    chunks = route_chunks(exchange, sheet)
    _, first = synthesize_routed_chunks(chunks, engines, tmp_path)
    _, second = synthesize_routed_chunks(chunks, engines, tmp_path)
    assert first["done"] == 4
    assert second == {"done": 0, "cached": 4}


def test_missing_engine_raises(exchange, sheet, tmp_path):
    chunks = route_chunks(exchange, sheet)
    with pytest.raises(ValueError, match="am_two"):
        synthesize_routed_chunks(
            chunks, {"af_one": MockEngine(voice="af_one")}, tmp_path)


def test_pause_metadata_flows_through(exchange, sheet, engines, tmp_path):
    chunks = route_chunks(exchange, sheet)
    chunk_wavs, _ = synthesize_routed_chunks(chunks, engines, tmp_path)
    assert all(pause >= PAUSE_TURN_MS for _p, pause in chunk_wavs)


# ── Chunk dataclass compatibility ────────────────────────────────────────────

def test_chunk_voice_id_defaults_none():
    c = Chunk(0, "Text.", 0, None, "h")
    assert c.voice_id is None
    assert c.to_dict()["voice_id"] is None


def test_chunk_to_dict_round_trips_voice_id():
    c = Chunk(0, "Text.", 0, None, "h", voice_id="af_one")
    assert c.to_dict()["voice_id"] == "af_one"
