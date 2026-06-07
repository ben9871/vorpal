"""Front/back-matter classification.

Sections that exist but should not be narrated by default — copyright page,
printing history, contents, index, "about the author" — are *classified and
visible* in the review table with `include: false`, never silently dropped
(docs/01-audit.md §2's <80-word silent skip is the failure this replaces).
"""

import re

# Titles that identify non-narrated apparatus. Matched against a normalized
# (uppercased, de-punctuated) title.
_FRONT_TITLE_RE = re.compile(
    r"^(CONTENTS|TABLE OF CONTENTS|COPYRIGHT|TITLE PAGE|HALF TITLE|"
    r"LIST OF (TABLES|FIGURES|ILLUSTRATIONS)|PRINTING HISTORY|EPIGRAPH)\b"
)
_BACK_TITLE_RE = re.compile(
    r"^(INDEX|BIBLIOGRAPHY|NOTES|GLOSSARY|ABOUT THE AUTHOR|"
    r"ALSO BY\b|ACKNOWLEDG)"
)
# Flagged pages whose composite QA score (OCR confidence × text quality) is
# below this are figures/diagrams: prose pages score 0.9+, the Firestone
# dialectic chart scores 0.27.
_FIGURE_SCORE = 0.5


def _norm(title: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^A-Za-z ]+", " ", title.upper())).strip()


def classify_title(title: str, late_in_book: bool = False) -> str:
    """'frontmatter' | 'backmatter' | 'chapter' from a section title."""
    norm = _norm(title)
    if _BACK_TITLE_RE.match(norm):
        return "backmatter"
    if _FRONT_TITLE_RE.match(norm):
        # an "epigraph"/"contents" title in the last pages is still apparatus,
        # but acknowledgments etc. at the front are front matter
        return "backmatter" if late_in_book else "frontmatter"
    return "chapter"


def is_figure_page(page) -> bool:
    """A page extraction flagged with a very low QA score is a figure or
    diagram (e.g. the Firestone dialectic charts), not prose."""
    return page.flagged and page.score < _FIGURE_SCORE


def _has_back_title(page) -> bool:
    for b in page.blocks[:4]:
        first = b.text.strip().split("\n", 1)[0]
        if _BACK_TITLE_RE.match(_norm(first)):
            return True
    return False


def find_back_matter_start(pages, last_chapter_page: int) -> int:
    """First page index after `last_chapter_page` where back matter begins.

    Two triggers, both restricted to the book's tail (last ~15%): a
    back-matter heading block, or a figure page — the latter only when what
    follows is also back matter / end of book, so a mid-conclusion diagram
    can never chop the chapter. Returns one past the last page when none."""
    end = pages[-1].index + 1 if pages else 0
    tail_start = max(last_chapter_page + 1, int(end * 0.85))
    candidates = [p for p in pages if p.index >= tail_start]
    for i, page in enumerate(candidates):
        if _has_back_title(page):
            return page.index
        if is_figure_page(page):
            rest = candidates[i + 1:i + 3]
            if not rest or any(_has_back_title(p) or is_figure_page(p) for p in rest):
                return page.index
    return end
