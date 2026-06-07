"""Unit tests for Phase-3 normalize.py.

Table-driven tests covering:
  - spoken_form(): numbers, ordinals, years, ranges, roman numerals,
    abbreviations, citations, dashes, symbols
  - normalize_chapter(): chunk packing, paragraph pauses, no sentence splits
  - assert_no_loss(): invariant holds on realistic text, fires on corruption
  - lint_chunks(): junk-lint gate catches OCR artifacts
  - Regression: v0 .T.h.e. dotting bug must not recur
"""

import pytest

from vorpal.normalize import (
    spoken_form,
    normalize_chapter,
    assert_no_loss,
    lint_chunks,
    PAUSE_PARAGRAPH_MS,
)


# ── spoken_form: numbers ──────────────────────────────────────────────────

NUMBERS = [
    ("0",           "zero"),
    ("1",           "one"),
    ("12",          "twelve"),
    ("21",          "twenty-one"),
    ("100",         "one hundred"),
    ("101",         "one hundred one"),
    ("1000",        "one thousand"),
    ("1001",        "one thousand one"),
    ("1500",        "fifteen hundred"),   # year range → year words
    ("2000",        "two thousand"),
    ("1,000",       "one thousand"),
    ("1,000,000",   "one million"),
]

@pytest.mark.parametrize("inp,expected", NUMBERS)
def test_number_expansion(inp, expected):
    assert spoken_form(inp) == expected


# ── spoken_form: ordinals ─────────────────────────────────────────────────

ORDINALS = [
    ("1st",  "first"),
    ("2nd",  "second"),
    ("3rd",  "third"),
    ("4th",  "fourth"),
    ("11th", "eleventh"),
    ("12th", "twelfth"),
    ("21st", "twenty-first"),
    ("22nd", "twenty-second"),
    ("100th","one hundredth"),
]

@pytest.mark.parametrize("inp,expected", ORDINALS)
def test_ordinal_expansion(inp, expected):
    assert spoken_form(inp) == expected


# ── spoken_form: years ────────────────────────────────────────────────────

YEARS = [
    ("1970",  "nineteen seventy"),
    ("1900",  "nineteen hundred"),
    ("1800",  "eighteen hundred"),
    ("2001",  "two thousand one"),
    ("2010",  "twenty ten"),
    ("2023",  "twenty twenty-three"),
    # Year range
    ("1970-1980", "nineteen seventy to nineteen eighty"),
    ("1969–1970", "nineteen sixty-nine to nineteen seventy"),
]

@pytest.mark.parametrize("inp,expected", YEARS)
def test_year_expansion(inp, expected):
    result = spoken_form(inp)
    assert result == expected, f"spoken_form({inp!r}) = {result!r}"


# ── spoken_form: roman numerals ───────────────────────────────────────────

ROMANS = [
    ("Chapter I",    "Chapter one"),
    ("Chapter IV",   "Chapter four"),
    ("Chapter IX",   "Chapter nine"),
    ("Chapter XIV",  "Chapter fourteen"),
    ("Part II",      "Part two"),
    ("Volume III",   "Volume three"),
    # Roman in a heading-like context
    ("I. Introduction", "one. Introduction"),
]

@pytest.mark.parametrize("inp,expected", ROMANS)
def test_roman_numeral_expansion(inp, expected):
    result = spoken_form(inp)
    assert result == expected, f"spoken_form({inp!r}) = {result!r}"


# ── spoken_form: abbreviations survive normalization ──────────────────────

ABBREVS_INTACT = [
    # These should NOT be split by pysbd — verified via normalize_chapter
    "Dr. Smith attended the conference.",
    "Mrs. Jones and Mr. Brown met at pp. 14 of the report.",
    "The study (cf. vol. 3) examined the data.",
    "It was approx. 40 miles from the center.",
]

@pytest.mark.parametrize("text", ABBREVS_INTACT)
def test_abbreviations_dont_over_split(text):
    """Abbreviations should not create spurious chunk boundaries."""
    chunks = normalize_chapter(text, max_chars=500)
    # All text should be in one chunk (it's short and one sentence)
    assert len(chunks) >= 1
    # No chunk should end with a bare abbreviated word
    for chunk in chunks:
        assert not chunk.text.endswith("Dr.")
        assert not chunk.text.endswith("Mrs.")
        assert not chunk.text.endswith("Mr.")


