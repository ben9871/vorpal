"""Segmentation stage: boilerplate removal → footnote separation → text
repair → chapter cascade → front/back-matter classification.

`segment_pages()` is the stage driver: pages.jsonl in, sections (for the
manifest) + per-section bodies + side-channel artifacts out.
"""

from dataclasses import dataclass, field

from .boilerplate import BoilerplateReport, remove_boilerplate
from .chapters import Section, detect_chapters, section_body
from .footnotes import FootnoteReport, separate_footnotes
from .frontmatter import classify_title, find_back_matter_start, is_figure_page
from .repair import RepairReport, repair_pages

__all__ = [
    "Section", "SegmentResult", "segment_pages",
    "remove_boilerplate", "separate_footnotes", "repair_pages",
    "detect_chapters", "section_body",
    "classify_title", "find_back_matter_start", "is_figure_page",
    "BoilerplateReport", "FootnoteReport", "RepairReport",
]


@dataclass
class SegmentResult:
    sections: list                      # [Section, ...]
    source: str                         # winning cascade rung
    bodies: dict = field(default_factory=dict)      # section id -> body text
    footnotes: list = field(default_factory=list)   # [{"page", "text"}, ...]
    qa: dict = field(default_factory=dict)


def segment_pages(pages, outline: list = None) -> "SegmentResult":
    """Run the full segmentation pipeline over extracted pages (mutates the
    page blocks in place — callers re-read pages.jsonl for a fresh copy)."""
    bp = remove_boilerplate(pages)
    fn = separate_footnotes(pages)
    rep = repair_pages(pages)
    sections, source = detect_chapters(pages, outline)
    bodies = {s.id: section_body(s, pages) for s in sections}
    return SegmentResult(
        sections=sections, source=source, bodies=bodies,
        footnotes=[{"page": f.page, "text": f.text} for f in fn.footnotes],
        qa={
            "boilerplate_clusters": bp.clusters,
            "header_lines_removed": bp.header_lines_removed,
            "page_number_lines_removed": bp.page_number_lines_removed,
            "footnotes_separated": len(fn.footnotes),
            "footnote_markers_stripped": fn.markers_stripped,
            "hyphens_joined": rep.hyphens_joined,
            "mojibake_tokens": rep.mojibake_tokens,
            "chapter_source": source,
        },
    )
