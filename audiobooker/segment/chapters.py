"""Text cleanup and chapter splitting.

Phase 0: verbatim port of the v0 regex-heuristic logic, known-bad (it produced
58 sections for the 11-chapter Firestone book — see docs/01-audit.md §2).
Phase 2 replaces it with boilerplate clustering and the outline → TOC →
layout-heuristics cascade from docs/03-architecture.md.
"""

import re

# Patterns that indicate a chapter/part/section heading.
HEADING_PATTERNS = [
    # "CHAPTER ONE" / "CHAPTER 1" / "Chapter One"
    re.compile(r"^(CHAPTER|Chapter)\s+([IVXLCDM\d\w]+)(\s*\n\s*(.+))?$", re.MULTILINE),
    # "PART I" / "PART ONE"
    re.compile(r"^(PART|Part)\s+([IVXLCDM\d\w]+)(\s*\n\s*(.+))?$", re.MULTILINE),
    # Standalone Roman numeral (I, II, III ...) optionally followed by a title line
    re.compile(r"^(I{1,3}|IV|VI{0,3}|IX|X{1,3}|XI{1,3}|XIV|XV|XVI{0,3}|XIX|XX)$\s*\n\s*(.+)$", re.MULTILINE),
    # All-caps line 4-60 chars that looks like a title (no lowercase)
    re.compile(r"^([A-Z][A-Z\s\-\:]{3,58}[A-Z])$", re.MULTILINE),
]


def is_likely_toc(text: str) -> bool:
    """Return True if this block of text looks like a table of contents."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if len(lines) < 3:
        return False
    dot_lines = sum(1 for l in lines if re.search(r"\.{3,}", l))
    num_lines = sum(1 for l in lines if re.search(r"\s\d{1,3}\s*$", l))
    # If more than 30% of lines have trailing page numbers or dot leaders -> TOC
    return (dot_lines + num_lines) / len(lines) > 0.30


def clean_raw_text(text: str, header_patterns: list = None) -> str:
    """Basic OCR cleanup before chapter splitting."""
    if header_patterns:
        for p in header_patterns:
            text = re.sub(re.escape(p), "", text, flags=re.IGNORECASE)

    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)          # fix hyphenated line-breaks
    text = re.sub(r"^\s*\d{1,4}\s*$", "", text, flags=re.MULTILINE)  # page numbers
    text = re.sub(r"--- PAGE BREAK ---", "", text)
    text = text.replace("\f", "\n\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return "\n".join(l.rstrip() for l in text.splitlines()).strip()


def find_headings(text: str) -> list:
    """Return a sorted list of (char_position, heading_title) tuples."""
    hits = []
    seen_positions = set()

    for pattern in HEADING_PATTERNS:
        for m in pattern.finditer(text):
            pos = m.start()
            if pos in seen_positions:
                continue
            seen_positions.add(pos)

            # Build a clean title from the match groups
            groups = [g for g in m.groups() if g and g.strip()]
            title = " ".join(groups).strip()
            title = re.sub(r"\s+", " ", title)
            hits.append((pos, title))

    hits.sort(key=lambda x: x[0])
    return hits


def split_into_chapters(text: str) -> list:
    """
    Returns list of dicts: [{title, body, skip}, ...]
    skip=True means it looks like front-matter / TOC and should not be narrated.
    """
    headings = find_headings(text)

    if not headings:
        # No headings found — treat whole book as one chapter
        return [{"title": "Book", "body": text, "skip": False}]

    chapters = []

    # Text before the first heading = front matter
    preamble = text[:headings[0][0]].strip()
    if preamble:
        chapters.append({
            "title": "Front Matter",
            "body": preamble,
            "skip": is_likely_toc(preamble),
        })

    for i, (pos, title) in enumerate(headings):
        end_pos = headings[i + 1][0] if i + 1 < len(headings) else len(text)
        # Body starts after the heading line itself
        heading_end = text.index("\n", pos) if "\n" in text[pos:] else pos + len(title)
        body = text[heading_end:end_pos].strip()

        skip = is_likely_toc(body)
        # Skip short bodies — index entries, sub-headers, etc.
        # Real chapters have substantial text
        if len(body.split()) < 80:
            skip = True

        chapters.append({"title": title, "body": body, "skip": skip})

    kept = [c for c in chapters if not c["skip"]]
    skipped = [c for c in chapters if c["skip"]]
    print(f"  {len(chapters)} sections found → {len(kept)} chapters, {len(skipped)} skipped (TOC/front-matter)")

    for s in skipped:
        print(f"    Skipped: \"{s['title'][:60]}\"")

    return chapters
