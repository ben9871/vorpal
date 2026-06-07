"""Footnote separation: bottom-of-page footnote blocks → side channel.

Footnotes are detected per *column* (two-page-spread scans put one printed
page per column), in the bottom region of the page, led by a footnote marker
(`*`, `†`, or `1.`/`1)`-style). Matching blocks move to a side channel so the
narration never reads them mid-sentence; reference markers attached to body
words are stripped (docs/03-architecture.md stage 3.2).

Conservative by design: a bare digit-space lead (OCR's rendering of an inline
superscript, e.g. `1 was told…` = `I was told…`) is NOT treated as a marker —
on scans it is more often a misread capital than a footnote.
"""

import re
from dataclasses import dataclass, field

# Block must start in the bottom portion of the page to be a footnote.
BOTTOM_FRAC = 0.60
# Symbol markers (asterisk/dagger, possibly doubled) are unambiguous.
STAR_MARKER_RE = re.compile(r"^\s*[\*†‡]{1,2}\s*\S")
# Numeric markers ("1." / "1)") collide with numbered body lists, so they are
# only trusted on the digital path where the small-font signal confirms them.
NUM_MARKER_RE = re.compile(r"^\s*\d{1,2}[.)]\s+\S")
# Section dividers like "* * *" / "***" are body ornaments, not footnotes.
DIVIDER_RE = re.compile(r"^[\s\*†‡·.\-—]{2,}$")
# A body word carrying a footnote reference: "tory,*" / "Complex,*" / "word†"
BODY_REF_RE = re.compile(r"(?<=[\w,;:.\"'’”)])[\*†‡](?=\s|$|[,;:.])")
# Digital path: footnote font is noticeably smaller than the body font.
SMALL_FONT_RATIO = 0.85


@dataclass
class Footnote:
    page: int
    text: str


@dataclass
class FootnoteReport:
    footnotes: list = field(default_factory=list)   # [Footnote, ...]
    markers_stripped: int = 0


def _column(block, page_width: float) -> int:
    """0 = left column, 1 = right (spread scans); single-column pages → 0."""
    return 0 if (block.bbox[0] + block.bbox[2]) / 2 < page_width / 2 else 1


def _body_font(page) -> float:
    """Median font size of the page's blocks (digital path), or None."""
    sizes = sorted(b.font_size for b in page.blocks if b.font_size)
    return sizes[len(sizes) // 2] if sizes else None


def _is_marker_led(text: str, small_font: bool) -> bool:
    first_line = text.strip().split("\n", 1)[0]
    if DIVIDER_RE.match(first_line):
        return False
    if not (STAR_MARKER_RE.match(first_line)
            or (small_font and NUM_MARKER_RE.match(first_line))):
        return False
    # Footnotes are sentence-case prose. An ALL-CAPS block is a TOC entry or
    # heading ("10. FEMINISM AND ECOLOGY"); a near-letterless one is a
    # misOCR'd ornament ("* * x"). Neither is a footnote.
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 10:
        return False
    return sum(c.islower() for c in letters) / len(letters) >= 0.5


def separate_footnotes(pages) -> FootnoteReport:
    """Move footnote blocks out of `pages` (mutated in place) into the report,
    and strip footnote-reference markers from the remaining body text."""
    report = FootnoteReport()

    for page in pages:
        if not page.blocks:
            continue
        body_font = _body_font(page)
        keep, removed_idx = [], set()

        for col in (0, 1):
            col_blocks = [(i, b) for i, b in enumerate(page.blocks)
                          if _column(b, page.width) == col]
            # Find marker-led footnote blocks in the bottom region.
            note_idxs = []
            for i, b in col_blocks:
                if b.bbox[1] < page.height * BOTTOM_FRAC:
                    continue
                has_font = bool(body_font and b.font_size)
                small_font = has_font and b.font_size <= body_font * SMALL_FONT_RATIO
                if has_font and not small_font:
                    continue        # digital path: not in the small footnote font
                if not _is_marker_led(b.text, small_font):
                    continue
                note_idxs.append(i)
            if not note_idxs:
                continue
            # A block directly below a footnote, in the same column, is its
            # continuation when it's also small-font (digital) or when it sits
            # closer to the footnote above than the body gap would allow —
            # conservatively: only unmarked blocks whose top is within one
            # text-line (~14pt) of the footnote's bottom.
            notes = {}
            for i in note_idxs:
                notes[i] = page.blocks[i].text.strip()
            for i, b in col_blocks:
                if i in notes or b.bbox[1] < page.height * BOTTOM_FRAC:
                    continue
                above = [j for j in notes if page.blocks[j].bbox[3] <= b.bbox[1] + 2
                         and _column(page.blocks[j], page.width) == col]
                if not above:
                    continue
                nearest = max(above, key=lambda j: page.blocks[j].bbox[3])
                if b.bbox[1] - page.blocks[nearest].bbox[3] <= 14:
                    notes[nearest] += "\n" + b.text.strip()
                    removed_idx.add(i)
            removed_idx.update(notes.keys())
            for i in sorted(notes):
                report.footnotes.append(Footnote(page=page.index, text=notes[i]))

        page.blocks = [b for i, b in enumerate(page.blocks) if i not in removed_idx]

        # Strip footnote-reference markers from the surviving body text.
        for b in page.blocks:
            new_text, n = BODY_REF_RE.subn("", b.text)
            if n:
                b.text = new_text
                report.markers_stripped += n

    return report
