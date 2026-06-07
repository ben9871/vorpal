"""Plain-text input path: chapter heuristics → section dicts.

Converges at the same interface as extract/epub.py.  Clean text (Gutenberg
TXT has no OCR noise) means heading-pattern heuristics are reliable here —
unlike scanned PDFs where v0's guessing exploded to 58 sections.

Returns section dicts compatible with Section.from_dict.
"""

import re
from pathlib import Path


# ── chapter heading patterns ──────────────────────────────────────────────

# Matches lines like:
#   CHAPTER I       CHAPTER ONE      CHAPTER 1
#   Chapter I       Chapter 12       CHAPTER XII
#   PART ONE        PART I           BOOK I
#   I.              IV.              XII.    (roman numeral followed by period)
_HEADING_RE = re.compile(
    r"^(?:"
    r"(?:CHAPTER|Chapter|chapter)\s+(?:[IVXLCDM]+|[A-Za-z]+|\d+)"
    r"|(?:PART|Part|BOOK|Book)\s+(?:[IVXLCDM]+|[A-Za-z]+|\d+)"
    r"|[IVXLCDM]{1,5}\."          # bare roman numeral + period
    r")"
    r"(?:\s*[.:\-—]?\s*.{0,80})?$",
    re.MULTILINE,
)

_GUTENBERG_HEADER_RE = re.compile(
    r"\*\*\*\s*START OF THE PROJECT GUTENBERG", re.IGNORECASE
)
_GUTENBERG_FOOTER_RE = re.compile(
    r"\*\*\*\s*END OF THE PROJECT GUTENBERG", re.IGNORECASE
)


def _strip_gutenberg_wrapper(text: str) -> str:
    """Remove Project Gutenberg header/footer boilerplate."""
    m = _GUTENBERG_HEADER_RE.search(text)
    if m:
        text = text[m.end():]
        # Skip to next blank line after the header sentinel
        idx = text.find("\n\n")
        if idx >= 0:
            text = text[idx:]

    m = _GUTENBERG_FOOTER_RE.search(text)
    if m:
        text = text[:m.start()]

    return text.strip()


_DOT_LEADER_RE = re.compile(r"\.{2,}|\. {1,3}\.")   # "..." or ". . ." patterns

def _is_heading_line(line: str) -> bool:
    line = line.strip()
    if not line:
        return False
    # Must be short enough to be a heading
    if len(line) > 120:
        return False
    # TOC entries have dot leaders — skip them
    if _DOT_LEADER_RE.search(line):
        return False
    return bool(_HEADING_RE.match(line))


# ── extraction ────────────────────────────────────────────────────────────

def extract_txt(txt_path: Path) -> dict:
    """Parse a plain-text file into section dicts ready for the pipeline.

    Returns:
        {
          "title": str,
          "author": str,
          "format": "txt",
          "sections": [section_dict, ...],
          "qa": dict,
        }

    Sections get ``source = "heuristic"`` (may need review if confidence is
    low) or ``source = "manual"`` when no structure is found.
    """
    try:
        raw = txt_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        raise RuntimeError(f"Cannot read text file {txt_path}: {e}") from e

    text = _strip_gutenberg_wrapper(raw)

    # Try to extract title/author from Gutenberg-style header
    title, author = _extract_gutenberg_meta(raw)

    raw_sections = _split_into_sections(text)
    heuristic_used = len(raw_sections) > 1

    sections = []
    chapter_no = 0
    for idx, (heading, body) in enumerate(raw_sections):
        body = body.strip()
        words = len(body.split())
        kind = _classify_title(heading) if heading else "chapter"
        include = kind == "chapter"
        if include:
            chapter_no += 1
            display = _strip_enum_prefix(heading) if heading else "Book"
            spoken_intro = f"Chapter {_spoken_num(chapter_no)}. {display}."
        else:
            spoken_intro = (_strip_enum_prefix(heading) if heading else "Front matter") + "."

        source = "heuristic" if heuristic_used and heading else "manual"
        confidence = 0.7 if heuristic_used and heading else 0.3

        flags = []
        if words < 100 and include:
            flags.append("short-body")
        if not heading:
            flags.append("no-structure-found")

        sections.append({
            "id": idx + 1,
            "title": heading or "Book",
            "kind": kind,
            "include": include,
            "spoken_intro": spoken_intro,
            "start": [idx, 0],
            "end": [idx, 0],
            "pages": [idx + 1, idx + 1],
            "source": source,
            "confidence": confidence,
            "words": words,
            "flags": flags,
            "body": body,
        })

    qa = {
        "heuristic_used": heuristic_used,
        "sections_produced": len(sections),
        "chapter_source": "heuristic" if heuristic_used else "manual",
    }

    return {
        "title": title,
        "author": author,
        "format": "txt",
        "sections": sections,
        "qa": qa,
    }


