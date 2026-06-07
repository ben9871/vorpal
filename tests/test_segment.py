"""Unit tests for v0-ported cleanup and chapter splitting.

These pin the *intended* stable behaviors. The heading heuristics themselves
are known-bad (docs/01-audit.md §2) and will be replaced in Phase 2, at which
point the splitting tests get rewritten against the new cascade.
"""

from audiobooker.segment import (
    clean_raw_text,
    find_headings,
    is_likely_toc,
    split_into_chapters,
)

BODY_80_WORDS = (
    "This is substantial body text that goes on for a while. " * 12
).strip()


def test_clean_removes_page_break_sentinels_and_page_numbers():
    raw = "Some text here.\n\n--- PAGE BREAK ---\n\n42\nMore text follows."
    cleaned = clean_raw_text(raw)
    assert "PAGE BREAK" not in cleaned
    assert "\n42\n" not in cleaned
    assert "Some text here." in cleaned
    assert "More text follows." in cleaned


def test_clean_repairs_hyphenated_linebreaks():
    raw = "the feminist revo-\nlution had begun"
    assert "revolution" in clean_raw_text(raw)


def test_clean_strips_given_running_headers():
    raw = "THE DIALECTIC OF SEX\nactual body text continues here"
    cleaned = clean_raw_text(raw, header_patterns=["THE DIALECTIC OF SEX"])
    assert "DIALECTIC" not in cleaned
    assert "actual body text" in cleaned


def test_find_headings_detects_chapter_lines():
    text = "intro text\n\nCHAPTER ONE\nThe Beginning\n\nbody text follows here"
    headings = find_headings(text)
    assert headings, "expected at least one heading"
    assert any("CHAPTER" in title for _, title in headings)


def test_split_keeps_real_chapters_and_skips_short_junk():
    text = (
        f"CHAPTER ONE\n\n{BODY_80_WORDS}\n\n"
        f"RANDOM CAPS LINE\n\nshort junk body\n\n"
        f"CHAPTER TWO\n\n{BODY_80_WORDS}"
    )
    chapters = split_into_chapters(text)
    kept = [c for c in chapters if not c["skip"]]
    skipped = [c for c in chapters if c["skip"]]
    assert len(kept) == 2
    assert any("short junk" in c["body"] for c in skipped)


def test_split_without_headings_returns_single_chapter():
    chapters = split_into_chapters("Just plain prose with no headings at all.")
    assert len(chapters) == 1
    assert chapters[0]["skip"] is False


def test_is_likely_toc_on_dot_leaders():
    toc = (
        "Chapter One .......... 3\n"
        "Chapter Two .......... 27\n"
        "Chapter Three ........ 55\n"
        "Chapter Four ......... 89\n"
    )
    assert is_likely_toc(toc) is True


def test_is_likely_toc_on_prose():
    assert is_likely_toc(BODY_80_WORDS + "\nMore lines.\nAnd more.\nAnd more.") is False
