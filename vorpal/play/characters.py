"""Character extraction and role classification for parsed plays.

Builds a cast list from a PlayDoc: counts lines/words per speaker, assigns
a role tier (protagonist/major/minor/cameo), and guesses gender from a
hardcoded canonical-name table + pronoun scan in stage directions.
"""

import re
from dataclasses import dataclass
from typing import List, Optional

from .models import PlayDoc

# ── canonical name gender table (Shakespeare ~60 most common names) ──────────

_GENDER_TABLE: dict = {
    # Male
    "HAMLET": "m", "HORATIO": "m", "LAERTES": "m", "POLONIUS": "m",
    "CLAUDIUS": "m", "GHOST": "m", "OSRIC": "m", "FORTINBRAS": "m",
    "ROSENCRANTZ": "m", "GUILDENSTERN": "m", "MARCELLUS": "m",
    "BARNARDO": "m", "FRANCISCO": "m", "REYNALDO": "m",
    "OTHELLO": "m", "IAGO": "m", "CASSIO": "m", "RODERIGO": "m",
    "BRABANTIO": "m", "DUKE": "m",
    "MACBETH": "m", "BANQUO": "m", "MACDUFF": "m", "MALCOLM": "m",
    "DONALBAIN": "m", "ROSS": "m", "LENNOX": "m", "ANGUS": "m",
    "CAITHNESS": "m", "MENTEITH": "m",
    "PROSPERO": "m", "CALIBAN": "m", "ARIEL": "m", "FERDINAND": "m",
    "GONZALO": "m", "TRINCULO": "m", "STEPHANO": "m",
    "ANTONIO": "m", "SEBASTIAN": "m", "ALONSO": "m",
    "ORSINO": "m", "MALVOLIO": "m", "TOBY": "m", "ANDREW": "m",
    "FESTE": "m", "VALENTINE": "m", "CURIO": "m",
    "OBERON": "m", "PUCK": "m", "BOTTOM": "m", "LYSANDER": "m",
    "DEMETRIUS": "m", "QUINCE": "m", "FLUTE": "m", "SNOUT": "m",
    "SNUG": "m", "STARVELING": "m", "EGEUS": "m", "PHILOSTRATE": "m",
    "BENEDICK": "m", "CLAUDIO": "m", "LEONATO": "m", "DOGBERRY": "m",
    "BALTHASAR": "m", "BORACHIO": "m", "CONRADE": "m", "VERGES": "m",
    # As You Like It (PG #1523) — added in Phase 40: ROSALIND was scanning
    # masculine because stage directions track her Ganymede disguise
    "ROSALIND": "f", "CELIA": "f", "AUDREY": "f", "PHEBE": "f",
    "ORLANDO": "m", "OLIVER": "m", "JAQUES": "m", "TOUCHSTONE": "m",
    "SILVIUS": "m", "CORIN": "m", "ADAM": "m", "AMIENS": "m",
    "CHARLES": "m", "WILLIAM": "m",
    # Twelfth Night (PG #1526)
    "FABIAN": "m", "CLOWN": "m",
    # Female
    "GERTRUDE": "f", "OPHELIA": "f",
    "DESDEMONA": "f", "EMILIA": "f", "BIANCA": "f",
    "LADY MACBETH": "f", "HECATE": "f",
    "MIRANDA": "f",
    "VIOLA": "f", "OLIVIA": "f", "MARIA": "f",
    "TITANIA": "f", "HERMIA": "f", "HELENA": "f", "HIPPOLYTA": "f",
    "HERO": "f", "BEATRICE": "f", "MARGARET": "f", "URSULA": "f",
    "GWENDOLEN": "f", "CECILY": "f", "MISS PRISM": "f", "LADY BRACKNELL": "f",
    # The Importance of Being Earnest female characters
    "LANE": "m", "ALGERNON": "m", "JACK": "m", "CHASUBLE": "m",
    "MERRIMAN": "m", "ERNEST": "m",
}

# Generic role labels (Gutenberg convention: "KING", "QUEEN", "FIRST CLOWN",
# "SECOND GENTLEMAN" …). Looked up on the full name and on the last word, so
# numbered/qualified labels resolve too. Added in Phase 34 — the real Hamlet
# text labels Claudius/Gertrude as KING/QUEEN, which the canonical table misses.
_GENERIC_GENDER: dict = {
    "KING": "m", "QUEEN": "f", "PRINCE": "m", "PRINCESS": "f",
    "LORD": "m", "LADY": "f", "GENTLEMAN": "m", "GENTLEWOMAN": "f",
    "PRIEST": "m", "FRIAR": "m", "MONK": "m", "NUN": "f",
    "CLOWN": "m", "FOOL": "m", "GRAVEDIGGER": "m",
    "SAILOR": "m", "SOLDIER": "m", "CAPTAIN": "m", "OFFICER": "m",
    "DUKE": "m", "DUCHESS": "f", "COUNT": "m", "COUNTESS": "f",
    "BOY": "m", "GIRL": "f", "NURSE": "f", "WITCH": "f",
    "FATHER": "m", "MOTHER": "f", "BROTHER": "m", "SISTER": "f",
}

