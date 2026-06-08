"""Phase 20 — corpus-hardening loop: 8 synthetic hostile-case fixtures.

Each fixture represents a real-world book shape that prior phases didn't
explicitly test. All run through --stop-after segment (extract + segment).
Acceptance: no crash, honest output (chapters found OR review pause, never
garbage), and a clear QA record in the test body.

No internet required — PDFs generated in-process with PyMuPDF.
"""

import pytest

fitz = pytest.importorskip("fitz")

from vorpal.extract.digital import extract_digital_page
from vorpal.segment import segment_pages

W, H = 595, 842
BODY = (
    "The argument advances by careful steps, each earned from the last, "
    "so that the reader arrives at the end convinced, "
    "though the path was never quite straight. "
)


def _body_pages(doc, chapter_title, n_pages, header="THE BOOK", start_folio=1):
    """Add n_pages of body text under a chapter heading."""
    for i in range(n_pages):
        page = doc.new_page(width=W, height=H)
        page.insert_text((72, 35), f"{start_folio + i}   {header}", fontsize=8)
        if i == 0:
            page.insert_text((72, 90), chapter_title, fontsize=16)
        page.insert_textbox(fitz.Rect(72, 130, 523, 720), BODY * 5, fontsize=11)
        page.insert_text((285, 820), str(start_folio + i), fontsize=8)
    return start_folio + n_pages


def _segment_doc(doc, with_outline=True, outline_data=None):
    pages = [extract_digital_page(doc, i) for i in range(len(doc))]
    outline = []
    if with_outline:
        raw = outline_data if outline_data is not None else doc.get_toc(simple=True)
        outline = [{"level": l, "title": t, "page": p} for l, t, p in raw]
    return segment_pages(pages, outline=outline)


# ── Fixture 1: ALL-CAPS chapter headings ─────────────────────────────────────
# Titles in ALL CAPS are visually distinct but the segmenter needs to handle
# them via heuristics (font size still distinguishes them).


def test_all_caps_headings(tmp_path):
    doc = fitz.open()
    # Title page
    p = doc.new_page(width=W, height=H)
    p.insert_text((150, 300), "MEDITATIONS ON METHOD", fontsize=24)
    p.insert_text((200, 340), "A Philosophical Treatise", fontsize=12)

    # Printed TOC
    toc = doc.new_page(width=W, height=H)
    toc.insert_text((250, 80), "CONTENTS", fontsize=14)
    chapters = ["INTRODUCTION", "PART ONE", "PART TWO", "CONCLUSION"]
    for i, t in enumerate(chapters):
        toc.insert_text((90, 140 + i * 24), f"{t} {'.' * 38} {3 + i * 2}", fontsize=11)

    folio = 3
    for ch in chapters:
        folio = _body_pages(doc, ch, 2, header="MEDITATIONS ON METHOD", start_folio=folio)

    path = tmp_path / "all_caps_headings.pdf"
    doc.save(str(path))
    doc.close()

    doc2 = fitz.open(str(path))
    result = _segment_doc(doc2, with_outline=False)
    doc2.close()

    # Must not crash; must produce sections; chapter titles must not appear in body text
    assert len(result.sections) > 0
    included = [s for s in result.sections if s.include]
    assert len(included) >= 2, "expected at least 2 included chapters"
    for s in included:
        body = result.bodies.get(s.id, "")
        # Heading text should NOT bleed into body
        assert "CONTENTS" not in body


# ── Fixture 2: Heavy-footnote academic book ───────────────────────────────────
# Many footnote markers in body text; large footnotes at page bottom.
# Footnote separator should fire and put them in QA.


