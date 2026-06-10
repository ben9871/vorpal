"""Spoken-form normalization, sentence segmentation, and prosody-aware chunking.

Phase 3 rewrite. Replaces the Phase-0 placeholder chunker with:
  - spoken_form(): deterministic text normalization (numbers, ordinals, roman
    numerals, abbreviations, citations, dashes, symbols)
  - normalize_chapter(): run spoken_form + pysbd segmentation + paragraph-aware
    chunk packing; returns structured Chunk objects with pause metadata and a
    tone slot carried for the post-v1 LLM pass
  - lint_chunks(): junk-lint gate — catches residual OCR noise and formatting
    artifacts before they reach the TTS engine
  - no-loss invariant: asserted on every chapter; build fails if text is dropped

Chunk schema (also written to chunks/{chapter}.jsonl):
  { idx, text, pause_after_ms, tone, text_hash }

tone is always null here; the post-v1 tone.py pass fills it.
"""

import hashlib
import re
import unicodedata
from dataclasses import dataclass, asdict
from typing import Optional

import pysbd

from .segment.dialogue import is_dialogue_chunk as _is_dialogue_chunk

# ── integer → word conversion ──────────────────────────────────────────────

_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven",
         "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen",
         "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
         "eighty", "ninety"]
_ORDINAL_IRREGULAR = {
    "zero": "zeroth", "one": "first", "two": "second", "three": "third",
    "four": "fourth", "five": "fifth", "six": "sixth", "seven": "seventh",
    "eight": "eighth", "nine": "ninth", "ten": "tenth",
    "eleven": "eleventh", "twelve": "twelfth", "thirteen": "thirteenth",
    "fourteen": "fourteenth", "fifteen": "fifteenth", "sixteen": "sixteenth",
    "seventeen": "seventeenth", "eighteen": "eighteenth", "nineteen": "nineteenth",
    "twenty": "twentieth", "thirty": "thirtieth", "forty": "fortieth",
    "fifty": "fiftieth", "sixty": "sixtieth", "seventy": "seventieth",
    "eighty": "eightieth", "ninety": "ninetieth",
    "hundred": "hundredth", "thousand": "thousandth", "million": "millionth",
}


def _int_to_words(n: int) -> str:
    if n < 0:
        return "negative " + _int_to_words(-n)
    if n < 20:
        return _ONES[n]
    if n < 100:
        tens, ones = divmod(n, 10)
        return _TENS[tens] + ("-" + _ONES[ones] if ones else "")
    if n < 1000:
        hundreds, rest = divmod(n, 100)
        return (_ONES[hundreds] + " hundred"
                + (" " + _int_to_words(rest) if rest else ""))
    if n < 1_000_000:
        thousands, rest = divmod(n, 1000)
        return (_int_to_words(thousands) + " thousand"
                + (" " + _int_to_words(rest) if rest else ""))
    if n < 1_000_000_000:
        millions, rest = divmod(n, 1_000_000)
        return (_int_to_words(millions) + " million"
                + (" " + _int_to_words(rest) if rest else ""))
    return str(n)


def _ordinal_words(n: int) -> str:
    words = _int_to_words(n)
    # Split off the last word (handles hyphenated tens like "twenty-one")
    if "-" in words.rsplit(" ", 1)[-1]:
        # e.g. "twenty-one" → "twenty-first"
        base, unit = words.rsplit("-", 1)
        suffix = _ORDINAL_IRREGULAR.get(unit, unit + "th")
        return base + "-" + suffix
    parts = words.rsplit(" ", 1)
    last = parts[-1]
    suffix = _ORDINAL_IRREGULAR.get(last, last + "th")
    return (" ".join(parts[:-1]) + " " + suffix).strip() if len(parts) > 1 else suffix


def _is_year(n: int) -> bool:
    return 1400 <= n <= 2100


def _year_to_words(n: int) -> str:
    if 1100 <= n <= 1999:
        hi, lo = divmod(n, 100)
        hi_w = _int_to_words(hi)
        if lo == 0:
            return hi_w + " hundred"
        if lo < 10:
            return hi_w + " oh " + _ONES[lo]
        return hi_w + " " + _int_to_words(lo)
    if 2000 <= n <= 2009:
        return "two thousand" + (" " + _ONES[n - 2000] if n > 2000 else "")
    if 2010 <= n <= 2099:
        hi, lo = divmod(n, 100)
        return _int_to_words(hi) + " " + _int_to_words(lo)
    return _int_to_words(n)


