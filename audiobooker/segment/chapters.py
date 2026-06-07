"""Chapter detection: outline → printed-TOC parse → layout heuristics.

A cascade (docs/03-architecture.md stage 3.4): each rung produces candidate
sections and must pass validation to win; failure falls through to the next
rung, never to garbage. Every section records its `source` and `confidence`
in the manifest so the review step can show *why* the tool believes in it.

Replaces the v0 regex heading-guessing that turned the 11-chapter Firestone
book into 58 sections (docs/01-audit.md §2).
"""

import re
import unicodedata
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from ..extract.quality import wordlike_ratio
from .frontmatter import classify_title, find_back_matter_start, is_figure_page
from .repair import join_blocks

# Fuzzy score (0..100) for a heading block to anchor a title.
ANCHOR_SCORE = 70
# A rung must anchor at least this fraction of its entries to validate.
MIN_ANCHORED_FRAC = 0.8
# Heading blocks live in the upper part of a page and are short.
HEADING_MAX_Y_FRAC = 0.50
HEADING_MAX_CHARS = 120
HEADING_MAX_LINES = 4
# Chapters with fewer body words than this get flagged for review.
MIN_BODY_WORDS = 100

_ONES = "zero one two three four five six seven eight nine ten eleven twelve \
thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
_TENS = ["", "", "twenty", "thirty", "forty"]


def _spoken_number(n: int) -> str:
    if n < 20:
        return _ONES[n]
    if n < 50:
        tens, ones = divmod(n, 10)
        return _TENS[tens] + (f"-{_ONES[ones]}" if ones else "")
    return str(n)


@dataclass
class Section:
    id: int
    title: str
    kind: str                 # chapter | frontmatter | backmatter | figure
    include: bool
    start: tuple              # (page_index, block_index)
    end: tuple = None         # exclusive (page_index, block_index)
    source: str = "manual"    # outline | toc | heuristic | manual
    confidence: float = 0.0
    spoken_intro: str = ""
    number: int = None        # printed chapter number, when present
    words: int = 0
    flags: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "title": self.title, "kind": self.kind,
            "include": self.include, "spoken_intro": self.spoken_intro,
            "start": list(self.start), "end": list(self.end) if self.end else None,
            "pages": [self.start[0] + 1, (self.end[0] if self.end else self.start[0]) + 1],
            "source": self.source, "confidence": round(self.confidence, 2),
            "words": self.words, "flags": self.flags,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Section":
        return cls(
            id=d["id"], title=d["title"], kind=d["kind"], include=d["include"],
            start=tuple(d["start"]), end=tuple(d["end"]) if d.get("end") else None,
            source=d.get("source", "manual"), confidence=d.get("confidence", 0.0),
            spoken_intro=d.get("spoken_intro", ""), words=d.get("words", 0),
            flags=d.get("flags", []),
        )


# ── title normalization & anchoring ──────────────────────────────────────

# The roman branch must not bite into a word ("Conclusion" starts with the
# roman numeral C; "Love" with L) — hence the trailing letter lookahead.
_ENUM_PREFIX_RE = re.compile(
    r"^\s*(?:chapter|part)?\s*(?:\d{1,3}|[IVXLCDM]+(?![A-Za-z]))\s*[.):—-]?\s*",
    re.IGNORECASE)
_LEAD_NUM_RE = re.compile(r"^\s*(\d{1,3})\s*[.):]")


def _norm_title(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).upper()
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _strip_enum(title: str) -> str:
    stripped = _ENUM_PREFIX_RE.sub("", title.strip())
    return stripped if stripped else title.strip()


def _title_number(title: str) -> int:
    m = _LEAD_NUM_RE.match(title)
    return int(m.group(1)) if m else None


def _heading_candidates(page) -> list:
    """(block_index, block) pairs that could be a chapter heading."""
    out = []
    for i, b in enumerate(page.blocks):
        text = b.text.strip()
        if not text or len(text) > HEADING_MAX_CHARS:
            continue
        if len(text.split("\n")) > HEADING_MAX_LINES:
            continue
        if b.bbox[1] > page.height * HEADING_MAX_Y_FRAC:
            continue
        out.append((i, b))
    return out


def _match_score(title_norm: str, block_text: str) -> float:
    block_norm = _norm_title(block_text)
    if not block_norm:
        return 0.0
    return fuzz.token_set_ratio(title_norm, block_norm)


def _find_anchor(pages_by_index: dict, title: str, hint: int):
    """Find a heading block matching `title` on page `hint` (or ±1).
    Returns (page_index, block_index, score) or None."""
    title_norm = _norm_title(_strip_enum(title))
    if not title_norm:
        return None
    for idx in (hint, hint + 1, hint - 1):
        page = pages_by_index.get(idx)
        if page is None:
            continue
        best = None
        for bi, b in _heading_candidates(page):
            score = _match_score(title_norm, b.text)
            if score >= ANCHOR_SCORE and (best is None or score > best[2]):
                best = (idx, bi, score)
        if best:
            return best
    return None


