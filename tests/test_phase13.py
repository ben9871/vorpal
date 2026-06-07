"""Phase 13 — Pronunciation lexicon tests.

All tests are deterministic and do not call any LLM backend.
"""

import pytest
from vorpal.lexicon import (
    extract_proper_nouns,
    apply_lexicon_to_text,
    merge_lexicon,
    _parse_proposal,
    _cache_key,
)


# ── extract_proper_nouns ──────────────────────────────────────────────────────


def test_extract_finds_proper_nouns():
    text = "He met Shulamith in Berlin. Later he visited Paris."
    nouns = extract_proper_nouns(text)
    assert "Shulamith" in nouns
    assert "Berlin" in nouns
    assert "Paris" in nouns


def test_extract_skips_sentence_initial():
    # "He" is sentence-initial — should not be extracted as a proper noun
    text = "He went to London yesterday."
    nouns = extract_proper_nouns(text)
    # "He" is the first word of the sentence, so it should be excluded
    # London is after sentence start — included
    assert "London" in nouns


def test_extract_skips_common_caps():
    text = "In January he met The American at New York."
    nouns = extract_proper_nouns(text)
    # "January", "The", "American", "New" are in the common-caps filter
    assert "January" not in nouns
    assert "The" not in nouns


def test_extract_empty_text():
    assert extract_proper_nouns("") == []


def test_extract_no_proper_nouns():
    # All lowercase, no proper nouns
    text = "the quick brown fox jumped over the lazy dog."
    nouns = extract_proper_nouns(text)
    assert nouns == []


def test_extract_deduplicates():
    text = "Habermas argues. According to Habermas this is key. Habermas repeats."
    nouns = extract_proper_nouns(text)
    assert nouns.count("Habermas") == 1


def test_extract_returns_sorted():
    text = "He met Zelda in Austin and Beatrice in Chicago."
    nouns = extract_proper_nouns(text)
    assert nouns == sorted(nouns)


def test_extract_caps_at_100():
    # Generate text with 200 unique proper nouns
    words = [f"Noun{i:03d}" for i in range(200)]
    text = "First word. " + " ".join(words) + "."
    nouns = extract_proper_nouns(text)
    assert len(nouns) <= 100


# ── apply_lexicon_to_text ─────────────────────────────────────────────────────


def test_apply_approved_entry():
    entries = [{"word": "Habermas", "spoken_form": "Hah-ber-mahss", "approved": True}]
    result = apply_lexicon_to_text("Habermas argues Habermas repeats.", entries)
    assert result == "Hah-ber-mahss argues Hah-ber-mahss repeats."


def test_apply_unapproved_entry_unchanged():
    entries = [{"word": "Shulamith", "spoken_form": "Shoo-lah-mith", "approved": False}]
    text = "Shulamith Firestone wrote this."
    assert apply_lexicon_to_text(text, entries) == text


def test_apply_no_entries():
    text = "Some text here."
    assert apply_lexicon_to_text(text, []) == text


def test_apply_word_boundary():
    # Should not replace "Paris" inside "Parisian"
    entries = [{"word": "Paris", "spoken_form": "PEHR-ee", "approved": True}]
    text = "Paris is beautiful. Parisian culture is rich."
    result = apply_lexicon_to_text(text, entries)
    assert "PEHR-ee is beautiful" in result
    assert "Parisian" in result  # unchanged


def test_apply_longer_form_first():
    # "New York" longer than "New" — longer match should not be broken
    entries = [
        {"word": "New", "spoken_form": "Noo", "approved": True},
        {"word": "New York", "spoken_form": "Nyoo York", "approved": True},
    ]
    text = "He visited New York."
    result = apply_lexicon_to_text(text, entries)
    # "New York" must match before "New" alone
    assert "Nyoo York" in result


def test_apply_mixed_approved():
    entries = [
        {"word": "Habermas", "spoken_form": "Hah-ber-mahss", "approved": True},
        {"word": "Foucault", "spoken_form": "Foo-koh", "approved": False},
    ]
    text = "Habermas and Foucault debated."
    result = apply_lexicon_to_text(text, entries)
    assert "Hah-ber-mahss" in result
    assert "Foucault" in result  # unapproved, unchanged


# ── merge_lexicon ─────────────────────────────────────────────────────────────


def test_merge_adds_new_entries():
    existing = []
    proposed = [{"word": "Shulamith", "spoken_form": "Shoo-lah-mith", "approved": False}]
    merged = merge_lexicon(existing, proposed)
    assert len(merged) == 1
    assert merged[0]["word"] == "Shulamith"


