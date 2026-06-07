"""Unit tests for the TTS chunker.

Includes the regression test for the v0 empty-placeholder bug that turned
every long paragraph into ".T.h.e. .d.o.g." (docs/01-audit.md §3).
"""

import re

from audiobooker.normalize import split_into_chunks

SENTENCE = "The quick brown fox jumps over the lazy dog and keeps running. "


def _words(text: str) -> list:
    return text.split()


def test_short_paragraph_kept_whole():
    para = "A short paragraph that easily fits."
    assert split_into_chunks(para, max_chars=500) == [para]


def test_no_character_dotting_regression():
    """v0 inserted a period between EVERY character of long paragraphs."""
    para = (SENTENCE * 20).strip()  # well over max_chars, forces sentence split
    chunks = split_into_chunks(para, max_chars=200)
    assert len(chunks) > 1
    for chunk in chunks:
        assert ".T.h" not in chunk
        assert not re.search(r"\.\w\.\w\.", chunk), f"dotted garbage in chunk: {chunk[:60]}"
        # Every chunk must be a verbatim substring of the source paragraph
        assert chunk in para


def test_no_words_lost_or_duplicated():
    para = (SENTENCE * 20).strip()
    chunks = split_into_chunks(para, max_chars=200)
    assert _words(" ".join(chunks)) == _words(para)


def test_abbreviations_do_not_split_sentences():
    para = (
        "Dr. Smith and Mrs. Jones went to the lab. "
        "They worked for hours on the experiment together until late."
    )
    chunks = split_into_chunks(para, max_chars=60)
    joined = " ".join(chunks)
    # Periods restored intact
    assert "Dr. Smith" in joined
    assert "Mrs. Jones" in joined
    # No chunk ends mid-abbreviation (i.e. "Dr." never ends a chunk)
    for chunk in chunks:
        assert not chunk.endswith("Dr.")
        assert not chunk.endswith("Mrs.")


def test_max_chars_respected_for_normal_sentences():
    para = (SENTENCE * 20).strip()
    chunks = split_into_chunks(para, max_chars=200)
    assert all(len(c) <= 200 for c in chunks)


def test_paragraph_boundaries_respected():
    text = "First paragraph here.\n\nSecond paragraph here."
    chunks = split_into_chunks(text, max_chars=500)
    assert chunks == ["First paragraph here.", "Second paragraph here."]


def test_empty_and_whitespace_input():
    assert split_into_chunks("", max_chars=200) == []
    assert split_into_chunks("\n\n  \n\n", max_chars=200) == []