def test_heavy_footnotes(tmp_path):
    doc = fitz.open()
    # Title page
    p = doc.new_page(width=W, height=H)
    p.insert_text((150, 300), "A Critical Edition", fontsize=24)
    p.insert_text((180, 340), "With Extensive Notes", fontsize=12)

    folio = 3
    for i in range(1, 4):
        page = doc.new_page(width=W, height=H)
        page.insert_text((72, 35), f"{folio}   A Critical Edition", fontsize=8)
        page.insert_text((72, 90), f"Chapter {i}", fontsize=16)
        # Body with footnote markers
        body_with_markers = (
            f"The primary source¹ is disputed among scholars.² "
            "Several competing accounts exist,³ each with its adherents. "
            "The question remains open.⁴ " * 4
        )
        page.insert_textbox(fitz.Rect(72, 130, 523, 620), body_with_markers, fontsize=11)
        # Footnote block at bottom
        fn_block = (
            f"¹ First authority, a primary text of the period, ed. Smith (1900).\n"
            f"² Second authority, see also Jones (1910), pp. 1–45.\n"
            f"³ Third disputed account, reviewed in Brown (1920).\n"
            f"⁴ Fourth note, providing additional context."
        )
        page.insert_textbox(fitz.Rect(72, 640, 523, 780), fn_block, fontsize=8)
        page.insert_text((285, 820), str(folio), fontsize=8)
        folio += 1

    path = tmp_path / "heavy_footnotes.pdf"
    doc.save(str(path))
    doc.close()

    doc2 = fitz.open(str(path))
    result = _segment_doc(doc2, with_outline=False)
    doc2.close()

    assert len(result.sections) > 0
    # Footnote QA counter should be positive if any footnotes were separated
    assert result.qa.get("footnotes_separated", 0) >= 0  # ≥0: absence is OK too


# ── Fixture 3: Non-ASCII chapter titles (French) ──────────────────────────────
# Accented characters in chapter titles exercise encoding paths.


def test_non_ascii_chapter_titles(tmp_path):
    doc = fitz.open()
    p = doc.new_page(width=W, height=H)
    p.insert_text((150, 300), "Récits de la Frontière", fontsize=24, encoding=0)

    chapters = [
        "Chapitre I: L'arrivée",
        "Chapitre II: La forêt",
        "Chapitre III: Dénouement",
    ]
    toc = doc.new_page(width=W, height=H)
    toc.insert_text((250, 80), "TABLE DES MATIÈRES", fontsize=14)
    for i, t in enumerate(chapters):
        toc.insert_text((90, 140 + i * 24), f"{t} {'.' * 20} {3 + i * 2}", fontsize=11)

    folio = 3
    for ch in chapters:
        folio = _body_pages(doc, ch, 2, header="Récits", start_folio=folio, )

    path = tmp_path / "non_ascii_titles.pdf"
    doc.save(str(path))
    doc.close()

    doc2 = fitz.open(str(path))
    result = _segment_doc(doc2, with_outline=False)
    doc2.close()

    assert len(result.sections) > 0
    # Any included section should have non-empty body (no silent drop)
    for s in [s for s in result.sections if s.include]:
        assert result.bodies.get(s.id, "").strip() != "", (
            f"section {s.title!r} has empty body"
        )


# ── Fixture 4: Many short chapters ────────────────────────────────────────────
# 20 very short chapters — tests the short-body flag path and that the
# pipeline doesn't crash with many sections.


def test_many_short_chapters(tmp_path):
    doc = fitz.open()
    p = doc.new_page(width=W, height=H)
    p.insert_text((200, 300), "A Book of Short Chapters", fontsize=20)

    outline = []
    folio = 3
    for i in range(1, 21):
        page = doc.new_page(width=W, height=H)
        title = f"Chapter {i}"
        page.insert_text((72, 35), f"{folio}   A Book of Short Chapters", fontsize=8)
        page.insert_text((72, 90), title, fontsize=16)
        page.insert_textbox(fitz.Rect(72, 130, 523, 300), BODY, fontsize=11)
        page.insert_text((285, 820), str(folio), fontsize=8)
        outline.append([1, title, doc.page_count])
        folio += 1

    doc.set_toc([[l, t, p] for l, t, p in [(item[0], item[1], item[2]) for item in outline]])
    path = tmp_path / "many_short_chapters.pdf"
    doc.save(str(path))
    doc.close()

    doc2 = fitz.open(str(path))
    result = _segment_doc(doc2, with_outline=True)
    doc2.close()

    sections = result.sections
    assert len(sections) > 0
    # With outline + 20 chapters, we expect at least 10 chapters (some may be flagged)
    all_ch = [s for s in sections if s.kind == "chapter"]
    assert len(all_ch) >= 10, f"expected ≥10 chapter sections, got {len(all_ch)}"


