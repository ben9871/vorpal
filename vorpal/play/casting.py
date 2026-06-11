"""Voice casting: map cast characters to voice-registry entries.

Goals (Phase 34, roadmap Arc 7):

- The protagonist gets the richest voice matching their gender.
- No two characters with more than 50 spoken lines share a voice.
- Gender is matched where the cast and registry both know it.
- Minor/cameo characters cycle through a shared pool; sharing is noted in the cast sheet.
- Stage directions get a dedicated narrator voice (default ``bm_lewis``).

The cast sheet stores voice *ids*, not VoiceEntry objects, so it JSON
round-trips cleanly into the play workdir alongside play.json / cast.json.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..tts.voices import VoiceEntry

# Characters above this many spoken lines never share a voice (while possible).
UNIQUE_LINE_THRESHOLD = 50

# Default "best voice" per protagonist gender.
DEFAULT_BEST_VOICE = {"m": "bm_george", "f": "af_heart"}

DEFAULT_NARRATOR_VOICE = "bm_lewis"


@dataclass
class CastSheet:
    """Character → voice assignment for one play."""
    assignments: Dict[str, str]                 # character name → voice id
    narrator_voice: str = DEFAULT_NARRATOR_VOICE
    notes: List[str] = field(default_factory=list)  # shared-voice / overflow log

    def voice_id_for(self, character_name: str) -> Optional[str]:
        return self.assignments.get(character_name)

    def shared_voices(self) -> Dict[str, List[str]]:
        """voice id → list of characters sharing it (only where len > 1)."""
        by_voice: Dict[str, List[str]] = {}
        for name, vid in self.assignments.items():
            by_voice.setdefault(vid, []).append(name)
        return {vid: names for vid, names in by_voice.items() if len(names) > 1}

    def to_dict(self) -> dict:
        return {
            "assignments": dict(self.assignments),
            "narrator_voice": self.narrator_voice,
            "notes": list(self.notes),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CastSheet":
        return cls(
            assignments=dict(d["assignments"]),
            narrator_voice=d.get("narrator_voice", DEFAULT_NARRATOR_VOICE),
            notes=list(d.get("notes", [])),
        )


def castable_voices(registry: Dict[str, VoiceEntry]) -> Dict[str, VoiceEntry]:
    """Voices usable for casting: local engines only.

    Credential-gated engines (openai) are excluded — a cast sheet must be
    synthesizable on the deterministic local pipeline.
    """
    return {vid: v for vid, v in registry.items() if v.engine == "kokoro"}


def _gender_of(entry: VoiceEntry) -> str:
    return entry.gender if entry.gender in ("m", "f") else "unknown"


class _Pools:
    """Gender-split voice pools with round-robin cursors for shared casting."""

    def __init__(self, voices: Dict[str, VoiceEntry]):
        self.by_gender: Dict[str, List[str]] = {"m": [], "f": [], "unknown": []}
        for vid, entry in voices.items():
            self.by_gender[_gender_of(entry)].append(vid)
        self._cursor: Dict[str, int] = {"m": 0, "f": 0, "unknown": 0}
        self.all_ids: List[str] = list(voices.keys())

    def pool_for(self, gender: str) -> List[str]:
        """Gender-matched pool; falls back to all voices when empty."""
        pool = self.by_gender.get(gender if gender in ("m", "f") else "unknown", [])
        if gender == "unknown":
            # Unknown-gender characters may draw from anywhere.
            pool = self.by_gender["unknown"] or self.all_ids
        return pool or self.all_ids

    def next_shared(self, gender: str) -> str:
        """Round-robin pick from the gender pool (sharing allowed)."""
        pool = self.pool_for(gender)
        key = gender if gender in ("m", "f") else "unknown"
        vid = pool[self._cursor[key] % len(pool)]
        self._cursor[key] += 1
        return vid


def _needs_unique_voice(character) -> bool:
    return (
        character.role in ("protagonist", "major")
        or character.line_count > UNIQUE_LINE_THRESHOLD
    )


def _pick_unique(pools: _Pools, gender: str, used: set, avoid: set,
                 gender_only: bool = False) -> Optional[str]:
    """First unused voice from the gender pool, then from any pool.

    ``avoid`` (e.g. the narrator voice) is skipped while alternatives remain.
    ``gender_only=True`` never crosses gender pools — used for minor/cameo
    parts, where a gender-matched shared voice beats a unique mismatched one
    (a male ghost in a female voice is worse than two gentlemen sharing).
    """
    candidates = list(pools.pool_for(gender))
    if not gender_only:
        for vid in pools.all_ids:
            if vid not in candidates:
                candidates.append(vid)
    for skip_avoided in (True, False):
        for vid in candidates:
            if vid in used:
                continue
            if skip_avoided and vid in avoid:
                continue
            return vid
    return None


def assign_voices(
    cast: list,
    voices: Dict[str, VoiceEntry],
    best_voice: Optional[str] = None,
    narrator_voice: str = DEFAULT_NARRATOR_VOICE,
) -> CastSheet:
    """Assign a voice to every character in ``cast``.

    ``cast`` is the list of Character objects from ``extract_cast`` (already
    sorted by word count, protagonist first).  ``voices`` is the casting
    registry (id → VoiceEntry), normally ``castable_voices(VOICE_REGISTRY)``.
    """
    if not voices:
        raise ValueError("assign_voices requires a non-empty voice registry")

    sheet = CastSheet(assignments={}, narrator_voice=narrator_voice)
    pools = _Pools(voices)
    used: set = set()
    avoid = {narrator_voice}

    # Process biggest parts first so they get first pick of unique voices.
    ordered = sorted(
        cast,
        key=lambda c: (c.role != "protagonist", -c.word_count),
    )

    for character in ordered:
        gender = character.gender_guess

        if character.role == "protagonist":
            wanted = best_voice or DEFAULT_BEST_VOICE.get(gender, "bm_george")
            vid = wanted if wanted in voices else None
            if vid is None:
                vid = _pick_unique(pools, gender, used, avoid)
            if vid is None:  # registry smaller than the cast
                vid = pools.next_shared(gender)
                sheet.notes.append(
                    f"OVERFLOW: protagonist {character.name} shares voice {vid}"
                )
        elif _needs_unique_voice(character):
            vid = _pick_unique(pools, gender, used, avoid)
            if vid is None:
                vid = pools.next_shared(gender)
                sheet.notes.append(
                    f"OVERFLOW: {character.role} {character.name} "
                    f"({character.line_count} lines) shares voice {vid} — "
                    f"registry exhausted"
                )
        else:
            # Minor/cameo: prefer an unused gender-matched voice when one
            # exists, otherwise cycle the shared gender pool. Never cross
            # gender just to stay unique.
            vid = _pick_unique(pools, gender, used, avoid, gender_only=True)
            if vid is None:
                vid = pools.next_shared(gender)

        sheet.assignments[character.name] = vid
        used.add(vid)

    for vid, names in sorted(sheet.shared_voices().items()):
        sheet.notes.append(f"shared: voice {vid} plays {', '.join(sorted(names))}")

    return sheet


def apply_overrides(
    sheet: CastSheet,
    overrides: Dict[str, str],
    voices: Dict[str, VoiceEntry],
) -> CastSheet:
    """Apply ``{"HAMLET": "bm_daniel"}``-style overrides to a cast sheet.

    Unknown voice ids are an error (a typo would silently miscast); unknown
    character names are recorded as notes and skipped (the play may simply
    not contain them).
    """
    for name, vid in overrides.items():
        if vid not in voices:
            raise ValueError(
                f"cast override for {name!r}: unknown voice id {vid!r}"
            )
        if name not in sheet.assignments:
            sheet.notes.append(f"override skipped: no character named {name!r}")
            continue
        sheet.assignments[name] = vid
        sheet.notes.append(f"override: {name} → {vid}")
    return sheet


def format_cast_table(cast: list, sheet: CastSheet,
                      voices: Dict[str, VoiceEntry]) -> str:
    """Render the cast sheet as the `vorpal cast` table."""
    lines = [
        f"  {'character':<24} {'voice':<20} {'role':<12} {'lines':>6}  gender",
        "  " + "─" * 74,
    ]
    for character in cast:
        vid = sheet.voice_id_for(character.name) or "—"
        entry = voices.get(vid)
        label = f"{vid} ({entry.display_name})" if entry else vid
        lines.append(
            f"  {character.name[:24]:<24} {label[:20]:<20} "
            f"{character.role:<12} {character.line_count:>6}  "
            f"{character.gender_guess}"
        )
    narr = voices.get(sheet.narrator_voice)
    narr_label = (
        f"{sheet.narrator_voice} ({narr.display_name})" if narr
        else sheet.narrator_voice
    )
    lines.append("")
    lines.append(f"  narrator (stage directions): {narr_label}")
    for note in sheet.notes:
        lines.append(f"  note: {note}")
    return "\n".join(lines)