# ── rung a: embedded PDF outline ─────────────────────────────────────────

def _from_outline(pages, outline: list) -> list:
    """Sections from the PDF outline (ground truth when present).
    Returns [] when the outline is absent or fails validation."""
    entries = [e for e in outline if e.get("level", 1) == 1]
    if len(entries) < 2:
        return []
    pages_by_index = {p.index: p for p in pages}
    last_index = pages[-1].index if pages else 0

    sections, anchored = [], 0
    for e in entries:
        hint = e["page"] - 1                    # outline pages are 1-based
        if hint < 0 or hint > last_index:
            continue        # counts against the anchored fraction below —
                            # an outline pointing past the book is suspect
        anchor = _find_anchor(pages_by_index, e["title"], hint)
        if anchor:
            anchored += 1
            start, conf = (anchor[0], anchor[1]), 0.95
        else:
            start, conf = (hint, 0), 0.70
        late = hint > last_index * 0.8
        kind = classify_title(e["title"], late_in_book=late)
        sections.append(Section(
            id=0, title=e["title"].strip(), kind=kind,
            include=(kind == "chapter"), start=start,
            source="outline", confidence=conf,
            number=_title_number(e["title"]),
        ))

    if not sections or anchored / len(entries) < MIN_ANCHORED_FRAC:
        return []
    starts = [s.start for s in sections]
    if starts != sorted(starts):
        return []
    return sections


# ── rung b: printed TOC parse ────────────────────────────────────────────

_TOC_LINE_RE = re.compile(r"^(.{3,70}?)[ .·…]{2,}(\d{1,3})\s*$")
_TOC_SCAN_FRAC = 0.20      # TOC lives in the first fifth of the book


def _parse_toc_entries(pages) -> tuple:
    """Find printed-TOC pages and parse (title, printed_page) pairs.
    Returns (entries, last_toc_page_index)."""
    limit = max(pages[-1].index * _TOC_SCAN_FRAC, 10) if pages else 0
    entries, last_toc_page = [], None
    for page in pages:
        if page.index > limit:
            break
        page_entries = []
        for b in page.blocks:
            for line in b.text.split("\n"):
                m = _TOC_LINE_RE.match(line.strip())
                if m and wordlike_ratio(m.group(1)) >= 0.5:
                    page_entries.append((m.group(1).strip(" ."), int(m.group(2))))
        if len(page_entries) >= 3:
            entries.extend(page_entries)
            last_toc_page = page.index
    return entries, last_toc_page


def _from_toc(pages) -> list:
    """Sections from the printed table of contents. The TOC gives the exact
    expected chapter count — a structural checksum — and each entry must
    anchor at a heading-like block to validate."""
    entries, toc_page = _parse_toc_entries(pages)
    if len(entries) < 2:
        return []
    printed = [n for _, n in entries]
    if printed != sorted(printed):                  # numbers must ascend
        return []

    pages_by_index = {p.index: p for p in pages}
    body_pages = [p for p in pages if p.index > toc_page]

    # Anchor each title by global search (printed→PDF offset varies, and
    # two-page-spread scans break constant-offset inference entirely).
    sections, anchored, search_from = [], 0, toc_page + 1
    for title, printed_num in entries:
        best = None
        for page in body_pages:
            if page.index < search_from:
                continue
            anchor = _find_anchor({page.index: page}, title, page.index)
            if anchor and (best is None or anchor[2] > best[2]):
                best = anchor
                if anchor[2] >= 95:
                    break
        if best:
            anchored += 1
            search_from = best[0]                   # keep anchors monotonic
            start, conf = (best[0], best[1]), 0.85
        else:
            start, conf = None, 0.0
        late = bool(best) and best[0] > pages[-1].index * 0.8
        kind = classify_title(title, late_in_book=late)
        sections.append(Section(
            id=0, title=title, kind=kind, include=(kind == "chapter"),
            start=start, source="toc", confidence=conf,
            number=_title_number(title),
        ))

    if anchored / len(sections) < MIN_ANCHORED_FRAC:
        return []
    sections = [s for s in sections if s.start is not None]
    starts = [s.start for s in sections]
    if len(sections) < 2 or starts != sorted(starts):
        return []
    return sections


# ── rung c: layout heuristics ────────────────────────────────────────────

_HEUR_FONT_RATIO = 1.25    # heading font outlier vs body median (digital)


