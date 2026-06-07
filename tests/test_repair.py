"""Unit tests for text repair (de-hyphenation, mojibake, reflow)."""

from audiobooker.extract.pagemodel import Block, Page
from audiobooker.segment.repair import (
    RepairReport,
    count_mojibake,
    dehyphenate,
    fix_mojibake,
    join_blocks,
    reflow_block,
    repair_pages,
)


def test_dehyphenate_joins_linebreak_hyphens():
    assert dehyphenate("the feminist revo-\nlution had begun") == \
        "the feminist revolution had begun"


def test_dehyphenate_keeps_proper_noun_compounds():
    assert dehyphenate("as Levi-\nStrauss observed") == "as Levi-Strauss observed"


def test_dehyphenate_counts_into_report():
    report = RepairReport()
    dehyphenate("effec-\ntive and Levi-\nStrauss", report)
    assert report.hyphens_joined == 1
    assert report.hyphens_kept == 1


def test_fix_mojibake_normalizes_quote_classes():
    assert fix_mojibake("“It’s here,” she said") == "\"It's here,\" she said"


def test_fix_mojibake_nfkc_ligatures():
    assert fix_mojibake("the ﬁrst conﬂict") == "the first conflict"


def test_mojibake_is_counted_not_rewritten():
    text = fix_mojibake("THE DIALECTIC OF SE¥s")
    assert "¥" in text                      # never silently "fixed"
    assert count_mojibake(text) == 1


def test_reflow_block_flows_hard_wrapped_lines():
    assert reflow_block("Sex class is so deep\nas to be invisible.") == \
        "Sex class is so deep as to be invisible."


def test_join_blocks_keeps_paragraph_boundaries():
    body = join_blocks(["First paragraph ends here.", "Second paragraph starts."])
    assert body == "First paragraph ends here.\n\nSecond paragraph starts."


def test_join_blocks_stitches_cross_page_continuation():
    body = join_blocks(["The movement was gaining", "momentum in every state."])
    assert body == "The movement was gaining momentum in every state."


def test_join_blocks_heals_break_point_hyphen():
    body = join_blocks(["the coming revo-", "lution was foreshadowed"])
    assert body == "the coming revolution was foreshadowed"


def test_repair_pages_end_to_end():
    page = Page(index=0, kind="scanned", width=600, height=800, blocks=[
        Block(bbox=(50, 100, 550, 200),
              text="The “quoted” line wraps\nacross a hyphen-\nated break."),
    ])
    report = repair_pages([page])
    assert page.blocks[0].text == 'The "quoted" line wraps across a hyphenated break.'
    assert report.hyphens_joined == 1
