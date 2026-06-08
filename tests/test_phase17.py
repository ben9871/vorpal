"""Phase 17 — LLM-assisted OCR repair tests.

All tests use synthetic fixtures (no real PDF or LLM calls).
The manual-seeding workflow is fully exercised: find → seed → review → approve → apply.
"""

import json
from pathlib import Path

import pytest

from vorpal.extract.pagemodel import Block, Page
from vorpal.ocr_repair import (
    RepairProposal,
    apply_approved_repairs,
    find_repair_candidates,
    format_repair_review,
    load_proposals,
    merge_proposals,
    propose_repairs_llm,
    propose_repairs_seeded,
    save_proposals,
)


# ── fixtures ──────────────────────────────────────────────────────────────────


def _make_page(idx, blocks):
    """Create a scanned Page with the given (text, conf) block list."""
    raw_blocks = [Block(bbox=(0, 0, 100, 100), text=t, conf=c) for t, c in blocks]
    page_conf = sum(c for _, c in blocks) / len(blocks) if blocks else 1.0
    return Page(index=idx, kind="scanned", width=600, height=800,
                blocks=raw_blocks, conf=page_conf)


# ── RepairProposal round-trip ─────────────────────────────────────────────────


def test_proposal_to_dict():
    p = RepairProposal(page_idx=3, block_idx=1, original="OCR junk", proposed="Fixed",
                       conf=0.55, approved=None, method="manual_seed")
    d = p.to_dict()
    assert d["page_idx"] == 3
    assert d["approved"] is None
    assert d["method"] == "manual_seed"


def test_proposal_from_dict_round_trip():
    original = RepairProposal(page_idx=5, block_idx=2, original="bad text",
                              proposed="good text", conf=0.60, approved=True, method="llm")
    recovered = RepairProposal.from_dict(original.to_dict())
    assert recovered.page_idx == original.page_idx
    assert recovered.approved is True
    assert recovered.proposed == "good text"


def test_proposal_from_dict_defaults():
    p = RepairProposal.from_dict({"page_idx": 0, "block_idx": 0,
                                   "original": "x", "proposed": "y"})
    assert p.conf == 0.0
    assert p.approved is None
    assert p.method == "llm"


# ── find_repair_candidates ────────────────────────────────────────────────────


def test_find_candidates_returns_low_conf_blocks():
    pages = [
        _make_page(0, [("Good text here", 0.95), ("OCR junk xyx", 0.45)]),
        _make_page(1, [("Clean block", 0.90)]),
    ]
    cands = find_repair_candidates(pages, threshold=0.70)
    assert len(cands) == 1
    assert cands[0]["page_idx"] == 0
    assert cands[0]["block_idx"] == 1
    assert "OCR junk" in cands[0]["text"]


def test_find_candidates_filters_short_blocks():
    pages = [_make_page(0, [("ab", 0.30)])]  # too short (< 10 non-ws chars)
    cands = find_repair_candidates(pages, threshold=0.70)
    assert cands == []


def test_find_candidates_empty_pages():
    assert find_repair_candidates([], 0.70) == []


def test_find_candidates_all_clean():
    pages = [_make_page(0, [("Perfectly clean text here.", 0.95)])]
    cands = find_repair_candidates(pages, threshold=0.70)
    assert cands == []


def test_find_candidates_threshold_boundary():
    pages = [_make_page(0, [("Borderline block here", 0.70)])]
    cands = find_repair_candidates(pages, threshold=0.70)
    assert cands == []  # exactly at threshold → not a candidate


# ── propose_repairs_seeded ────────────────────────────────────────────────────


def test_seeded_proposals_match_candidates():
    pages = [_make_page(0, [("THE GASE FOR FEMINIST REV", 0.45)])]
    cands = find_repair_candidates(pages, threshold=0.70)
    seeds = [{"page_idx": 0, "block_idx": 0, "proposed": "THE CASE FOR FEMINIST REV"}]
    proposals = propose_repairs_seeded(cands, seeds)
    assert len(proposals) == 1
    assert proposals[0].proposed == "THE CASE FOR FEMINIST REV"
    assert proposals[0].method == "manual_seed"
    assert proposals[0].original == "THE GASE FOR FEMINIST REV"


def test_seeded_no_match_if_not_in_candidates():
    seeds = [{"page_idx": 99, "block_idx": 0, "proposed": "Doesn't exist"}]
    proposals = propose_repairs_seeded([], seeds)
    assert proposals == []


def test_seeded_only_matching_seeds():
    cands = [{"page_idx": 0, "block_idx": 0, "text": "Bad text here", "conf": 0.50},
             {"page_idx": 1, "block_idx": 2, "text": "More bad text", "conf": 0.55}]
    seeds = [{"page_idx": 0, "block_idx": 0, "proposed": "Good text here"}]
    proposals = propose_repairs_seeded(cands, seeds)
    assert len(proposals) == 1  # only the first candidate was seeded


# ── propose_repairs_llm ───────────────────────────────────────────────────────


def test_llm_raises_runtime_error_when_blocked(tmp_path):
    with pytest.raises(RuntimeError, match="blocked"):
        propose_repairs_llm([], [], tmp_path, "claude-haiku-4-5", "cli")


# ── manifest I/O ──────────────────────────────────────────────────────────────


class _FakeManifest:
    def __init__(self, tmp_path):
        self.path = tmp_path / "book.json"
        self.data = {}
        self._saved = False

    def save(self):
        self.path.write_text(json.dumps(self.data), encoding="utf-8")
        self._saved = True