# ── roman numeral expansion ────────────────────────────────────────────────
# Only expand in well-defined contexts to avoid treating pronoun "I" as a
# roman numeral. Contexts: after "Chapter/Part/Volume/Book/Act/Scene/Section"
# and standalone at start of a segment before a period (heading format).

_ROMAN_LOOKUP = {
    "i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7,
    "viii": 8, "ix": 9, "x": 10, "xi": 11, "xii": 12, "xiii": 13,
    "xiv": 14, "xv": 15, "xvi": 16, "xvii": 17, "xviii": 18, "xix": 19,
    "xx": 20, "xxi": 21, "xxii": 22, "xxiii": 23, "xxiv": 24, "xxv": 25,
    "xxvi": 26, "xxvii": 27, "xxviii": 28, "xxix": 29, "xxx": 30,
    "xxxi": 31, "xxxii": 32, "xxxiii": 33, "xxxiv": 34, "xxxv": 35,
    "xxxvi": 36, "xxxvii": 37, "xxxviii": 38, "xxxix": 39,
}

_ROMAN_WORD = r"(?:x{0,3}(?:ix|iv|v?i{0,3}))"
# After a structural keyword
_ROMAN_KEYWORD_RE = re.compile(
    r"\b(Chapter|Part|Volume|Book|Act|Scene|Section)\s+(" + _ROMAN_WORD + r")\b",
    re.IGNORECASE,
)
# Standalone at start of text before period: "I. Introduction"
_ROMAN_HEADING_RE = re.compile(
    r"(?:^|\n)(" + _ROMAN_WORD + r")\.",
    re.IGNORECASE,
)


def _roman_to_words(match_str: str) -> str:
    key = match_str.lower()
    n = _ROMAN_LOOKUP.get(key)
    if n is None:
        return match_str  # unrecognised — leave as-is
    return _int_to_words(n)


# ── abbreviation protection (before pysbd) ─────────────────────────────────
# Use bytes/sentinel to prevent pysbd from splitting on abbreviation periods.
# \x01 (SOH) never appears in book text.
# IMPORTANT: use lambdas, not raw-string replacements — \x in a regex
# replacement string is not a valid escape sequence.

_SENTINEL = "\x01"   # replaces abbreviation period dots during segmentation

_ABBREV_PROTECT = [
    # Titles
    (re.compile(r"\b(Mr|Mrs|Ms|Dr|Prof|Sr|Jr|Rev|Lt|Gen|Sgt|Cpl|Pvt|Capt|Col|Maj)\.", re.I),
     lambda m: m.group(1) + _SENTINEL),
    # Academic / reference
    (re.compile(r"\b(vol|pp|p|ch|fig|sec|eq|approx|dept|est|govt|inc|corp|ltd|etc|vs|cf|al|ed|eds)\.", re.I),
     lambda m: m.group(1) + _SENTINEL),
    # Latin abbreviations (e.g., i.e.)
    (re.compile(r"\b(e\.g|i\.e|et\s+al|op\.cit|ibid)\.", re.I),
     lambda m: m.group(0).replace(".", _SENTINEL)),
    # Single-letter initials before another capital (A. B. Smith)
    (re.compile(r"\b([A-Z])\.\s+([A-Z])"),
     lambda m: m.group(1) + _SENTINEL + " " + m.group(2)),
]
_ABBR_RESTORE_RE = re.compile(re.escape(_SENTINEL))


def _protect_abbrevs(text: str) -> str:
    for pattern, repl in _ABBREV_PROTECT:
        text = pattern.sub(repl, text)
    return text


def _restore_abbrevs(text: str) -> str:
    return _ABBR_RESTORE_RE.sub(".", text)


# ── parenthetical citation stripping ──────────────────────────────────────

_CITATION_RE = re.compile(
    r"\("
    r"(?:"
    r"(?:see\s+)?pp?\.?\s*\d[\d\s,–\-]*"          # (pp. 14–22)
    r"|(?:see\s+)?(?:ibid|op\.cit|cf\.)[^)]*"      # (ibid.), (cf. ...)
    r"|italics\s+(?:mine|in\s+original)"            # (italics mine)
    r"|emphasis\s+(?:added|mine|in\s+original)"     # (emphasis added)
    r"|my\s+(?:italics|emphasis)"                   # (my italics)
    r"|sic"                                          # (sic)
    r")"
    r"\)",
    re.IGNORECASE,
)

