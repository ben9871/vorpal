"""Text-to-chunk preparation for TTS.

Phase 0: port of the v0 chunker with one deliberate fix. The v0 code used the
EMPTY STRING as the abbreviation-period placeholder, and `s.replace("", ".")`
inserts a period between every character in Python — so every sentence in any
paragraph longer than max_chars reached the TTS engine as ".T.h.e. .d.o.g."
(docs/01-audit.md §3). We use a real sentinel character instead; behavior is
otherwise identical. Phase 3 replaces this module with full spoken-form
normalization + pysbd segmentation.
"""

import re

# Abbreviations that should never trigger a sentence split
_ABBREVS = re.compile(
    r"(Mr|Mrs|Ms|Dr|Prof|Sr|Jr|St|vs|etc|e\.g|i\.e|cf|al|vol|pp|ch|fig|approx|dept|est|govt|inc|corp|ltd)\.",
    re.IGNORECASE,
)

# Sentinel for protected abbreviation periods. NUL never occurs in book text.
_ABBR_DOT = "\x00"


def split_into_chunks(text: str, max_chars: int = 500) -> list:
    """
    Split text into natural TTS chunks:
    - Respect paragraph boundaries (double newlines)
    - Don't split on known abbreviations
    - Keep chunks large enough for natural flow
    - Each chunk ends at a real sentence boundary
    """
    # First split on paragraph breaks — these are natural pause points
    paragraphs = re.split(r"\n\n+", text)
    chunks = []

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        # If paragraph fits in one chunk, keep it whole
        if len(para) <= max_chars:
            chunks.append(para)
            continue

        # Otherwise split on sentence endings, but protect abbreviations first
        # by swapping their periods for a sentinel that can't trigger a split.
        protected = _ABBREVS.sub(lambda m: m.group(0).replace(".", _ABBR_DOT), para)

        # Split on sentence-ending punctuation followed by whitespace
        raw_sentences = re.split(r"(?<=[.!?])\s+", protected)

        # Restore the protected periods
        sentences = [s.replace(_ABBR_DOT, ".") for s in raw_sentences]

        current = ""
        for s in sentences:
            s = s.strip()
            if not s:
                continue
            if len(current) + len(s) + 1 <= max_chars:
                current = (current + " " + s).strip()
            else:
                if current:
                    chunks.append(current)
                # If a single sentence exceeds max_chars, split at clause boundaries
                if len(s) > max_chars:
                    clauses = re.split(r"(?<=[,;:])\s+", s)
                    sub = ""
                    for clause in clauses:
                        if len(sub) + len(clause) + 1 <= max_chars:
                            sub = (sub + " " + clause).strip()
                        else:
                            if sub:
                                chunks.append(sub)
                            sub = clause
                    if sub:
                        chunks.append(sub)
                    current = ""
                else:
                    current = s
        if current:
            chunks.append(current)

    return [c for c in chunks if c.strip()]
