"""Footnote narration — Phase 25.

Provides two opt-in modes for surfacing footnote text in the audiobook:
  inline:  footnotes appended after each chapter body, spoken as a numbered list
  chapter: all footnotes collected into a single synthetic chapter entry

Both modes normalize footnote text through the standard spoken_form() path,
so numbers, abbreviations, and citations are handled consistently.

Usage in cmd_build():
    footnotes = load_footnotes_json(work_dir)
    # inline: mutate chapter["body"] for each chapter
    # chapter: append a synthetic chapter dict to the chapters list
"""

import json
from pathlib import Path
from typing import Optional

from .normalize import spoken_form


# ── text / number helpers ──────────────────────────────────────────────────

_SMALL_WORDS = [
    "", "one", "two", "three", "four", "five",
    "six", "seven", "eight", "nine", "ten",
    "eleven", "twelve", "thirteen", "fourteen", "fifteen",
    "sixteen", "seventeen", "eighteen", "nineteen", "twenty",
]


def _index_word(n: int) -> str:
    """Return the spoken ordinal for 1-based index n (falls back to digit string)."""
    if 1 <= n <= len(_SMALL_WORDS) - 1:
        return _SMALL_WORDS[n]
    return str(n)


def _clean_marker(text: str) -> str:
    """Strip leading footnote reference markers from footnote text.

    Handles patterns like:
      * This is a footnote.
      1. This is a footnote.
      1) This is a footnote.
      † This is a footnote.
    """
    import re
    text = text.strip()
    text = re.sub(r'^[\*†‡]+\s*', '', text)
    text = re.sub(r'^\d+[.)]\s*', '', text)
    return text.strip()


# ── load / assign ──────────────────────────────────────────────────────────

def load_footnotes_json(work_dir: Path) -> list:
    """Load footnotes.json from the workdir.  Returns [] if absent."""
    path = work_dir / "footnotes.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def assign_to_chapter(footnotes: list, section) -> list:
    """Return the subset of footnotes that fall within the section's page range.

    section is a vorpal.segment.chapters.Section (or a dict from manifest with
    "start" and "end" keys).  page numbers in footnotes are 0-based indices
    matching Section.start[0].
    """
    if isinstance(section, dict):
        start_page = section.get("start", [0])[0]
        end = section.get("end")
        end_page = end[0] if end else None
    else:
        start_page = section.start[0]
        end_page = section.end[0] if section.end else None

    result = []
    for fn in footnotes:
        p = fn.get("page", -1)
        if p < start_page:
            continue
        if end_page is not None and p >= end_page:
            continue
        result.append(fn)
    return result


# ── text formatting ────────────────────────────────────────────────────────

def format_inline_text(footnotes: list, start_index: int = 1) -> str:
    """Return a text block to append after a chapter body for inline mode.

    Each footnote is formatted as:
        Footnote [N]. [normalized text]

    Returns an empty string if footnotes is empty.
    """
    if not footnotes:
        return ""
    lines = []
    for i, fn in enumerate(footnotes, start=start_index):
        raw = _clean_marker(fn.get("text", ""))
        if not raw:
            continue
        normalized = spoken_form(raw)
        word = _index_word(i)
        lines.append(f"Footnote {word}. {normalized}")
    if not lines:
        return ""
    return "\n\n".join(lines)


def format_chapter_body(footnotes: list) -> str:
    """Return the body text for a synthetic footnotes chapter.

    All footnotes are numbered globally starting from 1.
    Returns an empty string if footnotes is empty.
    """
    return format_inline_text(footnotes, start_index=1)


# ── chapter-mode manifest entry ───────────────────────────────────────────

def make_footnotes_chapter(footnotes: list) -> Optional[dict]:
    """Return a synthetic chapter dict for chapter mode, or None if empty."""
    body = format_chapter_body(footnotes)
    if not body:
        return None
    return {
        "title": "Footnotes",
        "body": body,
        "skip": True,       # include=False by default; user can flip in manifest
        "spoken_intro": "End notes.",
        "kind": "footnotes",
    }