def test_save_and_load_proposals(tmp_path):
    manifest = _FakeManifest(tmp_path)
    proposals = [
        RepairProposal(page_idx=0, block_idx=1, original="junk", proposed="fix",
                       conf=0.45, approved=None, method="manual_seed"),
    ]
    save_proposals(manifest, proposals)
    assert manifest._saved
    loaded = load_proposals(manifest)
    assert len(loaded) == 1
    assert loaded[0].original == "junk"
    assert loaded[0].proposed == "fix"


def test_load_proposals_empty_manifest():
    class _Empty:
        data = {}
    assert load_proposals(_Empty()) == []


# ── merge_proposals ───────────────────────────────────────────────────────────


def test_merge_does_not_overwrite_approved():
    existing = [RepairProposal(0, 0, "old", "fix", 0.5, approved=True, method="manual_seed")]
    new_p = [RepairProposal(0, 0, "old", "different fix", 0.5, approved=None)]
    merged = merge_proposals(existing, new_p)
    assert len(merged) == 1
    assert merged[0].approved is True
    assert merged[0].proposed == "fix"  # original preserved


def test_merge_adds_new_proposals():
    existing = [RepairProposal(0, 0, "old", "fix0", 0.5)]
    new_p = [RepairProposal(1, 0, "new", "fix1", 0.5)]
    merged = merge_proposals(existing, new_p)
    assert len(merged) == 2


def test_merge_deduplicates_pending():
    existing = [RepairProposal(0, 0, "old", "fix", 0.5, approved=None)]
    new_p = [RepairProposal(0, 0, "old", "other fix", 0.5, approved=None)]
    merged = merge_proposals(existing, new_p)
    assert len(merged) == 1


# ── apply_approved_repairs ────────────────────────────────────────────────────


def test_apply_patches_approved_block():
    pages = [_make_page(0, [("THE GASE FOR FEMINIST REV", 0.45), ("Good text", 0.90)])]
    proposals = [
        RepairProposal(0, 0, "THE GASE FOR FEMINIST REV", "THE CASE FOR FEMINIST REV",
                       0.45, approved=True, method="manual_seed")
    ]
    patched = apply_approved_repairs(pages, proposals)
    assert patched[0].blocks[0].text == "THE CASE FOR FEMINIST REV"
    assert patched[0].blocks[1].text == "Good text"   # untouched


def test_apply_does_not_patch_rejected():
    pages = [_make_page(0, [("OCR junk here", 0.45)])]
    proposals = [
        RepairProposal(0, 0, "OCR junk here", "Fixed text",
                       0.45, approved=False, method="manual_seed")
    ]
    patched = apply_approved_repairs(pages, proposals)
    assert patched[0].blocks[0].text == "OCR junk here"


def test_apply_does_not_patch_pending():
    pages = [_make_page(0, [("OCR junk here too", 0.45)])]
    proposals = [
        RepairProposal(0, 0, "OCR junk here too", "Fixed",
                       0.45, approved=None, method="manual_seed")
    ]
    patched = apply_approved_repairs(pages, proposals)
    assert patched[0].blocks[0].text == "OCR junk here too"


def test_apply_is_non_destructive_for_unaffected_pages():
    p0 = _make_page(0, [("Bad text here full", 0.45)])
    p1 = _make_page(1, [("Good text", 0.90)])
    proposals = [RepairProposal(0, 0, "Bad text here full", "Fixed", 0.45, approved=True)]
    patched = apply_approved_repairs([p0, p1], proposals)
    assert patched[1] is p1   # same object — untouched page


def test_apply_empty_proposals():
    pages = [_make_page(0, [("Some text", 0.90)])]
    patched = apply_approved_repairs(pages, [])
    assert patched[0] is pages[0]


def test_apply_no_approved():
    pages = [_make_page(0, [("Bad text here full", 0.45)])]
    proposals = [RepairProposal(0, 0, "Bad text here full", "Fix", 0.45, approved=None)]
    patched = apply_approved_repairs(pages, proposals)
    assert patched == pages


# ── format_repair_review ──────────────────────────────────────────────────────


def test_format_review_shows_diff():
    proposals = [RepairProposal(0, 0, "THE GASE", "THE CASE", 0.45)]
    output = format_repair_review(proposals)
    assert "- THE GASE" in output
    assert "+ THE CASE" in output
    assert "PENDING" in output


def test_format_review_empty():
    output = format_repair_review([])
    assert "No OCR repair proposals" in output


def test_format_review_counts():
    proposals = [
        RepairProposal(0, 0, "a", "b", 0.5, approved=True),
        RepairProposal(1, 0, "c", "d", 0.5, approved=False),
        RepairProposal(2, 0, "e", "f", 0.5, approved=None),
    ]
    output = format_repair_review(proposals)
    assert "1 approved" in output or "approved" in output
    assert "1 rejected" in output or "rejected" in output
    assert "1 pending" in output or "pending" in output


# ── CLI flags ─────────────────────────────────────────────────────────────────


def test_build_parser_has_repair_flag():
    from vorpal.cli import build_parser
    p = build_parser()
    args = p.parse_args(["build", "book.pdf", "--repair"])
    assert args.repair is True


def test_build_parser_repair_default_false():
    from vorpal.cli import build_parser
    p = build_parser()
    args = p.parse_args(["build", "book.pdf"])
    assert args.repair is False


def test_build_parser_repair_backend():
    from vorpal.cli import build_parser
    p = build_parser()
    args = p.parse_args(["build", "book.pdf", "--repair", "--repair-backend", "api"])
    assert args.repair_backend == "api"


def test_review_parser_has_repairs_flag():
    from vorpal.cli import build_parser
    p = build_parser()
    args = p.parse_args(["review", "book.pdf", "--repairs"])
    assert args.repairs is True