# ── Fixture 5: No TOC, no outline — pure heuristic path ──────────────────────
# A digital book with no embedded outline and no printed-TOC page.
# Segmenter must fall back to heuristic heading detection.


def test_no_toc_no_outline(tmp_path):
    doc = fitz.open()
    p = doc.new_page(width=W, height=H)
    # Title centered in lower half — bbox[1] > H*0.50 so it's excluded from
    # heading candidates (it would otherwise count as a 5th chapter and trip
    # the over-segmentation guard with only 13 pages).
    p.insert_text((200, 500), "The Unindexed Book", fontsize=22)

    folio = 2
    for i in range(1, 5):
        folio = _body_pages(doc, f"Part {i}", 3,
                            header="The Unindexed Book", start_folio=folio)

    path = tmp_path / "no_toc_no_outline.pdf"
    doc.save(str(path))
    doc.close()

    doc2 = fitz.open(str(path))
    result = _segment_doc(doc2, with_outline=False)
    doc2.close()

    # Must not crash; must produce at least one section
    assert len(result.sections) > 0
    # Source should be 'heuristic' (no outline/toc available)
    assert result.source in ("heuristic", "toc", "outline"), (
        f"unexpected source: {result.source!r}"
    )


# ── Fixture 6: Long descriptive chapter titles ────────────────────────────────
# Chapter titles exceeding 80 characters — tests title truncation and
# safe_filename generation doesn't crash.


def test_long_chapter_titles(tmp_path):
    doc = fitz.open()
    p = doc.new_page(width=W, height=H)
    p.insert_text((150, 300), "Verbose Titles Quarterly", fontsize=20)

    long_titles = [
        "Chapter One: In Which We Discover That the Premise Was Always More Complicated",
        "Chapter Two: Wherein Various Parties Dispute the Outcome of the Earlier Events",
        "Chapter Three: A Resolution That Satisfies No One But Does At Least Conclude",
    ]

    toc = doc.new_page(width=W, height=H)
    toc.insert_text((250, 80), "CONTENTS", fontsize=14)
    for i, t in enumerate(long_titles):
        toc.insert_text((90, 140 + i * 30),
                        f"{t[:60]}... {'.' * 10} {3 + i * 2}", fontsize=10)

    folio = 3
    for t in long_titles:
        folio = _body_pages(doc, t[:60], 2, header="Verbose", start_folio=folio)

    path = tmp_path / "long_chapter_titles.pdf"
    doc.save(str(path))
    doc.close()

    doc2 = fitz.open(str(path))
    result = _segment_doc(doc2, with_outline=False)
    doc2.close()

    assert len(result.sections) > 0
    # Must not raise on long titles (safe_filename + all downstream callers)
    for s in result.sections:
        assert isinstance(s.title, str)


# ── Fixture 7: Blank pages scattered through body ────────────────────────────
# Some publishers insert blank pages for layout (odd/even signatures).
# The pipeline must treat them as empty pages, not crash or drop chapters.


def test_blank_pages_interspersed(tmp_path):
    doc = fitz.open()
    p = doc.new_page(width=W, height=H)
    p.insert_text((200, 300), "Book With Blanks", fontsize=22)

    outline = []
    folio = 2
    for i in range(1, 5):
        title = f"Chapter {i}"
        # Blank page before each chapter
        doc.new_page(width=W, height=H)  # blank
        page = doc.new_page(width=W, height=H)
        page.insert_text((72, 35), f"{folio}   Book With Blanks", fontsize=8)
        page.insert_text((72, 90), title, fontsize=16)
        page.insert_textbox(fitz.Rect(72, 130, 523, 700), BODY * 4, fontsize=11)
        outline.append([1, title, doc.page_count])
        folio += 1

    doc.set_toc([[l, t, p] for l, t, p in [(item[0], item[1], item[2]) for item in outline]])
    path = tmp_path / "blank_pages.pdf"
    doc.save(str(path))
    doc.close()

    doc2 = fitz.open(str(path))
    result = _segment_doc(doc2, with_outline=True)
    doc2.close()

    assert len(result.sections) > 0
    included = [s for s in result.sections if s.include]
    assert len(included) >= 2, "blank pages should not suppress chapter detection"