def _split_into_sections(text: str) -> list:
    """Split text into [(heading, body), ...] based on chapter headings.

    Falls back to a single (None, full_text) section if no headings found.
    """
    # Split into paragraphs (double newlines)
    # Then look for heading-paragraph patterns
    lines = text.splitlines()

    # Find candidate heading line indices
    # A heading must be preceded and followed by blank lines (or be at the start)
    heading_positions = []  # list of (line_index, heading_text)
    for i, line in enumerate(lines):
        if not _is_heading_line(line):
            continue
        # Check: line before is blank (or we're near the start)
        prev_blank = (i == 0 or not lines[i - 1].strip())
        # Check: line after is blank (or next non-blank line is content)
        next_blank = (i + 1 >= len(lines) or not lines[i + 1].strip())
        if prev_blank or next_blank:
            heading_positions.append((i, line.strip()))

    if len(heading_positions) < 2:
        return [(None, text)]

    sections = []
    for j, (pos, heading) in enumerate(heading_positions):
        # Body: from after this heading to just before the next heading
        body_start = pos + 1
        body_end = heading_positions[j + 1][0] if j + 1 < len(heading_positions) else len(lines)
        body = "\n".join(lines[body_start:body_end]).strip()
        # Convert multiple blank lines to double newline (paragraph separator)
        body = re.sub(r"\n{3,}", "\n\n", body)
        sections.append((heading, body))

    return sections


def _extract_gutenberg_meta(text: str) -> tuple:
    """Extract title and author from Project Gutenberg header if present."""
    title = author = ""
    for line in text.splitlines()[:40]:
        line = line.strip()
        m = re.match(r"Title:\s+(.+)", line, re.IGNORECASE)
        if m and not title:
            title = m.group(1).strip()
        m = re.match(r"Author:\s+(.+)", line, re.IGNORECASE)
        if m and not author:
            author = m.group(1).strip()
        if title and author:
            break
    return title, author


# ── helpers (local copies to avoid segment import cycle) ─────────────────

_ONES = "zero one two three four five six seven eight nine ten eleven twelve \
thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
_TENS = ["", "", "twenty", "thirty", "forty", "fifty"]

_ENUM_RE = re.compile(
    r"^\s*(?:chapter|part|section|book)?\s*(?:\d{1,3}|[IVXLCDM]+(?![A-Za-z]))\s*[.):—-]?\s*",
    re.IGNORECASE,
)

_FRONT_KEYWORDS = frozenset([
    "preface", "foreword", "introduction", "acknowledgements", "acknowledgments",
    "prologue", "copyright", "dedication", "epigraph", "author's note",
    "note to the reader",
])
_FRONT_PREFIXES = ("about the author", "author note")

_BACK_KEYWORDS = frozenset([
    "index", "bibliography", "notes", "afterword", "appendix", "glossary",
    "further reading", "references", "selected works", "works cited",
])
_BACK_PREFIXES = ("about ", "appendix ")


def _spoken_num(n: int) -> str:
    if n < 20:
        return _ONES[n]
    if n < 60:
        tens, ones = divmod(n, 10)
        return _TENS[tens] + (f"-{_ONES[ones]}" if ones else "")
    return str(n)


def _strip_enum_prefix(title: str) -> str:
    stripped = _ENUM_RE.sub("", title.strip())
    return stripped if stripped else title.strip()


def _classify_title(title: str) -> str:
    t_clean = re.sub(r"[^a-z ]", "", title.lower().strip()).strip()
    if t_clean in _FRONT_KEYWORDS or any(t_clean.startswith(p) for p in _FRONT_PREFIXES):
        return "frontmatter"
    if t_clean in _BACK_KEYWORDS or any(t_clean.startswith(p) for p in _BACK_PREFIXES):
        return "backmatter"
    if "project gutenberg" in t_clean:
        return "backmatter"
    return "chapter"
