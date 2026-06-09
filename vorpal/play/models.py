"""Data model for a parsed stage play."""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Beat:
    """A single unit of play content: a speech or a stage direction."""
    type: str          # 'speech' | 'direction'
    speaker: Optional[str]  # character name for speeches; None for directions
    text: str
    tone_hint: Optional[str] = None  # set by Phase 33 emotion extractor

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "speaker": self.speaker,
            "text": self.text,
            "tone_hint": self.tone_hint,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Beat":
        return cls(
            type=d["type"],
            speaker=d.get("speaker"),
            text=d["text"],
            tone_hint=d.get("tone_hint"),
        )


@dataclass
class Scene:
    """A scene within an act."""
    name: str       # e.g. "Scene I"
    location: str   # e.g. "Elsinore. A platform before the castle."
    beats: List[Beat] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "location": self.location,
            "beats": [b.to_dict() for b in self.beats],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Scene":
        s = cls(name=d["name"], location=d.get("location", ""))
        s.beats = [Beat.from_dict(b) for b in d.get("beats", [])]
        return s


@dataclass
class Act:
    """An act containing one or more scenes."""
    name: str   # e.g. "Act I"
    scenes: List[Scene] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "scenes": [s.to_dict() for s in self.scenes],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Act":
        a = cls(name=d["name"])
        a.scenes = [Scene.from_dict(s) for s in d.get("scenes", [])]
        return a


@dataclass
class PlayDoc:
    """A fully parsed stage play."""
    title: str
    author: str
    acts: List[Act] = field(default_factory=list)

    @property
    def speakers(self) -> List[str]:
        """All unique speaker names across the play."""
        seen: set = set()
        result = []
        for act in self.acts:
            for scene in act.scenes:
                for beat in scene.beats:
                    if beat.type == "speech" and beat.speaker and beat.speaker not in seen:
                        seen.add(beat.speaker)
                        result.append(beat.speaker)
        return result

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "author": self.author,
            "acts": [a.to_dict() for a in self.acts],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PlayDoc":
        p = cls(title=d["title"], author=d.get("author", ""))
        p.acts = [Act.from_dict(a) for a in d.get("acts", [])]
        return p
