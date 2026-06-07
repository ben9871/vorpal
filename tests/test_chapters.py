"""Unit tests for the chapter cascade (outline → TOC → heuristics) and
front/back-matter classification."""

from vorpal.extract.pagemodel import Block, Page
from vorpal.segment.chapters import Section, detect_chapters, section_body
from vorpal.segment.frontmatter import classify_title, find_back_matter_start

W, H = 600, 800
PARA = ("Sentence of ordinary body prose that the section carries forward. " * 8).strip()


def page(index, blocks, kind="digital", flagged=False, score=0.95):
    return Page(index=index, kind=kind, width=W, height=H,
                blocks=blocks, flagged=flagged, score=score, quality=score)


def heading(text, font_size=18.0):
    return Block(bbox=(72, 90, 400, 120), text=text, font_size=font_size)


def body(text=PARA, font_size=11.0, y=200):
    return Block(bbox=(72, y, 540, y + 300), text=text, font_size=font_size)


def make_book(titles, pages_per_chapter=3, with_headings=True):
    """Digital book: each chapter opens with a heading block, then body pages."""
    pages, outline = [], []
    idx = 0
    for title in titles:
        outline.append({"level": 1, "title": title, "page": idx + 1})
        first = [heading(title.upper())] if with_headings else []
        pages.append(page(idx, first + [body()]))
        idx += 1
        for _ in range(pages_per_chapter - 1):
            pages.append(page(idx, [body()]))
            idx += 1
    return pages, outline


# ── rung a: outline ───────────────────────────────────────────────────────

def test_outline_rung_wins_and_anchors():
    pages, outline = make_book(["One Beginning", "Two Middle", "Three End"])
    sections, source = detect_chapters(pages, outline)
    assert source == "outline"
    chapters = [s for s in sections if s.kind == "chapter"]
    assert [s.title for s in chapters] == ["One Beginning", "Two Middle", "Three End"]
    assert all(s.confidence == 0.95 for s in chapters)
    assert all(s.include for s in chapters)


def test_outline_body_excludes_heading_and_spans_pages():
    pages, outline = make_book(["Alpha Chapter", "Beta Chapter"])
    sections, _ = detect_chapters(pages, outline)
    first = [s for s in sections if s.kind == "chapter"][0]
    text = section_body(first, pages)
    assert "ALPHA CHAPTER" not in text          # heading not narrated as body
    assert text.count("Sentence of ordinary body prose") >= 3


def test_outline_contents_entry_classified_front_matter():
    pages, outline = make_book(["Contents", "First Chapter", "Second Chapter"])
    pages[0].blocks = [heading("CONTENTS"), body("First Chapter .... 3")]
    sections, _ = detect_chapters(pages, outline)
    contents = next(s for s in sections if s.title == "Contents")
    assert contents.kind == "frontmatter"
    assert contents.include is False
    assert sum(1 for s in sections if s.include) == 2


def test_conclusion_intro_keeps_its_c():
    # regression: 'C' is a roman numeral; _strip_enum must not eat it
    pages, outline = make_book(["1. First Things", "Conclusion"])
    sections, _ = detect_chapters(pages, outline)
    conclusion = next(s for s in sections if s.title == "Conclusion")
    assert conclusion.spoken_intro == "Conclusion."
    numbered = next(s for s in sections if s.number == 1)
    assert numbered.spoken_intro == "Chapter one. First Things."


def test_outline_rejected_when_pages_not_monotonic():
    pages, outline = make_book(["One Beginning", "Two Middle", "Three End"])
    outline[1]["page"] = 90                    # bogus outline entry
    sections, source = detect_chapters(pages, outline)
    assert source != "outline"


def test_outline_rejected_when_anchors_missing():
    pages, outline = make_book(["One Beginning", "Two Middle", "Three End"],
                               with_headings=False)
    # no heading blocks anywhere → outline can't anchor; falls through
    _, source = detect_chapters(pages, outline)
    assert source != "outline"


# ── rung b: printed TOC ──────────────────────────────────────────────────

