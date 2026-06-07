"""Text repair: de-hyphenation, mojibake normalization, paragraph reflow.

Runs after boilerplate/footnote removal, before chapter detection
(docs/03-architecture.md stage 3.3). Three concerns:

- **De-hyphenation** of printed line-break hyphens (`revo-\\nlution`), checked
  against the same wordlike-shape test quality.py uses as its dictionary
  stand-in — a join that produces a non-wordlike token keeps its hyphen
  (`mother-\\nchild` stays a compound when the fusion looks wrong).
- **Mojibake normalization**: Unicode NFKC (ligatures, fullwidth forms),
  quote/dash class normalization, soft-hyphen and control-char removal.
  OCR confusables inside words (`SE¥s`) are *counted, not guessed at* —
  silently "fixing" words is how text gets corrupted invisibly.
- **Paragraph reflow**: hard-wrapped lines inside a block are flowed into a
  paragraph; `join_blocks()` assembles block runs into body text, stitching
  paragraphs that continue across block/page boundaries (a block ending
  mid-sentence followed by one starting lowercase is the same paragraph).
"""

import re
import unicodedata
from dataclasses import dataclass

from ..extract.quality import wordlike_ratio

# Curly/typographic quote classes → plain equivalents the normalizer and TTS
# handle uniformly. Dashes are left alone (normalize.py owns prosody).
_CHAR_MAP = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "ʼ": "'",
    "“": '"', "”": '"', "„": '"',
    "­": None,            # soft hyphen
    "ﬁ": "fi", "ﬂ": "fl",
})
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
# A non-ASCII symbol embedded in a letter run is OCR mojibake: SE¥s, DIALEGT¦C
_MOJIBAKE_RE = re.compile(r"[A-Za-z][^\x00-\x7f\s][A-Za-z]|[A-Za-z]{2}[^\x00-\x7f\s]")
_HYPHEN_BREAK_RE = re.compile(r"(\w+)-\n(\w+)")


@dataclass
class RepairReport:
    hyphens_joined: int = 0
    hyphens_kept: int = 0
    mojibake_tokens: int = 0   # counted for QA, never silently rewritten


def fix_mojibake(text: str) -> str:
    """NFKC + quote-class normalization + control-char removal."""
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_CHAR_MAP)
    return _CONTROL_RE.sub("", text)


def count_mojibake(text: str) -> int:
    return len(_MOJIBAKE_RE.findall(text))


def dehyphenate(text: str, report: RepairReport = None) -> str:
    """Join printed line-break hyphens when the fusion is word-shaped."""
    def _join(m):
        left, right = m.group(1), m.group(2)
        fused = left + right
        # A line-break hyphen continues in lowercase; a capitalized right half
        # is a proper-noun compound (Levi-\nStrauss) — keep it hyphenated.
        if right[0].islower() and wordlike_ratio(fused) == 1.0:
            if report:
                report.hyphens_joined += 1
            return fused
        if report:
            report.hyphens_kept += 1
        return f"{left}-{right}"
    return _HYPHEN_BREAK_RE.sub(_join, text)


def reflow_block(text: str) -> str:
    """Flow a block's hard-wrapped lines into one paragraph string."""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    return re.sub(r"  +", " ", " ".join(lines))


_SENT_END_RE = re.compile(r"[.!?:;\"'’”)\]]$")


def join_blocks(texts: list) -> str:
    """Assemble repaired block texts into body text. Blocks are paragraphs
    (blank line between); a block that ends mid-sentence and is followed by
    one starting lowercase is a continuation across a column/page boundary
    and is stitched into the same paragraph, healing the break-point hyphen."""
    out = []
    for text in texts:
        text = text.strip()
        if not text:
            continue
        if out:
            prev = out[-1]
            starts_lower = text[0].islower()
            if starts_lower and not _SENT_END_RE.search(prev):
                if prev.endswith("-"):                      # hyphen at the break
                    joined = dehyphenate(f"{prev[:-1]}-\n{text}")
                    out[-1] = joined.replace("\n", " ")
                else:
                    out[-1] = f"{prev} {text}"
                continue
        out.append(text)
    return "\n\n".join(out)


def repair_pages(pages) -> RepairReport:
    """Repair every block's text in place; returns QA counts."""
    report = RepairReport()
    for page in pages:
        for block in page.blocks:
            text = fix_mojibake(block.text)
            report.mojibake_tokens += count_mojibake(text)
            text = dehyphenate(text, report)
            block.text = reflow_block(text)
    return report
