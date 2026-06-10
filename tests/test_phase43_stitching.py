"""Phase 43: audio stitching quality fix.

Part 1 — chunking hierarchy in normalize.normalize_chapter():
  paragraph boundaries always flush; oversized paragraphs split at sentence
  boundaries only; a sentence is NEVER cut mid-sentence (oversized sentences
  emit intact).

Part 2 — crossfade stitching in synth.assemble_chapter_wav():
  intra-paragraph joins (pause 0) get a short linear crossfade; paragraph
  joins keep their silence; crossfade_ms=0 restores hard-cut behavior.
"""

import numpy as np
import pytest
import soundfile as sf

from vorpal.normalize import (
    PAUSE_PARAGRAPH_MS, assert_no_loss, normalize_chapter,
)
from vorpal.synth import DEFAULT_CROSSFADE_MS, assemble_chapter_wav

SENT = "The quick brown fox jumps over the lazy dog."
SR = 24000


# ── Part 1: chunking hierarchy ────────────────────────────────────────────

def test_paragraphs_never_merge_even_when_short():
    # Three tiny paragraphs, all of which would fit in one 400-char chunk.
    body = "One.\n\nTwo.\n\nThree."
    chunks = normalize_chapter(body, max_chars=400)
    assert len(chunks) == 3
    assert chunks[0].text == "One." and chunks[1].text == "Two."
    # paragraph pause on every chunk except the chapter-final one
    assert chunks[0].pause_after_ms == PAUSE_PARAGRAPH_MS
    assert chunks[1].pause_after_ms == PAUSE_PARAGRAPH_MS
    assert chunks[2].pause_after_ms == 0


def test_long_paragraph_splits_at_sentence_boundaries_only():
    body = " ".join([SENT] * 12)          # one paragraph, ~540 words of chars
    chunks = normalize_chapter(body, max_chars=150)
    assert len(chunks) > 1
    for c in chunks:
        # every chunk is a whole number of sentences
        assert c.text.rstrip()[-1] in ".!?"
        assert c.text.startswith("The quick")
    # intra-paragraph joins carry pause 0 (crossfaded at assembly)
    assert all(c.pause_after_ms == 0 for c in chunks)
    assert_no_loss(body, chunks)


def test_oversized_sentence_emitted_intact_never_truncated():
    # A single sentence well over max_chars: many comma clauses, no period
    # until the end — the old chunker cut this at commas (mid-sentence).
    long_sent = ("The army was built " + "not from above, " * 30 +
                 "but from the struggle itself.")
    chunks = normalize_chapter(long_sent, max_chars=200)
    assert len(chunks) == 1
    assert len(chunks[0].text) > 200          # oversized, intact
    assert chunks[0].text.endswith("struggle itself.")
    assert_no_loss(long_sent, chunks)


def test_oversized_sentence_mid_paragraph_flushes_and_continues():
    long_sent = ("It contained " + "clause after clause, " * 25 +
                 "and ended at last.")
    body = f"{SENT} {long_sent} {SENT}"
    chunks = normalize_chapter(body, max_chars=200)
    texts = [c.text for c in chunks]
    # the oversized sentence is one intact chunk somewhere in the middle
    assert any(t.startswith("It contained") and t.endswith("at last.")
               for t in texts)
    assert_no_loss(body, chunks)


def test_oversized_sentence_at_paragraph_end_carries_paragraph_pause():
    long_sent = "A sentence " + "with many words, " * 25 + "ending here."
    body = f"{long_sent}\n\nNext paragraph."
    chunks = normalize_chapter(body, max_chars=150)
    assert chunks[0].text.endswith("ending here.")
    assert chunks[0].pause_after_ms == PAUSE_PARAGRAPH_MS
    assert chunks[-1].pause_after_ms == 0


# ── Part 2: crossfade stitching ───────────────────────────────────────────

def _write_wav(path, value, n_samples, sr=SR):
    data = np.full(n_samples, value, dtype="float32")
    sf.write(str(path), data, sr)
    return path


