"""Stage direction classification and emotion hint extraction.

Classifies stage direction text into one of six kinds, and maps emotion
hints to the vorpal tone vocabulary (somber / tense / warm / wry / neutral).
All classification is rule-based — no LLM required.
"""

import re
from typing import Optional

# ── direction kind vocabulary ─────────────────────────────────────────────────

DIRECTION_KINDS = frozenset({
    "entry_exit",
    "location",
    "emotion_hint",
    "song",
    "action",
    "other",
})

# ── keyword lists ────────────────────────────────────────────────────────────

_ENTRY_EXIT_WORDS = frozenset({
    "enter", "exit", "exeunt", "re-enter", "re-enter",
})

_SONG_WORDS = frozenset({
    "sings", "singing", "song", "songs",
})

# ~80-word emotion vocabulary mapped to vorpal tone tags
# Format: {keyword: tone_tag}
_EMOTION_MAP: dict = {
    # somber
    "weeping": "somber",
    "weeps": "somber",
    "wept": "somber",
    "sobbing": "somber",
    "sadly": "somber",
    "mournfully": "somber",
    "in despair": "somber",
    "despairing": "somber",
    "in grief": "somber",
    "grieving": "somber",
    "lamenting": "somber",
    "sorrowfully": "somber",
    "heavily": "somber",
    "solemnly": "somber",
    "somberly": "somber",
    "in sorrow": "somber",
    "woefully": "somber",
    "bitterly": "somber",

    # tense
    "furiously": "tense",
    "angrily": "tense",
    "enraged": "tense",
    "in a rage": "tense",
    "threatening": "tense",
    "defiantly": "tense",
    "fiercely": "tense",
    "in horror": "tense",
    "horrified": "tense",
    "terrified": "tense",
    "in terror": "tense",
    "frantically": "tense",
    "desperately": "tense",
    "urgently": "tense",
    "accusingly": "tense",
    "harshly": "tense",
    "violently": "tense",
    "trembling": "tense",
    "shaking": "tense",
    "shouting": "tense",

    # warm
    "tenderly": "warm",
    "lovingly": "warm",
    "gently": "warm",
    "kindly": "warm",
    "warmly": "warm",
    "embracing": "warm",
    "kneeling": "warm",
    "fondly": "warm",
    "affectionately": "warm",
    "earnestly": "warm",
    "sincerely": "warm",
    "with affection": "warm",
    "compassionately": "warm",
    "reassuringly": "warm",
    "softly": "warm",
    "smiling": "warm",
    "laughing": "warm",
    "joyfully": "warm",
    "cheerfully": "warm",
    "merrily": "warm",
    "happily": "warm",
    "with joy": "warm",

    # wry
    "aside": "wry",
    "mockingly": "wry",
    "sarcastically": "wry",
    "ironically": "wry",
    "drily": "wry",
    "dryly": "wry",
    "with contempt": "wry",
    "contemptuously": "wry",
    "to himself": "wry",
    "to herself": "wry",
    "to himself or herself": "wry",
    "sneeringly": "wry",
    "wryly": "wry",
    "with a sneer": "wry",
    "cynically": "wry",
    "in an undertone": "wry",
    "whispering": "wry",
    "murmuring": "wry",
    "musing": "wry",
}

# Phrases take priority over single words (longest match wins)
_EMOTION_PHRASES = sorted(
    [(k, v) for k, v in _EMOTION_MAP.items() if " " in k],
    key=lambda x: -len(x[0]),
)
_EMOTION_WORDS = {k: v for k, v in _EMOTION_MAP.items() if " " not in k}


# ── classification helpers ────────────────────────────────────────────────────

def _strip_brackets(text: str) -> str:
    """Remove surrounding [brackets] or indentation from a direction string."""
    t = text.strip()
    if t.startswith("[") and t.endswith("]"):
        return t[1:-1].strip()
    return t


def _has_verb(text: str) -> bool:
    """Rough check: does the text contain a recognisable verb-like word?"""
    verbs = re.compile(
        r"\b(enter|exit|exeunt|kneel|sits?|sit|stand|stands?|rise|rises?|"
        r"draw|draws?|throws?|strikes?|falls?|falls?|fights?|runs?|comes?|goes?|"
        r"turns?|weeps?|laughs?|gives?|takes?|embraces?|kisses?|dies?|"
        r"steps?|crosses?|moves?|beckons?|drops?|picks?|puts?|sets?|"
        r"opens?|closes?|reads?|writes?|holds?|places?|removes?|"
        r"aside|singing|sings?|speaks?|whispers?|shouts?|returns?|"
        r"knocks?|rushes?|follows?|leads?)\b",
        re.IGNORECASE,
    )
    return bool(verbs.search(text))


# ── main functions ────────────────────────────────────────────────────────────

def classify_direction(text: str) -> str:
    """Classify a stage direction into one of the DIRECTION_KINDS.

    Classification priority:
      1. entry_exit  — contains Enter / Exit / Exeunt
      2. song        — contains Sings / Song
      3. emotion_hint — contains an emotion keyword
      4. location    — first direction of a scene (heuristic: no verb, describes a place)
      5. action      — anything else with a recognisable verb
      6. other       — fallback
    """
    body = _strip_brackets(text)
    lower = body.lower()

    # 0. Theatrical sound/spectacle cues ("Flourish", "Alarum", "Trumpets sound")
    # These are a distinct class of direction with no character action.
    _SPECTACLE_RE = re.compile(
        r"^\s*\[?\s*(flourish|alarum|trumpet|drum roll|thunder|lightning|music)\b",
        re.IGNORECASE,
    )
    if _SPECTACLE_RE.match(text):
        return "other"

    # 1. Entry/exit
    for word in _ENTRY_EXIT_WORDS:
        if re.search(r"\b" + re.escape(word) + r"\b", lower):
            return "entry_exit"

    # 2. Song
    for word in _SONG_WORDS:
        if re.search(r"\b" + re.escape(word) + r"\b", lower):
            return "song"

    # 3. Emotion hint (check phrases first, then words)
    for phrase, _ in _EMOTION_PHRASES:
        if phrase in lower:
            return "emotion_hint"
    for word in _EMOTION_WORDS:
        if re.search(r"\b" + re.escape(word) + r"\b", lower):
            return "emotion_hint"

    # 4. Location: short description of a place — typically contains a period or comma
    # (e.g. "Elsinore. A platform.") and no verb. Must look like a place name.
    if (len(body) < 120
            and not _has_verb(body)
            and (re.search(r"[A-Z][a-z]", body)  # contains a proper noun
                 or re.search(r"[.,]", body))     # or has punctuation typical of location
            and not re.search(r"^[A-Z][a-z\s]+$", body.strip())):  # not a single Title Word
        return "location"

    # 5. Action: has a verb
    if _has_verb(body):
        return "action"

    return "other"


def extract_emotion_hint(text: str) -> Optional[str]:
    """Return the tone tag for an emotion-hint direction, or None.

    Checks phrases (longest first) then single words. Returns one of:
    'somber', 'tense', 'warm', 'wry', or None if no emotion found.
    """
    body = _strip_brackets(text).lower()

    for phrase, tone in _EMOTION_PHRASES:
        if phrase in body:
            return tone
    for word, tone in _EMOTION_WORDS.items():
        if re.search(r"\b" + re.escape(word) + r"\b", body):
            return tone

    return None
