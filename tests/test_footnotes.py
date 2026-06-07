"""Unit tests for footnote separation."""

from audiobooker.extract.pagemodel import Block, Page
from audiobooker.segment.footnotes import separate_footnotes

W, H = 600, 800


def make_page(blocks, index=0):
    return Page(index=index, kind="scanned", width=W, height=H, blocks=blocks)


def body(text, y=100, h=400, font_size=None):
    return Block(bbox=(50, y, 550, y + h), text=text, font_size=font_size)


def note(text, y=700, h=40, font_size=None):
    return Block(bbox=(50, y, 550, y + h), text=text, font_size=font_size)


def all_text(pages):
    return "\n".join(b.text for p in pages for b in p.blocks)


def test_star_footnote_moved_to_side_channel():
    pages = [make_page([
        body("The early movement* was radical in character."),
        note("* Hereafter abbreviated as the movement, for brevity."),
    ])]
    report = separate_footnotes(pages)
    assert len(report.footnotes) == 1
    assert "Hereafter abbreviated" in report.footnotes[0].text
    assert "Hereafter" not in all_text(pages)


def test_body_reference_marker_stripped():
    pages = [make_page([
        body("The early movement,* it is said, was radical."),
        note("* A footnote with enough prose to count as one."),
    ])]
    report = separate_footnotes(pages)
    assert report.markers_stripped == 1
    assert "movement, it is said" in all_text(pages)


def test_numbered_body_list_is_not_a_footnote():
    # Firestone's numbered arguments live at the bottom of scanned pages;
    # on scans, digit markers must never be treated as footnotes.
    pages = [make_page([
        body("Consider the following:"),
        note("1) That women throughout history were at the mercy of biology."),
    ])]
    report = separate_footnotes(pages)
    assert not report.footnotes
    assert "That women throughout history" in all_text(pages)


def test_numbered_footnote_accepted_on_digital_small_font():
    pages = [make_page([
        body("Body paragraph with a reference.", font_size=11.0),
        note("1. A numbered footnote in the smaller print of the digital path.",
             font_size=8.5),
    ])]
    report = separate_footnotes(pages)
    assert len(report.footnotes) == 1


def test_normal_font_bottom_block_kept_on_digital():
    pages = [make_page([
        body("Body paragraph.", font_size=11.0),
        note("* Emphasis line at body size, not a footnote at all.", font_size=11.0),
    ])]
    report = separate_footnotes(pages)
    assert not report.footnotes


def test_divider_and_allcaps_blocks_are_not_footnotes():
    pages = [make_page([
        body("Body text."),
        note("* * *", y=660),
        note("10. FEMINISM AND ECOLOGY\nCONCLUSION", y=710),
    ])]
    report = separate_footnotes(pages)
    assert not report.footnotes
    assert "FEMINISM AND ECOLOGY" in all_text(pages)


def test_unmarked_continuation_directly_below_is_merged():
    pages = [make_page([
        body("Body text referencing something.*"),
        note("* A long footnote whose OCR block was split into", y=700, h=30),
        note("two pieces, this being the continuation line.", y=732, h=20),
    ])]
    report = separate_footnotes(pages)
    assert len(report.footnotes) == 1
    assert "continuation line" in report.footnotes[0].text
    assert "continuation" not in all_text(pages)


def test_distant_unmarked_block_is_not_swallowed():
    pages = [make_page([
        note("* A footnote near the bottom of the page region.", y=560, h=20),
        note("Ordinary body text well below the footnote's block.", y=700, h=20),
    ])]
    report = separate_footnotes(pages)
    assert len(report.footnotes) == 1
    assert "Ordinary body text" in all_text(pages)


def test_columns_are_independent():
    # two-page spread: a footnote in the left column must not swallow a
    # right-column block at the same height
    left_note = Block(bbox=(30, 700, 280, 740), text="* Left column footnote prose here.")
    right_body = Block(bbox=(320, 700, 570, 760), text="Right column body text continues.")
    pages = [make_page([left_note, right_body])]
    report = separate_footnotes(pages)
    assert len(report.footnotes) == 1
    assert "Right column body" in all_text(pages)