# URL / ISBN elision
_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_ISBN_RE = re.compile(r"\bISBN[:\s-]*[\d\-X]{10,17}\b", re.IGNORECASE)

# Pipe character — OCR artifact from column separators / table lines
_PIPE_RE = re.compile(r"\s*\|\s*")

# Em-dash / en-dash (not between digits — those are ranges, handled earlier)
_EMDASH_RE = re.compile(r"(?<!\d)\s*[—–]\s*(?!\d)|(?<=\d)\s*[—–]\s*(?!\d)|(?<!\d)\s*[—–]\s*(?=\d)")

# Symbol expansions applied in order (order matters for multi-char sequences)
_SYMBOL_MAP = [
    ("%", " percent"),
    ("&", " and "),
    ("§", " section "),
    ("°", " degrees "),
    ("©", ""),
    ("®", ""),
    ("™", ""),
    ("…", "..."),
    ("’", "'"),   # right single quotation → apostrophe
    ("‘", "'"),   # left single quotation
    ("“", '"'),   # left double quotation
    ("”", '"'),   # right double quotation
    ("­", ""),    # soft hyphen
]


def spoken_form(text: str) -> str:
    """Convert a prose string to a normalized spoken form suitable for TTS.

    Deterministic and unit-testable. No I/O, no model calls.
    """
    # 1. NFKC unicode normalization
    text = unicodedata.normalize("NFKC", text)

    # 2. Symbol substitutions
    for sym, replacement in _SYMBOL_MAP:
        text = text.replace(sym, replacement)

    # 3. URL / ISBN elision
    text = _URL_RE.sub("", text)
    text = _ISBN_RE.sub("", text)

    # 4. Parenthetical citation stripping
    text = _CITATION_RE.sub("", text)

    # 5. Pipe artifacts → comma (table/column OCR residue)
    text = _PIPE_RE.sub(", ", text)

    # 6. Roman numerals in structural context (before number expansion)
    def _roman_kw(m):
        return m.group(1) + " " + _roman_to_words(m.group(2))
    text = _ROMAN_KEYWORD_RE.sub(_roman_kw, text)

    def _roman_hd(m):
        # Preserve the leading newline if present, just replace the roman token
        prefix = m.group(0)[0] if m.group(0)[0] in "\n" else ""
        return prefix + _roman_to_words(m.group(1)) + "."
    text = _ROMAN_HEADING_RE.sub(_roman_hd, text)

    # 7. Ordinal numbers: 1st → first, 2nd → second, etc.
    def _expand_ordinal(m):
        return _ordinal_words(int(m.group(1)))
    text = re.sub(r"\b(\d+)(?:st|nd|rd|th)\b", _expand_ordinal, text)

    # 8. Page/volume ranges with pp.: pp. 14–22 → "pages fourteen to twenty-two"
    def _expand_pp_range(m):
        lo, hi = int(m.group(1)), int(m.group(2))
        return f"pages {_int_to_words(lo)} to {_int_to_words(hi)}"
    text = re.sub(r"\bpp?\.\s*(\d+)[–\-](\d+)\b", _expand_pp_range, text)

    # 9. Number ranges: 14–22 → "fourteen to twenty-two"
    #    Must run BEFORE em-dash step to preserve the dash between digits.
    def _expand_range(m):
        lo, hi = int(m.group(1)), int(m.group(2))
        if _is_year(lo) and _is_year(hi):
            return f"{_year_to_words(lo)} to {_year_to_words(hi)}"
        return f"{_int_to_words(lo)} to {_int_to_words(hi)}"
    text = re.sub(r"\b(\d{1,4})[–\-](\d{1,4})\b", _expand_range, text)

    # 10. Em-dash / en-dash → ", "  (after ranges are consumed)
    text = re.sub(r"\s*[—–]\s*", ", ", text)

    # 11. Standalone numbers (after ranges and ordinals are consumed)
    def _expand_number(m):
        raw = m.group(0)
        n = int(raw.replace(",", ""))
        if len(raw.replace(",", "")) == 4 and _is_year(n):
            return _year_to_words(n)
        return _int_to_words(n)
    text = re.sub(r"\b\d{1,3}(?:,\d{3})*\b|\b\d+\b", _expand_number, text)

    # 12. Whitespace cleanup
    text = re.sub(r"  +", " ", text)
    text = re.sub(r" ([,\.])", r"\1", text)
    text = text.strip()

    return text