def test_crossfade_output_length_and_validity(tmp_path):
    cf_ms = 25
    cf_samples = int(cf_ms / 1000 * SR)
    a = _write_wav(tmp_path / "a.wav", 0.5, SR)        # 1 s at 0.5
    b = _write_wav(tmp_path / "b.wav", -0.5, SR)       # 1 s at -0.5
    out = tmp_path / "out.wav"
    frames, sr = assemble_chapter_wav(
        [(a, 0), (b, 0)], out, crossfade_ms=cf_ms)
    assert sr == SR
    assert frames == 2 * SR - cf_samples               # len_a + len_b - cf
    data, sr2 = sf.read(str(out), dtype="float32")
    assert sr2 == SR and len(data) == frames           # valid, length matches
    assert np.max(np.abs(data)) <= 1.0                 # no clipping
    # blend region runs 0.5 → -0.5 linearly; flat elsewhere
    join = data[SR - cf_samples:SR]
    assert join[0] == pytest.approx(0.5, abs=0.01)
    assert join[-1] == pytest.approx(-0.5, abs=0.01)
    assert np.all(np.diff(join) <= 0)                  # monotone ramp


def test_paragraph_gap_silence_unchanged(tmp_path):
    a = _write_wav(tmp_path / "a.wav", 0.4, SR)
    b = _write_wav(tmp_path / "b.wav", 0.4, SR)
    out = tmp_path / "out.wav"
    frames, sr = assemble_chapter_wav(
        [(a, PAUSE_PARAGRAPH_MS), (b, 0)], out, crossfade_ms=25)
    pause_samples = int(PAUSE_PARAGRAPH_MS / 1000 * SR)
    assert frames == 2 * SR + pause_samples            # full silence kept
    data, _ = sf.read(str(out), dtype="float32")
    # the gap really is silent
    assert np.all(data[SR:SR + pause_samples] == 0.0)


def test_crossfade_zero_restores_hard_cut_with_breath(tmp_path):
    a = _write_wav(tmp_path / "a.wav", 0.4, SR)
    b = _write_wav(tmp_path / "b.wav", 0.4, SR)
    out = tmp_path / "out.wav"
    frames, _ = assemble_chapter_wav(
        [(a, 0), (b, 0)], out, crossfade_ms=0)
    breath = int(50 / 1000 * SR)                       # pre-Phase-43 pacing
    assert frames == 2 * SR + 2 * breath               # breath after each


def test_chunk_too_short_to_crossfade_falls_back_to_hard_join(tmp_path):
    cf_ms = 25
    short_n = int(cf_ms / 1000 * SR)                   # == cf window, < 2x
    a = _write_wav(tmp_path / "a.wav", 0.4, SR)
    b = _write_wav(tmp_path / "b.wav", 0.4, short_n)
    out = tmp_path / "out.wav"
    frames, _ = assemble_chapter_wav(
        [(a, 0), (b, 0)], out, crossfade_ms=cf_ms)
    data, _ = sf.read(str(out), dtype="float32")
    assert len(data) == frames
    # nothing dropped: all of a and all of b are present
    assert frames == SR + short_n


def test_single_chunk_chapter(tmp_path):
    a = _write_wav(tmp_path / "a.wav", 0.3, SR)
    out = tmp_path / "out.wav"
    frames, sr = assemble_chapter_wav([(a, 0)], out,
                                      crossfade_ms=DEFAULT_CROSSFADE_MS)
    # tail held back is flushed at end — no audio lost
    assert frames == SR
    data, _ = sf.read(str(out), dtype="float32")
    assert len(data) == SR


def test_three_chunk_chain_crossfades_each_join(tmp_path):
    cf_samples = int(25 / 1000 * SR)
    paths = [_write_wav(tmp_path / f"{i}.wav", 0.2, SR) for i in range(3)]
    out = tmp_path / "out.wav"
    frames, _ = assemble_chapter_wav(
        [(p, 0) for p in paths], out, crossfade_ms=25)
    assert frames == 3 * SR - 2 * cf_samples