# Pronoun pattern for scanning stage directions
_MASC_PRONOUN_RE = re.compile(r"\b(he|him|his)\b", re.IGNORECASE)
_FEM_PRONOUN_RE = re.compile(r"\b(she|her|hers)\b", re.IGNORECASE)


# ── dataclass ────────────────────────────────────────────────────────────────

@dataclass
class Character:
    name: str
    line_count: int
    word_count: int
    role: str           # protagonist | major | minor | cameo
    gender_guess: str   # m | f | unknown

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "line_count": self.line_count,
            "word_count": self.word_count,
            "role": self.role,
            "gender_guess": self.gender_guess,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Character":
        return cls(
            name=d["name"],
            line_count=d["line_count"],
            word_count=d["word_count"],
            role=d["role"],
            gender_guess=d["gender_guess"],
        )


# ── helpers ──────────────────────────────────────────────────────────────────

def _count_words(text: str) -> int:
    return len(text.split())


def _guess_gender(name: str, play_doc: PlayDoc) -> str:
    """Return 'm', 'f', or 'unknown' for a character name."""
    # Canonical table lookup (normalised uppercase)
    canonical = name.strip().upper()
    if canonical in _GENDER_TABLE:
        return _GENDER_TABLE[canonical]

    words = canonical.split()

    # Gendered title prefix: "SIR TOBY", "LADY CAPULET" — decisive on its own
    # (Phase 40: "SIR TOBY" missed the table's "TOBY" entry, then a pronoun
    # scan returned f)
    if words:
        if words[0] in ("SIR", "LORD", "MASTER", "FATHER", "FRIAR", "DON"):
            return "m"
        if words[0] in ("LADY", "DAME", "MISTRESS", "MISS", "MRS", "MOTHER"):
            return "f"
        # Table lookup on the last word: "SIR TOBY" → TOBY
        if words[-1] in _GENDER_TABLE:
            return _GENDER_TABLE[words[-1]]

    # Generic role labels: "KING", "QUEEN", "FIRST CLOWN", "SECOND GENTLEMAN"…
    if canonical in _GENERIC_GENDER:
        return _GENERIC_GENDER[canonical]
    last_word = words[-1] if words else ""
    if last_word in _GENERIC_GENDER:
        return _GENERIC_GENDER[last_word]

    # Pronoun scan: look for "NAME … he/she" patterns in stage directions
    name_pat = re.compile(r"\b" + re.escape(name) + r"\b", re.IGNORECASE)
    masc = 0
    fem = 0
    for act in play_doc.acts:
        for scene in act.scenes:
            for beat in scene.beats:
                if beat.type != "direction":
                    continue
                if not name_pat.search(beat.text):
                    continue
                masc += len(_MASC_PRONOUN_RE.findall(beat.text))
                fem += len(_FEM_PRONOUN_RE.findall(beat.text))

    if masc > fem and masc > 0:
        return "m"
    if fem > masc and fem > 0:
        return "f"
    return "unknown"


def _assign_role(word_count: int, all_word_counts: List[int]) -> str:
    """Assign a role tier based on word-count percentile.

    Thresholds:
      - top 1 by word count  → protagonist (up to 1 character)
      - top 10% (≥ p90)      → major
      - top 40% (≥ p60)      → minor
      - rest                 → cameo
    """
    if not all_word_counts:
        return "cameo"
    sorted_counts = sorted(all_word_counts, reverse=True)
    n = len(sorted_counts)

    # Protagonist: the single character with the most words
    if word_count >= sorted_counts[0]:
        return "protagonist"

    # Major: top 10% (at least 2nd-ranked if only 2 characters)
    major_cutoff_idx = max(1, int(n * 0.10))
    major_cutoff = sorted_counts[major_cutoff_idx] if major_cutoff_idx < n else sorted_counts[-1]
    if word_count >= major_cutoff:
        return "major"

    # Minor: top 40%
    minor_cutoff_idx = max(1, int(n * 0.40))
    minor_cutoff = sorted_counts[minor_cutoff_idx] if minor_cutoff_idx < n else sorted_counts[-1]
    if word_count >= minor_cutoff:
        return "minor"

    return "cameo"


# ── main function ─────────────────────────────────────────────────────────────

def extract_cast(play_doc: PlayDoc) -> List[Character]:
    """Build a cast list from a PlayDoc.

    Returns characters in descending word-count order.
    """
    word_counts: dict = {}
    line_counts: dict = {}

    for act in play_doc.acts:
        for scene in act.scenes:
            for beat in scene.beats:
                if beat.type != "speech" or not beat.speaker:
                    continue
                name = beat.speaker
                if name not in word_counts:
                    word_counts[name] = 0
                    line_counts[name] = 0
                word_counts[name] += _count_words(beat.text)
                # Count speech turns (each beat = one speaking turn)
                line_counts[name] += 1

    if not word_counts:
        return []

    all_counts = list(word_counts.values())
    characters = []
    for name, wc in word_counts.items():
        characters.append(Character(
            name=name,
            line_count=line_counts[name],
            word_count=wc,
            role=_assign_role(wc, all_counts),
            gender_guess=_guess_gender(name, play_doc),
        ))

    characters.sort(key=lambda c: c.word_count, reverse=True)
    return characters