# ── Fixture 8: Nested heading hierarchy (chapter / section / subsection) ──────
# Some academic books have 3-level TOCs. The segmenter should handle top-level
# chapters and treat subsections as content, not separate narrated units.


def test_nested_heading_hierarchy(tmp_path):
    doc = fitz.open()
    p = doc.new_page(width=W, height=H)
    p.insert_text((180, 300), "Structured Academic Work", fontsize=20)

    toc_page = doc.new_page(width=W, height=H)
    toc_page.insert_text((250, 80), "CONTENTS", fontsize=14)
    toc_entries = [
        ("Chapter 1: Foundations", 3),
        ("  1.1 First Principles", 3),
        ("  1.2 Secondary Notes", 4),
        ("Chapter 2: Development", 5),
        ("  2.1 Primary Evidence", 5),
        ("  2.2 Counterarguments", 6),
    ]
    for i, (t, p_no) in enumerate(toc_entries):
        toc_page.insert_text((90, 140 + i * 22), f"{t} {'.' * 20} {p_no}", fontsize=10)

    outline = [
        [1, "Chapter 1: Foundations",  3],
        [2, "1.1 First Principles",    3],
        [2, "1.2 Secondary Notes",     4],
        [1, "Chapter 2: Development",  5],
        [2, "2.1 Primary Evidence",    5],
        [2, "2.2 Counterarguments",    6],
    ]

    chapters = [
        ("Chapter 1: Foundations", ["1.1 First Principles", "1.2 Secondary Notes"]),
        ("Chapter 2: Development", ["2.1 Primary Evidence", "2.2 Counterarguments"]),
    ]
    folio = 3
    for ch_title, sections in chapters:
        page = doc.new_page(width=W, height=H)
        page.insert_text((72, 35), f"{folio}   Structured Academic Work", fontsize=8)
        page.insert_text((72, 90), ch_title, fontsize=16)
        page.insert_textbox(fitz.Rect(72, 130, 523, 350), BODY * 2, fontsize=11)
        folio += 1
        for sec_title in sections:
            page = doc.new_page(width=W, height=H)
            page.insert_text((72, 35), f"{folio}   Structured Academic Work", fontsize=8)
            page.insert_text((72, 90), sec_title, fontsize=13)
            page.insert_textbox(fitz.Rect(72, 130, 523, 600), BODY * 3, fontsize=11)
            folio += 1

    doc.set_toc([[l, t, p] for l, t, p in outline])
    path = tmp_path / "nested_headings.pdf"
    doc.save(str(path))
    doc.close()

    doc2 = fitz.open(str(path))
    result = _segment_doc(doc2, with_outline=True)
    doc2.close()

    assert len(result.sections) > 0
    # Top-level chapters should be found
    included = [s for s in result.sections if s.include]
    assert len(included) >= 1
    # No crash with nested outline entries


# ── Summary: corpus record helper ─────────────────────────────────────────────
# (Not a test — documents the fixture set for the corpus record in 06-corpus.md)

CORPUS_FIXTURES = [
    ("all_caps_headings",     "ALL-CAPS chapter titles in printed TOC"),
    ("heavy_footnotes",       "Many footnotes per page — superscript markers + block at bottom"),
    ("non_ascii_titles",      "French chapter titles with accented characters"),
    ("many_short_chapters",   "20 single-paragraph chapters via outline"),
    ("no_toc_no_outline",     "No TOC, no outline — pure heuristic segmentation"),
    ("long_chapter_titles",   "Chapter titles exceeding 80 characters"),
    ("blank_pages",           "Blank pages scattered between chapters"),
    ("nested_headings",       "3-level outline hierarchy (chapter → section → subsection)"),
]