def make_toc_book():
    titles = ["The First Path", "The Second Path", "The Third Path"]
    toc = page(0, [heading("CONTENTS"), Block(
        bbox=(72, 200, 540, 400),
        text="\n".join(f"{t} ........ {3 + i * 10}" for i, t in enumerate(titles)),
        font_size=11.0,
    )])
    pages = [toc]
    idx = 1
    for t in titles:
        pages.append(page(idx, [heading(t.upper()), body()]))
        idx += 1
        pages.append(page(idx, [body()]))
        idx += 1
    return pages, titles


def test_toc_rung_wins_without_outline():
    pages, titles = make_toc_book()
    sections, source = detect_chapters(pages, outline=None)
    assert source == "toc"
    chapters = [s for s in sections if s.kind == "chapter"]
    assert [s.title for s in chapters] == titles
    assert all(s.confidence == 0.85 for s in chapters)


def test_toc_rejected_when_titles_never_anchor():
    pages, _ = make_toc_book()
    for p in pages[1:]:
        p.blocks = [body()]                     # remove all headings
    _, source = detect_chapters(pages, outline=None)
    assert source != "toc"


# ── rung c: heuristics ───────────────────────────────────────────────────

def test_heuristic_rung_on_font_outliers():
    pages = []
    idx = 0
    for t in ["Opening Movement", "Closing Movement"]:
        pages.append(page(idx, [heading(t.upper(), font_size=20.0), body()]))
        idx += 1
        pages.extend(page(idx + j, [body()]) for j in range(2))
        idx += 2
    sections, source = detect_chapters(pages, outline=None)
    assert source == "heuristic"
    chapters = [s for s in sections if s.kind == "chapter"]
    assert len(chapters) == 2
    assert all(s.confidence == 0.5 for s in chapters)


def test_heuristic_skips_gibberish_headings():
    pages = []
    for i in range(6):
        blocks = [body()]
        if i in (0, 3):
            blocks.insert(0, heading("RZGQT XKWPF VBNMD", font_size=20.0))
        pages.append(page(i, blocks))
    _, source = detect_chapters(pages, outline=None)
    assert source == "none"                     # diagram caps ≠ chapter titles


def test_no_structure_yields_single_reviewable_section():
    pages = [page(i, [body()]) for i in range(6)]
    sections, source = detect_chapters(pages, outline=None)
    assert source == "none"
    assert len(sections) == 1
    assert sections[0].flags == ["no-structure-found"]
    assert sections[0].include is True
    # every page's body present: 6 pages x 8 sentence repetitions
    assert section_body(sections[0], pages).count("Sentence of ordinary") == 48


# ── figure pages & back matter ───────────────────────────────────────────

def test_figure_page_excluded_from_body():
    pages, outline = make_book(["Solo Chapter", "Last Chapter"], pages_per_chapter=4)
    fig = pages[5]
    fig.flagged, fig.score = True, 0.2
    fig.blocks = [body("WOO33Y3 TWNX3S GIBBERISH CHART")]
    sections, _ = detect_chapters(pages, outline)
    last = [s for s in sections if s.kind == "chapter"][-1]
    assert "GIBBERISH" not in section_body(last, pages)


def test_back_matter_capped_by_about_the_author():
    pages, outline = make_book(["Only Chapter"], pages_per_chapter=30)
    pages[-1].blocks = [heading("ABOUT THE AUTHOR"), body("The author lives on.")]
    sections, _ = detect_chapters(pages, outline)
    back = sections[-1]
    assert back.kind == "backmatter" and back.include is False
    chapter = next(s for s in sections if s.kind == "chapter")
    assert "author lives on" not in section_body(chapter, pages)


def test_classify_title():
    assert classify_title("Contents") == "frontmatter"
    assert classify_title("INDEX", late_in_book=True) == "backmatter"
    assert classify_title("About the Author") == "backmatter"
    assert classify_title("Conclusion") == "chapter"
    assert classify_title("10. Feminism and Ecology") == "chapter"


def test_find_back_matter_start_figure_run():
    pages = [page(i, [body()]) for i in range(20)]
    pages[18].flagged, pages[18].score = True, 0.2
    pages[19].blocks = [heading("ABOUT THE AUTHOR")]
    assert find_back_matter_start(pages, last_chapter_page=10) == 18


def test_mid_book_figure_does_not_start_back_matter():
    pages = [page(i, [body()]) for i in range(20)]
    pages[12].flagged, pages[12].score = True, 0.2
    assert find_back_matter_start(pages, last_chapter_page=2) == 20