# ── junk-lint gate ─────────────────────────────────────────────────────────

_JUNK_PATTERNS = [
    (re.compile(r".{1,40}\|.{1,40}"),         "pipe-separated fragment"),
    (re.compile(r"^\s*\d{1,4}\s*$"),           "bare number line"),
    (re.compile(r"^\s*[A-Z ]{4,30}\s*$"),      "all-caps artifact"),
    (re.compile(r"[^\x20-\x7E\xC0-ɏ‘-”–—]{3}"),
     "non-printable cluster"),
]


def lint_chunks(chunks: list, chapter_title: str = "") -> list:
    """Return a list of lint violations found in the chunk texts."""
    violations = []
    for i, chunk in enumerate(chunks):
        text = chunk["text"]
        for pattern, label in _JUNK_PATTERNS:
            if pattern.search(text):
                violations.append({
                    "chunk_idx": i,
                    "pattern": label,
                    "snippet": text[:80],
                    "chapter": chapter_title,
                })
                break
    return violations


# ── chunk dataclass ────────────────────────────────────────────────────────

@dataclass
class Chunk:
    idx: int
    text: str
    pause_after_ms: int    # 0 = no pause; >0 = paragraph boundary
    tone: Optional[str]    # always None here; post-v1 tone.py fills it
    text_hash: str
    is_dialogue: bool = False  # Phase 24: True when chunk is majority quoted speech
    voice_id: Optional[str] = None  # Phase 35: per-chunk voice (plays); None = book voice

    def to_dict(self) -> dict:
        return asdict(self)


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# ── prosody-aware chunk packing ────────────────────────────────────────────

_SEGMENTER = pysbd.Segmenter(language="en", clean=False)

PAUSE_PARAGRAPH_MS = 600
PAUSE_SENTENCE_MS = 0

# A sentence with no letters or digits cannot be narrated — it's a scene-break
# ornament ('* * *'), a rule, or scan residue. It becomes a pause, never a
# synthesis attempt (Kokoro returns nothing for symbol-only input, which the
# retry→split→abort policy then correctly escalates into a build failure).
_SPEAKABLE_RE = re.compile(r"[A-Za-z0-9]")


def _sentences(text: str) -> list:
    protected = _protect_abbrevs(text)
    segs = _SEGMENTER.segment(protected)
    return [_restore_abbrevs(s).strip() for s in segs if s.strip()]


def normalize_chapter(body: str, max_chars: int = 400,
                       paragraph_pause_ms: int = PAUSE_PARAGRAPH_MS) -> list:
    """Normalize a chapter body and pack it into prosody-aware Chunks.

    Chunking hierarchy (Phase 43 — strict priority order):
      1. Paragraph boundary always flushes. The accumulator is per-paragraph;
         paragraphs are never merged into one chunk, however short.
      2. A paragraph exceeding max_chars is split at sentence boundaries only:
         sentences pack greedily; when the next sentence would overflow, the
         current pack is emitted and a new one starts with that sentence.
      3. A sentence is NEVER cut in the middle. A single sentence longer than
         max_chars is emitted intact as one oversized chunk — the engine's
         internal segmentation handles it better than an arbitrary text cut
         (a hard mid-sentence cut produces an audible prosody restart).
      4. The last chunk of a paragraph carries pause_after_ms =
         paragraph_pause_ms; mid-paragraph chunks carry 0 (crossfaded at
         assembly, see synth.assemble_chapter_wav).
    """
    paragraphs = [p.strip() for p in re.split(r"\n\n+", body) if p.strip()]
    chunks: list = []
    idx = 0

    def _emit(text: str, pause: int) -> None:
        nonlocal idx
        chunks.append(Chunk(idx, text, pause, None, _text_hash(text),
                            _is_dialogue_chunk(text)))
        idx += 1

    for para_i, para in enumerate(paragraphs):
        normalized_para = spoken_form(para)
        sentences = _sentences(normalized_para)
        if not sentences:
            continue

        is_last_para = (para_i == len(paragraphs) - 1)
        current = ""

        for s_i, sent in enumerate(sentences):
            sent = sent.strip()
            if not sent:
                continue
            if not _SPEAKABLE_RE.search(sent):
                # ornament/divider → narrate nothing, breathe instead
                if current:
                    _emit(current, paragraph_pause_ms)
                    current = ""
                elif chunks:
                    chunks[-1].pause_after_ms = max(chunks[-1].pause_after_ms,
                                                    paragraph_pause_ms)
                continue
            is_last_sent = (s_i == len(sentences) - 1)

            if len(sent) > max_chars:
                # Never split mid-sentence (Phase 43 hard invariant): flush the
                # accumulator, then emit the oversized sentence intact as its
                # own chunk.
                if current:
                    _emit(current, PAUSE_SENTENCE_MS)
                    current = ""
                pause = (paragraph_pause_ms
                         if is_last_sent and not is_last_para
                         else PAUSE_SENTENCE_MS)
                _emit(sent, pause)
            elif len(current) + len(sent) + 1 <= max_chars:
                current = (current + " " + sent).strip() if current else sent
            else:
                if current:
                    _emit(current, PAUSE_SENTENCE_MS)
                current = sent

        # End of paragraph — emit with paragraph pause (unless last paragraph)
        if current:
            pause = paragraph_pause_ms if not is_last_para else 0
            _emit(current, pause)

    return chunks