def test_merge_preserves_approved():
    existing = [{"word": "Habermas", "spoken_form": "old form", "approved": True}]
    proposed = [{"word": "Habermas", "spoken_form": "new form", "approved": False}]
    merged = merge_lexicon(existing, proposed)
    # Approved entry must not be overwritten
    match = next(e for e in merged if e["word"] == "Habermas")
    assert match["spoken_form"] == "old form"
    assert match["approved"] is True


def test_merge_updates_unapproved():
    existing = [{"word": "Gramsci", "spoken_form": "old", "approved": False}]
    proposed = [{"word": "Gramsci", "spoken_form": "Gram-shee", "approved": False}]
    merged = merge_lexicon(existing, proposed)
    match = next(e for e in merged if e["word"] == "Gramsci")
    assert match["spoken_form"] == "Gram-shee"


def test_merge_no_duplicates():
    existing = [{"word": "Adorno", "spoken_form": "Ah-dor-no", "approved": False}]
    proposed = [{"word": "Adorno", "spoken_form": "Ah-dor-no", "approved": False}]
    merged = merge_lexicon(existing, proposed)
    words = [e["word"] for e in merged]
    assert words.count("Adorno") == 1


def test_merge_combines_distinct():
    existing = [{"word": "Adorno", "spoken_form": "Ah-dor-no", "approved": True}]
    proposed = [{"word": "Horkheimer", "spoken_form": "Hork-high-mer", "approved": False}]
    merged = merge_lexicon(existing, proposed)
    assert len(merged) == 2
    words = {e["word"] for e in merged}
    assert "Adorno" in words
    assert "Horkheimer" in words


# ── _parse_proposal ───────────────────────────────────────────────────────────


def test_parse_proposal_valid():
    raw = '[{"word": "Habermas", "spoken_form": "Hah-ber-mahss"}]'
    result = _parse_proposal(raw)
    assert len(result) == 1
    assert result[0]["word"] == "Habermas"
    assert result[0]["approved"] is False


def test_parse_proposal_fenced():
    raw = '```json\n[{"word": "Test", "spoken_form": "Tehst"}]\n```'
    result = _parse_proposal(raw)
    assert len(result) == 1
    assert result[0]["word"] == "Test"


def test_parse_proposal_empty_array():
    assert _parse_proposal("[]") == []


def test_parse_proposal_invalid_json():
    assert _parse_proposal("not json at all") == []


def test_parse_proposal_skips_identity():
    # word == spoken_form should be skipped (no pronunciation hint needed)
    raw = '[{"word": "London", "spoken_form": "London"}]'
    result = _parse_proposal(raw)
    assert result == []


def test_parse_proposal_skips_missing_fields():
    raw = '[{"word": "", "spoken_form": "something"}]'
    result = _parse_proposal(raw)
    assert result == []


# ── cache key ─────────────────────────────────────────────────────────────────


def test_cache_key_deterministic():
    words = ["Habermas", "Adorno"]
    k1 = _cache_key(words, "My Book")
    k2 = _cache_key(words, "My Book")
    assert k1 == k2


def test_cache_key_order_independent():
    k1 = _cache_key(["Adorno", "Habermas"], "My Book")
    k2 = _cache_key(["Habermas", "Adorno"], "My Book")
    assert k1 == k2


def test_cache_key_title_matters():
    words = ["Habermas"]
    k1 = _cache_key(words, "Book A")
    k2 = _cache_key(words, "Book B")
    assert k1 != k2


# ── CLI parser flags ──────────────────────────────────────────────────────────


def test_build_parser_has_lexicon_flags():
    from vorpal.cli import build_parser
    parser = build_parser()
    args = parser.parse_args(["build", "book.pdf", "--lexicon",
                               "--lexicon-backend", "api"])
    assert args.lexicon is True
    assert args.lexicon_backend == "api"


def test_build_parser_lexicon_defaults():
    from vorpal.cli import build_parser
    parser = build_parser()
    args = parser.parse_args(["build", "book.pdf"])
    assert args.lexicon is False
    assert args.lexicon_backend == "cli"


def test_review_parser_has_lexicon_flag():
    from vorpal.cli import build_parser
    parser = build_parser()
    args = parser.parse_args(["review", "book.pdf", "--lexicon"])
    assert args.lexicon is True
