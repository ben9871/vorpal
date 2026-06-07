"""Text-quality scoring shared by species detection and OCR QA.

Two signals:
  - wordlike_ratio: fraction of tokens shaped like real English words
  - function_word_rate: hit rate of common function words ("the", "of", ...)
    Real prose runs ~35-55%; OCR'd diagrams and garbage run near zero.

text_quality() blends them into a 0..1 score. page_score() multiplies by OCR
confidence to give the per-page QA score from docs/03-architecture.md.
"""

import re

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'’-]*")
_WORDLIKE_RE = re.compile(r"^[A-Za-z][a-z'’-]*$")
_VOWEL_RE = re.compile(r"[aeiouyAEIOUY]")

# ~120 highest-frequency English function words. In normal running prose,
# 35%+ of tokens come from this set; OCR noise and diagram text score ~0.
_FUNCTION_WORDS = frozenset("""
the of and a to in is was he for it with as his on be at by i this had not
are but from or have an they which one you were her all she there would
their we him been has when who will more no if out so said what up its
about into than them can only other new some could time these two may then
do first any my now such like our over man me even most made after also
did many before must through back years where much your way well down
should because each just those people mr how too little state good very
make world still own see men work long get here between both life being
under never day same another know while last might us great old year off
come since against go came right used take three
""".split())

_FW_PROSE_RATE = 0.35  # function-word rate of typical English prose


def words(text: str) -> list:
    return _WORD_RE.findall(text)


_CONSONANT_RUN_RE = re.compile(r"[bcdfghjklmnpqrstvwxz]{5,}", re.IGNORECASE)


def wordlike_ratio(text: str) -> float:
    """Fraction of word tokens shaped like real words (has a vowel, plausible
    length, no absurd consonant runs). Case-insensitive: all-caps headings
    are normal in books."""
    toks = words(text)
    if not toks:
        return 0.0
    good = 0
    for t in toks:
        if len(t) > 22:
            continue
        if not _VOWEL_RE.search(t) and len(t) > 2:
            continue
        if _CONSONANT_RUN_RE.search(t):
            continue
        if _WORDLIKE_RE.match(t) or _WORDLIKE_RE.match(t.capitalize()):
            good += 1
    return good / len(toks)


def function_word_rate(text: str) -> float:
    toks = words(text)
    if not toks:
        return 0.0
    hits = sum(1 for t in toks if t.lower() in _FUNCTION_WORDS)
    return hits / len(toks)


_FW_MIN_TOKENS = 8  # below this, function-word stats are meaningless


def text_quality(text: str) -> float:
    """0..1 score of how much this text looks like real English prose.

    Function-word rate is the primary discriminator — pronounceable caps
    garbage (OCR'd diagrams) passes shape checks but contains zero function
    words. Very short texts (chapter-title pages) are judged on token shape
    alone, since a six-word title legitimately has no function words.
    """
    toks = words(text)
    if not toks:
        return 0.0
    wl = wordlike_ratio(text)
    if len(toks) < _FW_MIN_TOKENS:
        return wl
    fw = min(1.0, function_word_rate(text) / _FW_PROSE_RATE)
    return 0.35 * wl + 0.65 * fw


def page_score(ocr_confidence: float, text: str) -> float:
    """Per-page QA score: mean OCR confidence (0..1) x text quality (0..1)."""
    return ocr_confidence * text_quality(text)