def normalize_with_tones(body: str, paragraph_tones: list,
                         max_chars: int = 400) -> list:
    """Produce Chunks with tone annotations from paragraph-level tags.

    paragraph_tones: list of tone strings (one per paragraph, in order).
    Excess tones are ignored; missing tones fall back to 'neutral'.

    Groups consecutive same-tone paragraphs into 'tone runs', chunks each run
    independently (so chunks never cross a tone boundary), annotates each chunk
    with the run's tone ('neutral' is stored as None to match the base schema).
    """
    paragraphs = [p.strip() for p in re.split(r"\n\n+", body) if p.strip()]
    n = len(paragraphs)
    if not n:
        return []

    tones = list(paragraph_tones) + ["neutral"] * max(0, n - len(paragraph_tones))
    tones = tones[:n]

    # Group into (tone, combined_text) runs
    runs = []
    i = 0
    while i < n:
        tone = tones[i]
        run_paras = [paragraphs[i]]
        j = i + 1
        while j < n and tones[j] == tone:
            run_paras.append(paragraphs[j])
            j += 1
        runs.append((tone, "\n\n".join(run_paras)))
        i = j

    # Chunk each run, annotating with tone (None for neutral)
    all_chunks = []
    for tone, run_text in runs:
        run_chunks = normalize_chapter(run_text, max_chars=max_chars)
        tone_val = None if tone == "neutral" else tone
        for c in run_chunks:
            all_chunks.append(Chunk(c.idx, c.text, c.pause_after_ms, tone_val,
                                    c.text_hash, c.is_dialogue))

    # Re-index sequentially
    for i, c in enumerate(all_chunks):
        all_chunks[i] = Chunk(i, c.text, c.pause_after_ms, c.tone, c.text_hash,
                              c.is_dialogue)

    return all_chunks


def assert_no_loss(body: str, chunks: list) -> None:
    """Assert no text is dropped between normalization and chunking.

    Raises AssertionError if any words are missing or duplicated.
    The comparison is whitespace-insensitive to ignore spacing differences
    introduced by normalization.
    """
    def _canonical(text: str) -> str:
        return " ".join(text.split())

    chunk_text = " ".join(c.text for c in chunks)

    paras = [p.strip() for p in re.split(r"\n\n+", body) if p.strip()]
    expected_parts = []
    for para in paras:
        normalized = spoken_form(para)
        sents = _sentences(normalized)
        # unspeakable ornaments become pauses, not text — mirror the chunker
        expected_parts.extend(
            s.strip() for s in sents
            if s.strip() and _SPEAKABLE_RE.search(s)
        )
    expected = " ".join(expected_parts)

    c1 = _canonical(chunk_text)
    c2 = _canonical(expected)

    if c1 != c2:
        w1 = c1.split()
        w2 = c2.split()
        for i, (a, b) in enumerate(zip(w1, w2)):
            if a != b:
                ctx1 = " ".join(w1[max(0, i-3):i+5])
                ctx2 = " ".join(w2[max(0, i-3):i+5])
                raise AssertionError(
                    f"No-loss invariant violated at word {i}:\n"
                    f"  chunks:   ...{ctx1}...\n"
                    f"  expected: ...{ctx2}..."
                )
        if len(w1) != len(w2):
            raise AssertionError(
                f"No-loss invariant violated: chunks have {len(w1)} words, "
                f"expected {len(w2)} words"
            )
