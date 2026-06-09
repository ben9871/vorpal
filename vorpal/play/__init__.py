"""vorpal.play — theatrical mode: play ingestion and multi-voice dramatization."""

from .models import PlayDoc, Act, Scene, Beat
from .parser import parse_play
from .fetcher import fetch_play, CATALOGUE
from .characters import Character, extract_cast
from .casting import CastSheet, assign_voices, apply_overrides, castable_voices

__all__ = [
    "PlayDoc", "Act", "Scene", "Beat", "parse_play", "fetch_play", "CATALOGUE",
    "Character", "extract_cast",
    "CastSheet", "assign_voices", "apply_overrides", "castable_voices",
]
