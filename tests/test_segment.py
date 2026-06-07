"""Integration tests for the segment stage driver (segment_pages).

The v0 regex-splitting tests this file used to hold died with the v0 logic;
unit coverage for each sub-stage lives in test_boilerplate / test_footnotes /
test_repair / test_chapters. This file checks they compose.
"""

from vorpal.extract.pagemodel import Block, Page
from vorpal.segment import Section, segment_pages

W, H = 600, 800
PARA = ("Plain body prose, the kind a narrator should read aloud. " * 8).strip()


def page(index, blocks):
    return Page(index=index, kind="digital", width=W, height=H, blocks=blocks)


def make_book(titles, pages_per_chapter=3):
    pages, outline = [], []
    idx = 0
    for n, title in enumerate(titles, 1):
        outline.append({"level": 1, "title": title, "page": idx + 1})
        for j in range(pages_per_chapter):
            blocks = []
            blocks.append(Block(bbox=(60, 20, 400, 32),
                                text=f"{idx + 10} THE RUNNING HEADER"))
            if j == 0:
                blocks.append(Block(bbox=(72, 90, 400, 120),
                                    text=title.upper(), font_size=18.0))
            blocks.append(Block(bbox=(72, 200, 540, 600),
                                text=f"{PARA} (page {idx}.)", font_size=11.0))
            blocks.append(Block(bbox=(290, 760, 310, 775), text=str(idx + 10)))
            pages.append(page(idx, blocks))
            idx += 1
    return pages, outline


def test_segment_pages_composes_all_stages():
    pages, outline = make_book(["First Movement", "Second Movement"])
    result = segment_pages(pages, outline=outline)

    assert result.source == "outline"
    chapters = [s for s in result.sections if s.kind == "chapter"]
    assert [s.title for s in chapters] == ["First Movement", "Second Movement"]

    all_bodies = "\n".join(result.bodies[s.id] for s in chapters)
    assert "RUNNING HEADER" not in all_bodies          # boilerplate gone
    assert "(page 0.)" in all_bodies                   # body text kept
    assert "(page 5.)" in all_bodies

    qa = result.qa
    assert qa["chapter_source"] == "outline"
    assert qa["header_lines_removed"] >= 6
    assert qa["page_number_lines_removed"] >= 6


def test_segment_result_round_trips_through_manifest_dicts():
    pages, outline = make_book(["Alpha Section", "Omega Section"])
    result = segment_pages(pages, outline=outline)
    dicts = [s.to_dict() for s in result.sections]
    restored = [Section.from_dict(d) for d in dicts]
    assert [(s.id, s.title, s.kind, s.include, s.start, s.end)
            for s in restored] == \
           [(s.id, s.title, s.kind, s.include, s.start, s.end)
            for s in result.sections]


def test_section_body_stored_inline():
    """Sections with body stored inline (EPUB/TXT path) round-trip correctly."""
    s = Section(
        id=1, title="Chapter One", kind="chapter", include=True,
        start=(0, 0), end=(0, 0), source="spine", confidence=1.0,
        body="This is the stored body text for an EPUB section.",
    )
    d = s.to_dict()
    assert d["body"] == "This is the stored body text for an EPUB section."
    restored = Section.from_dict(d)
    assert restored.body == s.body

    # section_body() returns stored body, not page-lookup
    from vorpal.segment.chapters import section_body
    assert section_body(restored, []) == s.body


def test_section_body_empty_not_stored():
    """PDF sections (no inline body) don't emit a 'body' key in the dict."""
    s = Section(
        id=1, title="Chapter One", kind="chapter", include=True,
        start=(0, 0), end=(0, 0), source="outline", confidence=0.9,
    )
    d = s.to_dict()
    assert "body" not in d