# ── spoken_form: em-dash ──────────────────────────────────────────────────

DASHES = [
    ("A—B",        "A, B"),
    ("A — B",      "A, B"),
    ("A–B",        "A, B"),   # en-dash
    # Number ranges are expanded, not turned into pauses
    ("pp. 14–22",  "pages fourteen to twenty-two"),
]

@pytest.mark.parametrize("inp,expected", DASHES)
def test_dash_normalization(inp, expected):
    result = spoken_form(inp)
    assert result == expected, f"spoken_form({inp!r}) = {result!r}"


# ── spoken_form: symbols ──────────────────────────────────────────────────

SYMBOLS = [
    ("50%",  "fifty percent"),
    ("a & b", "a  and  b"),
    ("§ 3",  " section  three"),
    ("90°",  "ninety degrees"),
]

@pytest.mark.parametrize("inp,expected", SYMBOLS)
def test_symbol_expansion(inp, expected):
    result = spoken_form(inp)
    # Normalize multiple spaces for comparison
    assert " ".join(result.split()) == " ".join(expected.split())


# ── spoken_form: citation stripping ──────────────────────────────────────

CITATIONS = [
    ("The text (see pp. 14–22) continues.",    "The text continues."),
    ("She wrote (italics mine) about it.",      "She wrote  about it."),
    ("He noted (emphasis added) the gap.",      "He noted  the gap."),
    ("This is (sic) an error.",                 "This is  an error."),
]

@pytest.mark.parametrize("inp,expected", CITATIONS)
def test_citation_stripping(inp, expected):
    result = spoken_form(inp)
    assert " ".join(result.split()) == " ".join(expected.split())


# ── normalize_chapter: chunk packing ─────────────────────────────────────

SENTENCE = "The quick brown fox jumps over the lazy dog. "


def test_short_paragraph_single_chunk():
    body = "A short paragraph that easily fits in one chunk."
    chunks = normalize_chapter(body, max_chars=400)
    assert len(chunks) == 1
    assert chunks[0].pause_after_ms == 0  # last paragraph, no pause


def test_paragraph_boundary_pause():
    body = "First paragraph here.\n\nSecond paragraph here."
    chunks = normalize_chapter(body, max_chars=400)
    assert len(chunks) == 2
    # First paragraph chunk should carry the paragraph pause
    assert chunks[0].pause_after_ms == PAUSE_PARAGRAPH_MS
    # Last chunk: no pause
    assert chunks[1].pause_after_ms == 0


def test_max_chars_respected():
    body = (SENTENCE * 20).strip()
    chunks = normalize_chapter(body, max_chars=200)
    for chunk in chunks:
        assert len(chunk.text) <= 200, f"Chunk too long: {chunk.text[:60]!r}"


def test_no_sentence_split_across_chunks():
    """No chunk should end mid-sentence (i.e. with a word that is not the
    end of a sentence as detected by pysbd)."""
    body = (SENTENCE * 10).strip()
    chunks = normalize_chapter(body, max_chars=150)
    assert len(chunks) > 1
    for chunk in chunks:
        # Each chunk text should end with sentence-ending punctuation
        stripped = chunk.text.rstrip()
        assert stripped[-1] in ".!?", (
            f"Chunk ends mid-sentence: {stripped[-40:]!r}"
        )


def test_tone_field_is_none():
    body = "Every chunk carries a tone slot for the post-v1 LLM pass."
    chunks = normalize_chapter(body)
    for chunk in chunks:
        assert chunk.tone is None


def test_text_hash_present_and_stable():
    body = "Hash must be present and stable across calls."
    chunks1 = normalize_chapter(body)
    chunks2 = normalize_chapter(body)
    assert all(c.text_hash for c in chunks1)
    assert [c.text_hash for c in chunks1] == [c.text_hash for c in chunks2]


def test_chunk_idx_sequential():
    body = (SENTENCE * 15).strip()
    chunks = normalize_chapter(body, max_chars=150)
    for i, chunk in enumerate(chunks):
        assert chunk.idx == i


# ── no-loss invariant ─────────────────────────────────────────────────────

