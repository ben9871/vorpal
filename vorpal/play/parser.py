"""Plain-text play parser targeting Gutenberg Shakespeare format.

After the initial parse, a second pass applies emotion_hint tone tags to
speech beats that follow an emotion-hint stage direction (Phase 33 wiring).
The directions module is imported lazily to keep the dependency optional
during unit-testing of the parser alone.


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

# Wilde convention (Earnest, PG #844): "FIRST ACT" / "SECOND ACT" headers and
# a bare "SCENE" header with the location prose on the following lines.
_ACT_WORD_RE = re.compile(
    r"^(FIRST|SECOND|THIRD|FOURTH|FIFTH) ACT\.?\s*$")
_ACT_WORD_TO_NUMERAL = {
    "FIRST": "I", "SECOND": "II", "THIRD": "III",
    "FOURTH": "IV", "FIFTH": "V",
}
_SCENE_BARE_RE = re.compile(r"^SCENE\.?\s*$")

# Cast-list heading. Some editions place it AFTER the contents block (whose
# "ACT I"… lines have already flipped the parser into the play body), so the
# personae entries ("MACBETH, General in the King's Army.") would otherwise
# parse as speakers with speeches. Seeing this heading exits play-body mode
# until the next real ACT header.
_PERSONAE_RE = re.compile(
    r"^(dramatis person|persons of the play|characters in the play)",
    re.IGNORECASE,
)

# Speaker label: ALL-CAPS word(s) (letters, spaces, hyphens, apostrophes),
# optionally followed by a period, alone on the line.
_SPEAKER_RE = re.compile(r"^([A-Z][A-Z\s\-\']{1,50})\.?\s*$")

# Speaker label with an inline direction: "CLOWN. [_sings._]" — the speaker
# starts speaking AND a direction (usually a song cue) attaches to the turn.
_SPEAKER_INLINE_DIR_RE = re.compile(r"^([A-Z][A-Z\s\-\']{1,50})\.\s*(\[.+\])\s*$")

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
    if _ACT_WORD_RE.match(stripped) or _SCENE_BARE_RE.match(stripped):
        return None
    # "ACT DROP" (Wilde end-of-act marker) is staging, not a character
    if stripped.rstrip(".") == "ACT DROP":
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
    orphan_lines: list = []        # prose with no speaker → direction beat
    direction_buffer: Optional[list] = None  # multi-line [bracketed] direction
    song_open = False              # inside an _italic_ sung block of a speech

    def _flush_speech():
        nonlocal current_speaker, speech_lines, song_open
        song_open = False
        if current_speaker and speech_lines:
            body = "\n".join(speech_lines).strip()
            if body and current_scene is not None:
                current_scene.beats.append(Beat(type="speech", speaker=current_speaker, text=body))
        current_speaker = None
        speech_lines = []

    def _flush_orphans():
        # Scene-description prose (Wilde: the paragraph after a bare SCENE
        # header) becomes a direction beat — body text is never dropped.
        nonlocal orphan_lines
        if orphan_lines:
            text = " ".join(orphan_lines).strip()
            if text:
                sc = _ensure_scene()
                sc.beats.append(
                    Beat(type="direction", speaker=None, text=text))
        orphan_lines = []

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
        stripped = line.strip()

        # ── multi-line [bracketed] direction continuation ────────────────────
        if direction_buffer is not None:
            if stripped:
                direction_buffer.append(stripped)
            if stripped.endswith("]"):
                sc = _ensure_scene()
                sc.beats.append(Beat(type="direction", speaker=None,
                                     text=" ".join(direction_buffer)))
                direction_buffer = None
            continue

        # ── cast-list heading: leave play-body mode until the next ACT ──────
        if _PERSONAE_RE.match(stripped):
            _flush_speech()
            _flush_orphans()
            in_play = False
            current_scene = None
            continue

        # ── act header ───────────────────────────────────────────────────────
        m_act = _ACT_RE.match(line)
        m_act_word = _ACT_WORD_RE.match(stripped) if not m_act else None
        if m_act or m_act_word:
            _flush_speech()
            _flush_orphans()
            in_play = True
            if m_act:
                numeral = m_act.group(1).upper()
            else:
                numeral = _ACT_WORD_TO_NUMERAL[m_act_word.group(1)]
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
            _flush_orphans()
            numeral = m_scene.group(1).upper()
            location = m_scene.group(2).strip()
            current_scene = Scene(name=f"Scene {numeral}", location=location)
            if current_act is not None:
                current_act.scenes.append(current_scene)
            continue

        # Wilde: bare "SCENE" header, location prose follows as a direction
        if _SCENE_BARE_RE.match(stripped):
            _flush_speech()
            _flush_orphans()
            n = (len(current_act.scenes) + 1) if current_act else 1
            current_scene = Scene(name=f"Scene {n}", location="")
            if current_act is not None:
                current_act.scenes.append(current_scene)
            continue

        # ── blank line ───────────────────────────────────────────────────────
        if not stripped:
            # A blank line ends the current speech paragraph; keep speaker for
            # continuation (some Gutenberg plays split long speeches with blanks)
            if speech_lines:
                speech_lines.append("")
            _flush_orphans()
            continue

        # ── sung/italic lines inside a speech ────────────────────────────────
        # Songs are indented like directions but wrapped in _underscores_
        # ("  _O mistress mine, where are you roaming?"). They are the
        # character singing — speech content, never dropped as a direction.
        if current_speaker is not None and _INDENT_RE.match(line) and (
                stripped.startswith("_") or song_open):
            if stripped.count("_") % 2 == 1:
                song_open = not song_open
            speech_lines.append(stripped.strip("_"))
            continue

        # ── stage direction ──────────────────────────────────────────────────
        if _is_direction(line):
            _flush_speech()
            _flush_orphans()
            sc = _ensure_scene()
            sc.beats.append(Beat(type="direction", speaker=None, text=stripped))
            continue

        # Multi-line bracketed direction opens here (Wilde: "[Lane is
        # arranging … \n … enters.]") — buffer until the closing bracket
        if stripped.startswith("[") and "]" not in stripped:
            _flush_speech()
            _flush_orphans()
            direction_buffer = [stripped]
            continue

        # ── speaker label with inline direction: "CLOWN. [_sings._]" ────────
        m_inline = _SPEAKER_INLINE_DIR_RE.match(stripped)
        if m_inline and not _HAS_LOWER_RE.search(m_inline.group(1)):
            _flush_speech()
            _flush_orphans()
            sc = _ensure_scene()
            sc.beats.append(Beat(type="direction", speaker=None,
                                 text=m_inline.group(2)))
            current_speaker = m_inline.group(1).strip()
            speech_lines = []
            continue

        # ── speaker label ────────────────────────────────────────────────────
        speaker = _is_speaker(line)
        if speaker:
            _flush_speech()
            _flush_orphans()
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
        else:
            # Orphan prose (no speaker active): scene descriptions, epilogue
            # text — collected into a direction beat, never silently dropped
            orphan_lines.append(stripped)

    _flush_speech()
    _flush_orphans()
    _drop_speechless_acts(play)
    _apply_emotion_hints(play)
    return play


def _drop_speechless_acts(play: PlayDoc) -> None:
    """Drop acts containing no speech beats.

    Gutenberg editions with a plain-text Contents block ("ACT I" at column 0
    followed by mixed-case "Scene I. …" lines) produce phantom acts from the
    TOC — they hold at most orphan-direction beats, never speech. A real act
    with zero speeches isn't narratable either way.
    """
    play.acts[:] = [
        act for act in play.acts
        if any(b.type == "speech" for sc in act.scenes for b in sc.beats)
    ]


def _apply_emotion_hints(play: PlayDoc) -> None:
    """Post-parse pass: propagate emotion_hint tone tags to following speech beats.

    A speech beat that immediately follows an emotion-hint direction inherits
    the tone tag from that direction. Only the immediately following speech is
    tagged; subsequent speeches reset to no hint unless preceded by another
    direction.
    """
    from .directions import classify_direction, extract_emotion_hint

    for act in play.acts:
        for scene in act.scenes:
            pending_hint: Optional[str] = None
            for beat in scene.beats:
                if beat.type == "direction":
                    kind = classify_direction(beat.text)
                    if kind == "emotion_hint":
                        pending_hint = extract_emotion_hint(beat.text)
                    else:
                        pending_hint = None
                elif beat.type == "speech":
                    if pending_hint is not None:
                        beat.tone_hint = pending_hint
                    pending_hint = None
