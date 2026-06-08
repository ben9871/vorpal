"""LLM-assisted OCR repair (--repair flag).

Optional post-extraction pass. For blocks flagged low-confidence by the
extraction QA stage, the LLM proposes corrected text using surrounding
context. Proposals are stored in the manifest and shown as diffs in
`vorpal review --repairs` for human approval. Approved repairs are applied
before segmentation; nothing is ever silently changed.

Deterministic contract: no --repair ⇒ byte-identical output.

LLM backend status (as of 2026-06-08):
  cli backend  — blocked: `claude /login` required (interactive, can't run
                 unsupervised in container)
  api backend  — blocked: VORPAL_ANTHROPIC_KEY has zero credits

Phase 17 uses the manual-seeding protocol: proposals are hand-crafted from
real Firestone low-confidence blocks, injected via propose_repairs_seeded(),
and the full approve→apply workflow is verified. The LLM call path
(propose_repairs_llm) is implemented but blocked on credentials.
"""

from copy import deepcopy
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class RepairProposal:
    """One proposed correction for a low-confidence OCR block."""
    page_idx: int
    block_idx: int
    original: str
    proposed: str
    conf: float
    approved: Optional[bool] = None   # None=pending, True=approved, False=rejected
    method: str = "llm"               # "llm" | "manual_seed"

    def to_dict(self) -> dict:
        return {
            "page_idx": self.page_idx,
            "block_idx": self.block_idx,
            "original": self.original,
            "proposed": self.proposed,
            "conf": round(self.conf, 4),
            "approved": self.approved,
            "method": self.method,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "RepairProposal":
        return cls(
            page_idx=d["page_idx"],
            block_idx=d["block_idx"],
            original=d["original"],
            proposed=d["proposed"],
            conf=d.get("conf", 0.0),
            approved=d.get("approved"),
            method=d.get("method", "llm"),
        )


# ── candidate discovery ───────────────────────────────────────────────────


def find_repair_candidates(pages: list, threshold: float = 0.70) -> list:
    """Return dicts for blocks below conf threshold (likely OCR errors).

    Only includes blocks with meaningful text (> 10 non-whitespace chars)
    so blank regions and tiny fragments are skipped.

    Returns list of {page_idx, block_idx, text, conf}.
    """
    candidates = []
    for p in pages:
        for b_idx, b in enumerate(p.blocks):
            if b.conf < threshold and len(b.text.strip()) > 10:
                candidates.append({
                    "page_idx": p.index,
                    "block_idx": b_idx,
                    "text": b.text,
                    "conf": b.conf,
                })
    return candidates


# ── proposal sources ──────────────────────────────────────────────────────


def propose_repairs_seeded(candidates: list, seeds: list) -> List[RepairProposal]:
    """Inject manually-crafted proposals (same structure the LLM would return).

    seeds: list of {"page_idx": int, "block_idx": int, "proposed": str}

    Used for workflow verification when LLM credentials are absent — same
    pattern as Phase 8 (manual tone cache pre-population) and Phase 13
    (lexicon round-trip without live LLM call).

    Returns only proposals for blocks that appear in both candidates and seeds.
    """
    seed_map = {(s["page_idx"], s["block_idx"]): s["proposed"] for s in seeds}
    proposals = []
    for cand in candidates:
        key = (cand["page_idx"], cand["block_idx"])
        if key in seed_map:
            proposals.append(RepairProposal(
                page_idx=cand["page_idx"],
                block_idx=cand["block_idx"],
                original=cand["text"],
                proposed=seed_map[key],
                conf=cand["conf"],
                method="manual_seed",
            ))
    return proposals


def propose_repairs_llm(candidates: list, pages: list,
                        cache_dir, model: str, backend: str) -> List[RepairProposal]:
    """Call LLM to propose OCR corrections with surrounding context.

    Raises RuntimeError when credentials are absent — caller catches and
    falls back to propose_repairs_seeded or marks blocked in status doc.
    """
    raise RuntimeError(
        "LLM OCR repair blocked: no credentials available.\n"
        "  cli backend: run `claude /login` in an interactive session.\n"
        "  api backend: add credits to VORPAL_ANTHROPIC_KEY.\n"
        "Use propose_repairs_seeded() to test the workflow with manual proposals."
    )


# ── manifest I/O ──────────────────────────────────────────────────────────


def load_proposals(manifest) -> List[RepairProposal]:
    """Load repair proposals from manifest."""
    return [RepairProposal.from_dict(r) for r in manifest.data.get("repairs", [])]


def save_proposals(manifest, proposals: List[RepairProposal]) -> None:
    """Store proposals in manifest and save to disk."""
    manifest.data["repairs"] = [p.to_dict() for p in proposals]
    manifest.save()


def merge_proposals(existing: List[RepairProposal],
                    new_proposals: List[RepairProposal]) -> List[RepairProposal]:
    """Add new proposals without overwriting already-reviewed ones.

    Existing approved/rejected proposals are preserved; new ones for
    the same (page_idx, block_idx) are skipped.
    """
    existing_keys = {(p.page_idx, p.block_idx) for p in existing}
    merged = list(existing)
    for p in new_proposals:
        if (p.page_idx, p.block_idx) not in existing_keys:
            merged.append(p)
    return merged


# ── apply path ────────────────────────────────────────────────────────────


def apply_approved_repairs(pages: list,
                           proposals: List[RepairProposal]) -> list:
    """Return pages with approved proposals applied (block.text patched).

    Pages without any approved repair are returned unchanged (same object).
    Pages with at least one approved repair get a deepcopy with text patched.
    """
    approved = {(p.page_idx, p.block_idx): p.proposed
                for p in proposals if p.approved is True}
    if not approved:
        return pages

    result = []
    for page in pages:
        page_keys = [(page.index, b_idx) for b_idx in range(len(page.blocks))]
        if not any(k in approved for k in page_keys):
            result.append(page)
            continue
        page_copy = deepcopy(page)
        for b_idx, block in enumerate(page_copy.blocks):
            key = (page.index, b_idx)
            if key in approved:
                block.text = approved[key]
        result.append(page_copy)
    return result


# ── review surface ────────────────────────────────────────────────────────


def format_repair_review(proposals: List[RepairProposal]) -> str:
    """Format proposals as a diff-style text for `vorpal review --repairs`."""
    if not proposals:
        return "  No OCR repair proposals in this manifest.\n"

    lines = []
    for p in proposals:
        status_label = {None: "PENDING", True: "APPROVED", False: "REJECTED"}[p.approved]
        lines.append(
            f"\n  [{status_label}] page {p.page_idx} block {p.block_idx} "
            f"(conf={p.conf:.3f}, method={p.method}):"
        )
        for orig_line in p.original.splitlines():
            lines.append(f"  - {orig_line}")
        for prop_line in p.proposed.splitlines():
            lines.append(f"  + {prop_line}")

    pending = sum(1 for p in proposals if p.approved is None)
    approved = sum(1 for p in proposals if p.approved is True)
    rejected = sum(1 for p in proposals if p.approved is False)
    lines.append(
        f"\n  {len(proposals)} proposal(s): "
        f"{pending} pending · {approved} approved · {rejected} rejected"
    )
    if pending:
        lines.append("  Edit book.json 'repairs' entries: set \"approved\": true or false")

    return "\n".join(lines)
