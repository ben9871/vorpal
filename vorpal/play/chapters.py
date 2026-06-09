"""Act/scene chapter structure for plays (Phase 36).

Books get one chapter per chapter marker; plays get one chapter per act
(default) or per scene (``--chapters scene``). Chapter dicts use the same
shape the book pipeline's chapter list uses (title / skip / spoken_intro),
plus a ``beats`` list the synthesis router consumes — the mastering pipeline
needs no changes.
"""

import re
from typing import List, Optional

from .models import PlayDoc, Scene

_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}


def _roman_to_int(numeral: str) -> Optional[int]:
    """'IV' → 4; None when the string is not a roman numeral."""
    s = numeral.strip().upper()
    if not s or any(ch not in _ROMAN_VALUES for ch in s):
        return None
    total = 0
    prev = 0
    for ch in reversed(s):
        val = _ROMAN_VALUES[ch]
        total += val if val >= prev else -val
        prev = max(prev, val)
    return total


def _scene_number(scene: Scene) -> str:
    """Arabic scene number for titles: 'Scene III' → '3'; fallback raw tail."""
    m = re.match(r"Scene\s+(\S+)", scene.name)
    if not m:
        return scene.name
    token = m.group(1)
    if token.isdigit():
        return token
    val = _roman_to_int(token)
    return str(val) if val is not None else token


def scene_location(scene: Scene) -> str:
    """The scene's location for chapter titles.

    Prefers the SCENE-header tail the parser captured; falls back to the
    scene's first location-classified direction (Phase 33); empty when
    neither exists.
    """
    if scene.location.strip():
        return scene.location.strip()
    from .directions import classify_direction
    for beat in scene.beats:
        if beat.type != "direction":
            continue
        if classify_direction(beat.text) == "location":
            text = beat.text.strip()
            if text.startswith("[") and text.endswith("]"):
                text = text[1:-1].strip()
            return text
    return ""


def build_play_chapters(play_doc: PlayDoc, mode: str = "act") -> List[dict]:
    """Build the chapter list for a play.

    ``mode``: ``"act"`` (default — one chapter per act) or ``"scene"``
    (one per scene, titled ``"Act I, Scene 3 — <location>"``).

    Chapters with no beats are dropped (nothing to narrate).
    """
    if mode not in ("act", "scene"):
        raise ValueError(f"mode must be 'act' or 'scene', got {mode!r}")

    chapters: List[dict] = []
    for act in play_doc.acts:
        if mode == "act":
            beats = [b for scene in act.scenes for b in scene.beats]
            if not beats:
                continue
            chapters.append({
                "title": act.name,
                "kind": "act",
                "skip": False,
                "spoken_intro": None,
                "beats": beats,
            })
        else:
            for scene in act.scenes:
                if not scene.beats:
                    continue
                title = f"{act.name}, Scene {_scene_number(scene)}"
                location = scene_location(scene)
                if location:
                    title += f" — {location}"
                chapters.append({
                    "title": title,
                    "kind": "scene",
                    "skip": False,
                    "spoken_intro": None,
                    "beats": list(scene.beats),
                })
    return chapters
