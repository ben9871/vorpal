"""Quoted-speech detection for dialogue-aware delivery.

Identifies text spans enclosed in double-quote marks (both ASCII straight
quotes and Unicode curly/smart quotes) and classifies chunks as dialogue
or narration.

Design:
  - Only closed quote pairs are counted — unclosed quotes (em-dash interruptions,
    multi-paragraph dialogue openings) are deliberately ignored to avoid false
    positives.
  - A chunk is classified as dialogue when ≥50% of its non-whitespace characters
    are inside closed quote spans.
  - Detection operates on normalized text (post spoken_form()), which converts
    curly quotes to straight ASCII quotes — but the patterns here also handle
    raw curly quotes for robustness.
"""

import re

# Closed double-quote spans in normalized (straight-quote) text
_ASCII_QUOTE = re.compile(r'"([^"]{0,500})"', re.DOTALL)

# Curly/smart double-quote spans (used in raw pre-normalization text)
_CURLY_QUOTE = re.compile(r'“([^”]{0,500})”', re.DOTALL)


def detect_dialogue_fraction(text: str) -> float:
    """Return the fraction of non-whitespace characters inside closed double-quote spans.

    Returns a float in [0.0, 1.0].  A value ≥ 0.5 indicates the chunk is
    primarily dialogue.  Handles both ASCII (``"…"``) and Unicode curly
    (``"…"``) double quotes.

    Edge cases:
    - Scare quotes: ``The "experts" disagreed.`` → low fraction (not dialogue)
    - Short dialogue: ``"Yes," she said.`` → high fraction (dialogue)
    - Unclosed quotes / em-dash interruptions: not counted (conservative)
    - Empty text: returns 0.0
    """
    if not text:
        return 0.0
    total_nonws = sum(1 for c in text if not c.isspace())
    if total_nonws == 0:
        return 0.0

    in_quotes: set = set()
    for pattern in (_ASCII_QUOTE, _CURLY_QUOTE):
        for m in pattern.finditer(text):
            for i in range(m.start(), m.end()):
                if not text[i].isspace():
                    in_quotes.add(i)

    return len(in_quotes) / total_nonws


def is_dialogue_chunk(text: str, threshold: float = 0.5) -> bool:
    """Return True if the majority of the chunk text is quoted speech.

    Uses detect_dialogue_fraction() >= threshold (default 0.5 = 50%).
    """
    return detect_dialogue_fraction(text) >= threshold