def _from_heuristics(pages) -> list:
    """Last-resort sections from layout signals. Digital: font-size outlier
    blocks near the top of a page. Scans: this rung intentionally produces
    nothing — low-confidence guessing is what exploded v0, so scanned books
    without outline/TOC go to review as a single body instead."""
    sizes = sorted(b.font_size for p in pages for b in p.blocks if b.font_size)
    if not sizes:
        return []
    body_font = sizes[len(sizes) // 2]

    sections = []
    for page in pages:
        for bi, b in _heading_candidates(page):
            if not b.font_size or b.font_size < body_font * _HEUR_FONT_RATIO:
                continue
            title = " ".join(b.text.split())
            if wordlike_ratio(title) < 0.5:         # gibberish is a figure,
                continue                            # not a title
            late = page.index > pages[-1].index * 0.8
            kind = classify_title(title, late_in_book=late)
            sections.append(Section(
                id=0, title=title, kind=kind, include=(kind == "chapter"),
                start=(page.index, bi), source="heuristic", confidence=0.5,
                number=_title_number(title),
            ))
            break                                    # one heading per page

    n_chapters = sum(1 for s in sections if s.kind == "chapter")
    if n_chapters < 2 or n_chapters > max(len(pages) / 3, 3):
        return []
    return sections


# ── shared assembly & validation ─────────────────────────────────────────

def _section_text(section: Section, pages_by_index: dict) -> str:
    """Body text for a section: blocks from after its heading block to its
    end boundary, skipping figure pages, repaired into paragraphs."""
    sp, sb = section.start
    ep, eb = section.end
    texts = []
    for idx in range(sp, ep + 1):
        page = pages_by_index.get(idx)
        if page is None or is_figure_page(page):
            continue
        lo = sb + 1 if idx == sp else 0              # skip the heading block
        hi = eb if idx == ep else len(page.blocks)
        texts.extend(b.text for b in page.blocks[lo:hi])
    return join_blocks(texts)


def _finalize(sections: list, pages: list) -> list:
    """Set end boundaries, cap the last chapter before back matter, classify
    figure pages, compute bodies/word counts, apply validation flags."""
    pages_by_index = {p.index: p for p in pages}
    end_index = pages[-1].index if pages else 0
    sections.sort(key=lambda s: s.start)

    # end = next section's start; last section capped at back-matter start
    last_chapter_page = max((s.start[0] for s in sections
                             if s.kind == "chapter"), default=end_index)
    back_start = find_back_matter_start(pages, last_chapter_page)
    for s, nxt in zip(sections, sections[1:]):
        s.end = nxt.start
    if sections:
        last = sections[-1]
        cap = back_start if last.kind == "chapter" and back_start > last.start[0] \
            else end_index + 1
        last.end = (cap - 1, len(pages_by_index.get(cap - 1, pages[-1]).blocks)) \
            if cap - 1 >= last.start[0] else last.start

    # trailing back matter (about the author, index…) not covered by any rung
    covered = sections[-1].end[0] if sections else -1
    if back_start <= end_index and covered < end_index:
        sections.append(Section(
            id=0, title="Back matter", kind="backmatter", include=False,
            start=(back_start, 0), end=(end_index, len(pages_by_index[end_index].blocks)),
            source=sections[0].source if sections else "manual", confidence=0.8,
        ))

    # leading front matter before the first section
    if sections and sections[0].start > (pages[0].index, 0):
        first_start = sections[0].start
        sections.insert(0, Section(
            id=0, title="Front matter", kind="frontmatter", include=False,
            start=(pages[0].index, 0), end=first_start,
            source=sections[0].source, confidence=0.8,
        ))

    chapter_no = 0
    for i, s in enumerate(sections):
        s.id = i + 1
        s.words = len(_section_text(s, pages_by_index).split())
        if s.kind == "chapter":
            chapter_no = s.number if s.number else chapter_no + 1
            display = _strip_enum(s.title)
            if s.number is not None:
                s.spoken_intro = f"Chapter {_spoken_number(chapter_no)}. {display}."
            else:
                s.spoken_intro = f"{display}."
            if wordlike_ratio(display) < 0.5:
                s.flags.append("title-sanity")
                s.confidence = min(s.confidence, 0.4)
            if s.words < MIN_BODY_WORDS:
                s.flags.append("short-body")
                s.confidence = min(s.confidence, 0.5)
    return sections


def detect_chapters(pages, outline: list = None) -> tuple:
    """The cascade. Returns (sections, source) where source names the rung
    that won: 'outline' | 'toc' | 'heuristic' | 'none'. With 'none', the
    whole body is returned as a single low-confidence section for review."""
    if not pages:
        return [], "none"
    for rung, name in ((lambda: _from_outline(pages, outline or []), "outline"),
                       (lambda: _from_toc(pages), "toc"),
                       (lambda: _from_heuristics(pages), "heuristic")):
        sections = rung()
        if sections:
            return _finalize(sections, pages), name

    whole = Section(
        id=1, title="Book", kind="chapter", include=True,
        start=(pages[0].index, -1),     # -1: no heading block to skip
        source="manual", confidence=0.2, flags=["no-structure-found"],
    )
    return _finalize([whole], pages), "none"


def section_body(section: Section, pages) -> str:
    """Public accessor for a section's narrated body text."""
    return _section_text(section, {p.index: p for p in pages})