def test_no_loss_invariant_holds():
    body = (SENTENCE * 5).strip() + "\n\n" + (SENTENCE * 5).strip()
    chunks = normalize_chapter(body, max_chars=200)
    # Should not raise
    assert_no_loss(body, chunks)


def test_no_loss_invariant_fires_on_dropped_word():
    body = "The quick brown fox jumps over the lazy dog."
    chunks = normalize_chapter(body, max_chars=400)
    # Corrupt one chunk by removing a word
    from vorpal.normalize import Chunk, _text_hash
    bad_chunk = Chunk(0, "The quick fox jumps over the lazy dog.",
                      0, None, _text_hash("The quick fox jumps over the lazy dog."))
    with pytest.raises(AssertionError):
        assert_no_loss(body, [bad_chunk])


# ── unspeakable ornaments become pauses (Firestone '* * *' regression) ────

def test_divider_paragraph_becomes_pause_not_chunk():
    body = "First section ends here.\n\n* * *\n\nSecond section starts here."
    chunks = normalize_chapter(body, max_chars=400)
    assert all("*" not in c.text for c in chunks), \
        "ornament must never reach the TTS engine"
    # the divider's section break survives as a pause on the preceding chunk
    assert chunks[0].pause_after_ms >= 600
    assert_no_loss(body, chunks)            # invariant agrees ornaments aren't text


def test_divider_fused_mid_paragraph_is_skipped():
    body = "Before the break. * * *\n\nAfter the break it continues."
    chunks = normalize_chapter(body, max_chars=400)
    assert all("*" not in c.text for c in chunks)
    assert "Before the break." in chunks[0].text
    assert_no_loss(body, chunks)


def test_divider_only_body_yields_no_chunks():
    chunks = normalize_chapter("* * *", max_chars=400)
    assert chunks == []


# ── lint_chunks: junk-lint gate ───────────────────────────────────────────

def test_lint_catches_pipe_fragment():
    chunks = [{"text": "For that rare diagram freak | 3-D REVOLUTION"}]
    violations = lint_chunks(chunks, chapter_title="Test")
    assert len(violations) == 1
    assert violations[0]["pattern"] == "pipe-separated fragment"


def test_lint_catches_bare_number():
    chunks = [{"text": "127"}]
    violations = lint_chunks(chunks, chapter_title="Test")
    assert len(violations) == 1
    assert violations[0]["pattern"] == "bare number line"


def test_lint_catches_allcaps_artifact():
    chunks = [{"text": "THE DIALECTIC OF SEX"}]
    violations = lint_chunks(chunks, chapter_title="Test")
    assert len(violations) == 1
    assert violations[0]["pattern"] == "all-caps artifact"


def test_lint_clean_text_no_violations():
    chunks = [{"text": "She argued that the family is the first school of hierarchy."}]
    violations = lint_chunks(chunks, chapter_title="Test")
    assert violations == []


# ── regression: v0 character-dotting bug must not recur ──────────────────

def test_no_character_dotting_regression():
    """v0's empty-placeholder bug turned 'The dog.' into '.T.h.e. .d.o.g.'"""
    import re
    para = (SENTENCE * 20).strip()
    chunks = normalize_chapter(para, max_chars=200)
    assert len(chunks) > 1
    for chunk in chunks:
        assert ".T.h" not in chunk.text
        assert not re.search(r"\.\w\.\w\.", chunk.text), (
            f"dotted garbage in chunk: {chunk.text[:60]!r}"
        )


# ── multi-paragraph realistic text ───────────────────────────────────────

def test_realistic_book_paragraph():
    body = (
        "The material basis of the family unit became clear in the nineteenth "
        "century, when industrial capitalism separated the workplace from the home. "
        "Women were assigned to the domestic sphere, men to production.\n\n"
        "This division was not natural but historical. It arose from specific "
        "economic conditions and could, in principle, be dismantled by changing them."
    )
    chunks = normalize_chapter(body, max_chars=300)
    assert len(chunks) >= 2
    assert_no_loss(body, chunks)
    # Paragraph boundary pause exists between paragraphs
    pause_vals = [c.pause_after_ms for c in chunks]
    assert PAUSE_PARAGRAPH_MS in pause_vals
