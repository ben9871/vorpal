"""Unit tests for cross-page boilerplate (header/footer/page-number) removal."""

from vorpal.extract.pagemodel import Block, Page
from vorpal.segment.boilerplate import remove_boilerplate

W, H = 600, 800
TOP = 20       # well inside the 12% top band (96)
BOTTOM = 770   # inside the 10% bottom band (>720)
BODY = 300     # mid-page


def make_page(index, blocks):
    return Page(index=index, kind="scanned", width=W, height=H, blocks=blocks)


def header_block(text, y=TOP):
    return Block(bbox=(50, y, 400, y + 12), text=text)


def body_block(text, y=BODY):
    return Block(bbox=(50, y, 550, y + 200), text=text)


def make_book(n_pages=10, header_fmt="{n} THE GREAT BOOK"):
    """A book whose every page has a running header and a body block."""
    return [
        make_page(i, [
            header_block(header_fmt.format(n=i + 10)),
            body_block(f"Body prose of page {i}, which continues for a while."),
        ])
        for i in range(n_pages)
    ]


def all_text(pages):
    return "\n".join(b.text for p in pages for b in p.blocks)


def test_repeating_header_removed_everywhere():
    pages = make_book()
    report = remove_boilerplate(pages)
    assert "THE GREAT BOOK" not in all_text(pages)
    assert "Body prose of page 3" in all_text(pages)
    assert report.header_lines_removed == 10
    assert report.clusters and report.clusters[0]["pages"] == 10


def test_ocr_noise_variants_join_the_cluster():
    pages = make_book()
    # one page's header is OCR-mangled (SE¥-style noise)
    pages[4].blocks[0].text = "14 THE GREAT BO0K¥"
    remove_boilerplate(pages)
    assert "GREAT" not in all_text(pages)


def test_fused_header_strips_first_line_only():
    pages = make_book()
    # header fused into a tall body block, as seen on the Firestone scan
    pages[2].blocks = [Block(
        bbox=(50, TOP, 550, 500),
        text="12 THE GREAT BOOK\nActual body text that must survive.",
    )]
    remove_boilerplate(pages)
    text = all_text(pages)
    assert "THE GREAT BOOK" not in text
    assert "Actual body text that must survive." in text


def test_page_number_lines_removed_in_bands_only():
    pages = make_book()
    for i, p in enumerate(pages):
        p.blocks.append(Block(bbox=(280, BOTTOM, 320, BOTTOM + 10), text=str(i + 10)))
    # a bare number mid-page is content (e.g. a quoted figure), not a folio
    pages[5].blocks.append(Block(bbox=(280, BODY, 320, BODY + 10), text="1968"))
    report = remove_boilerplate(pages)
    assert report.page_number_lines_removed == 10
    assert "1968" in all_text(pages)


def test_heading_below_band_survives_even_when_text_matches_header():
    # Firestone: chapter 1 title == book title == running-header text.
    pages = make_book(header_fmt="{n} THE GREAT BOOK")
    pages[0].blocks.insert(1, Block(bbox=(50, 120, 400, 135), text="THE GREAT BOOK"))
    remove_boilerplate(pages)
    # the mid-page heading survives; the band copies are gone
    assert all_text(pages).count("THE GREAT BOOK") == 1


def test_non_repeating_band_text_is_kept():
    # body text that merely starts high on the page is not boilerplate
    pages = make_book()
    pages[7].blocks.append(Block(
        bbox=(50, 40, 550, 300),
        text="continuation of a paragraph from the previous page",
    ))
    remove_boilerplate(pages)
    assert "continuation of a paragraph" in all_text(pages)


def test_emptied_blocks_are_dropped():
    pages = make_book()
    report = remove_boilerplate(pages)
    assert report.blocks_dropped == 10
    assert all(len(p.blocks) == 1 for p in pages)


def test_short_book_below_min_pages_is_untouched():
    pages = make_book(n_pages=2)
    report = remove_boilerplate(pages)
    assert not report.clusters
    assert "THE GREAT BOOK" in all_text(pages)
