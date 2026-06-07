"""Running header/footer/page-number removal by cross-page clustering.

A line repeating on many pages at the same vertical band (top/bottom), with
~constant text modulo digits, is a running header/footer — removed everywhere,
robust to OCR noise (`SE¥s` ≈ `SEX` under Levenshtein). Standalone page-number
lines in the bands are removed categorically. This replaces v0's per-line
regex guessing (docs/03-architecture.md stage 3.1; kills the 21 surviving
`THE DIALECTIC OF SE'` headers and their fake chapters).

Geometry notes that shaped the logic (verified on the Firestone scan):
- Headers are often OCR'd *fused* into a tall body block as its first line,
  so removal is line-level within band blocks, never block-level only.
- Chapter headings print *below* the top band (drop folio), so band-limiting
  is what protects "THE DIALECTIC OF SEX" the chapter title from
  "24 THE DIALECTIC OF SEX" the running header.
- Two-page-spread scans put one header per column; both land in the top band.
"""

import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz

# Fractions of page height treated as the header/footer bands.
TOP_BAND = 0.12
BOTTOM_BAND = 0.10
# fuzz.ratio threshold for a line to join / match a cluster (OCR-noise tolerant).
SIMILARITY = 80
# A cluster is boilerplate when it appears on at least max(MIN_PAGES,
# MIN_PAGE_FRAC * n_pages) distinct pages.
MIN_PAGES = 4
MIN_PAGE_FRAC = 0.04
# Candidate lines longer than this (normalized) are body text that merely
# starts/ends in a band, not running headers — never clustered.
MAX_HEADER_CHARS = 60
# Standalone page number, tolerating OCR junk around it: "30.", "| 42", ": 4".
PAGE_NUMBER_RE = re.compile(r"^[\W_]{0,3}\d{1,4}[\W_]{0,3}$")


def _normalize(line: str) -> str:
    """Clustering key: digits → '#' (page numbers vary), whitespace collapsed."""
    return re.sub(r"\s+", " ", re.sub(r"\d+", "#", line)).strip()


@dataclass
class _Cluster:
    rep: str                       # representative normalized text
    pages: set = field(default_factory=set)
    count: int = 0

    def sample(self) -> str:
        return self.rep


@dataclass
class BoilerplateReport:
    clusters: list = field(default_factory=list)  # [{"sample", "pages", "count", "band"}]
    header_lines_removed: int = 0
    page_number_lines_removed: int = 0
    blocks_dropped: int = 0


def _band_candidates(page) -> list:
    """Yield (block, line_idx, line) for lines plausibly in the top/bottom band.

    Block bboxes are all we have (no per-line geometry), so: a block fully
    inside a band contributes all its lines; a tall block *starting* in the
    top band contributes its first line; one *ending* in the bottom band, its
    last line.
    """
    top_y = page.height * TOP_BAND
    bot_y = page.height * (1 - BOTTOM_BAND)
    out = []
    for block in page.blocks:
        x0, y0, x1, y1 = block.bbox
        lines = block.text.split("\n")
        if y0 < top_y:                       # starts in the top band
            if y1 <= top_y:                  # fully inside: every line
                out.extend((block, i, l, "top") for i, l in enumerate(lines))
            else:                            # fused with body: first line only
                out.append((block, 0, lines[0], "top"))
        elif y1 > bot_y:                     # ends in the bottom band
            if y0 >= bot_y:
                out.extend((block, i, l, "bottom") for i, l in enumerate(lines))
            else:
                out.append((block, len(lines) - 1, lines[-1], "bottom"))
    return out


def _find_clusters(pages) -> dict:
    """Greedy fuzzy clustering of band lines → {band: [_Cluster, ...]}."""
    clusters = {"top": [], "bottom": []}
    for page in pages:
        for _, _, line, band in _band_candidates(page):
            norm = _normalize(line)
            if not norm or len(norm) > MAX_HEADER_CHARS:
                continue
            if len(norm) < 4 or PAGE_NUMBER_RE.match(line.strip()):
                continue                     # page numbers handled categorically
            best, best_score = None, 0
            for c in clusters[band]:
                score = fuzz.ratio(norm, c.rep)
                if score >= SIMILARITY and score > best_score:
                    best, best_score = c, score
            if best is None:
                best = _Cluster(rep=norm)
                clusters[band].append(best)
            best.pages.add(page.index)
            best.count += 1
    return clusters


def remove_boilerplate(pages) -> BoilerplateReport:
    """Strip running headers/footers and page-number lines from `pages`.

    Mutates the Block texts in place (dropping emptied blocks) and returns a
    report of what was removed, for the QA trail.
    """
    n_pages = max(len(pages), 1)
    min_pages = max(MIN_PAGES, round(MIN_PAGE_FRAC * n_pages))
    clusters = _find_clusters(pages)
    boiler = {
        band: [c for c in cs if len(c.pages) >= min_pages]
        for band, cs in clusters.items()
    }

    report = BoilerplateReport(clusters=[
        {"sample": c.sample(), "pages": len(c.pages), "count": c.count, "band": band}
        for band, cs in boiler.items() for c in cs
    ])

    def is_boiler(line: str, band: str) -> bool:
        norm = _normalize(line)
        return any(fuzz.ratio(norm, c.rep) >= SIMILARITY for c in boiler[band])

    for page in pages:
        doomed = {}                          # block -> set of line indices to drop
        for block, line_idx, line, band in _band_candidates(page):
            stripped = line.strip()
            if not stripped:
                continue
            if PAGE_NUMBER_RE.match(stripped):
                doomed.setdefault(id(block), (block, set()))[1].add(line_idx)
                report.page_number_lines_removed += 1
            elif is_boiler(stripped, band):
                doomed.setdefault(id(block), (block, set()))[1].add(line_idx)
                report.header_lines_removed += 1
        for block, line_idxs in doomed.values():
            lines = block.text.split("\n")
            block.text = "\n".join(
                l for i, l in enumerate(lines) if i not in line_idxs
            ).strip()
        emptied = [b for b in page.blocks if not b.text.strip()]
        if emptied:
            report.blocks_dropped += len(emptied)
            page.blocks = [b for b in page.blocks if b.text.strip()]

    return report
