"""Plain-text play parser targeting Gutenberg Shakespeare format.

Gutenberg Shakespeare conventions:
  - ACT I.  / SCENE I. Location text.   — headers on their own lines
  - HAMLET. / FIRST CLOWN.              — ALL-CAPS speaker label on its own line
  - Indented lines (2+ spaces)          — stage directions
  - [Bracketed text]                    — inline stage directions
  - Blank lines                         — paragraph/speech breaks
"""

import re
from typing import Optional

from .models import Act, Beat, PlayDoc, Scene

# ── compiled patterns ────────────────────────────────────────────────────────
# Case-sensitive, no leading whitespace on ACT — distinguishes actual headers
# from TOC entries (TOC uses 1-space indent or mixed-case "Scene").
# SCENE allows 0 or 1 leading space (Gutenberg Hamlet uses 1 space for scenes
# after the first of each act).

_ACT_RE = re.compile(r"^ACT\s+([IVX]+|\d+)\.?\s*$")
_SCENE_RE = re.compile(r"^[ ]?SCENE\s+([IVX]+|\d+)\.?\s*(.*?)\s*$")

# Speaker label: ALL-CAPS word(s) (letters, spaces, hyphens, apostrophes),
# optionally followed by a period, alone on the line.
_SPEAKER_RE = re.compile(r"^([A-Z][A-Z\s\-\']{1,50})\.?\s*$")

# Stage direction: indented (2+ spaces) OR entirely in [brackets]
_BRACKET_DIR_RE = re.compile(r"^\s*\[.+\]\s*$")
_INDENT_RE = re.compile(r"^  ")  # starts with 2+ spaces

# Prose filter: lines that look uppercase but contain lowercase are not speakers
_HAS_LOWER_RE = re.compile(r"[a-z]")


def _is_speaker(line: str) -> Optional[str]:
    """Return the normalised speaker name if line is a speaker label, else None."""
    stripped = line.strip()
    if len(stripped) < 2:
        return None
    # Quick lowercase filter — speaker labels are ALL-CAPS
    if _HAS_LOWER_RE.search(stripped):
        return None
    # ACT / SCENE headers are handled separately; exclude them here
    if _ACT_RE.match(stripped) or _SCENE_RE.match(stripped):
        return None
    m = _SPEAKER_RE.match(stripped)
    if not m:
        return None
    name = m.group(1).strip()
    # Require at least 2 uppercase letters
    if len(re.sub(r"[^A-Z]", "", name)) < 2:
        return None
    return name


def _is_direction(line: str) -> bool:
    """True if the line looks like a stage direction."""
    return bool(_BRACKET_DIR_RE.match(line)) or bool(_INDENT_RE.match(line))


def _extract_metadata(text: str) -> tuple:
    """Heuristically extract title and author from the play's opening lines."""
    lines = [l.rstrip() for l in text.split("\n")]
    title = ""
    author = ""
    for line in lines[:30]:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.lower().startswith("by "):
            author = stripped[3:].strip()
        elif not title and len(stripped) > 3:
            title = stripped
        if title and author:
            break
    return title, author


# ── main parser ──────────────────────────────────────────────────────────────

def parse_play(text: str) -> PlayDoc:
    """Parse a Gutenberg plain-text play into a PlayDoc tree.

    The parser is intentionally tolerant: preamble (cast lists, dedications,
    etc.) is skipped until the first ACT header; beats before the first SCENE
    are attached to a synthetic "Prologue" scene for the act.
    """
    title, author = _extract_metadata(text)
    play = PlayDoc(title=title, author=author)

    acts = play.acts
    current_act: Optional[Act] = None
    current_scene: Optional[Scene] = None
    current_speaker: Optional[str] = None
    speech_lines: list = []

    def _flush_speech():
        nonlocal current_speaker, speech_lines
        if current_speaker and speech_lines:
            body = "\n".join(speech_lines).strip()
            if body and current_scene is not None:
                current_scene.beats.append(Beat(type="speech", speaker=current_speaker, text=body))
        current_speaker = None
        speech_lines = []

    def _ensure_scene() -> Scene:
        """Attach a synthetic prologue scene to current_act if none exists yet."""
        nonlocal current_scene
        if current_act is None:
            # Should not happen in well-formed plays, but be defensive
            act = Act(name="Act I")
            acts.append(act)
        target = current_act if current_act is not None else acts[-1]
        if current_scene is None or current_scene not in target.scenes:
            sc = Scene(name="Prologue", location="")
            target.scenes.append(sc)
            current_scene = sc
        return current_scene

    lines = text.split("\n")
    in_play = False  # becomes True after first ACT header

    for raw_line in lines:
        line = raw_line.rstrip()

        # ── act header ───────────────────────────────────────────────────────
        m_act = _ACT_RE.match(line)
        if m_act:
            _flush_speech()
            in_play = True
            numeral = m_act.group(1).upper()
            current_act = Act(name=f"Act {numeral}")
            acts.append(current_act)
            current_scene = None
            continue

        if not in_play:
            continue

        # ── scene header ─────────────────────────────────────────────────────
        m_scene = _SCENE_RE.match(line)
        if m_scene:
            _flush_speech()
            numeral = m_scene.group(1).upper()
            location = m_scene.group(2).strip()
            current_scene = Scene(name=f"Scene {numeral}", location=location)
            if current_act is not None:
                current_act.scenes.append(current_scene)
            continue

        # ── blank line ───────────────────────────────────────────────────────
        stripped = line.strip()
        if not stripped:
            # A blank line ends the current speech paragraph; keep speaker for
            # continuation (some Gutenberg plays split long speeches with blanks)
            if speech_lines:
                speech_lines.append("")
            continue

        # ── stage direction ──────────────────────────────────────────────────
        if _is_direction(line):
            _flush_speech()
            sc = _ensure_scene()
            sc.beats.append(Beat(type="direction", speaker=None, text=stripped))
            continue

        # ── speaker label ────────────────────────────────────────────────────
        speaker = _is_speaker(line)
        if speaker:
            _flush_speech()
            _ensure_scene()
            current_speaker = speaker
            speech_lines = []
            continue

        # ── speech text ──────────────────────────────────────────────────────
        if current_speaker is not None:
            # Inline bracket directions within a speech: flush, add direction, resume
            if _BRACKET_DIR_RE.match(line):
                _flush_speech()
                sc = _ensure_scene()
                sc.beats.append(Beat(type="direction", speaker=None, text=stripped))
            else:
                speech_lines.append(stripped)

    _flush_speech()
    return play
