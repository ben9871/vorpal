"""vorpal.play — theatrical mode: play ingestion and multi-voice dramatization."""

from .models import PlayDoc, Act, Scene, Beat
from .parser import parse_play
from .fetcher import fetch_play, CATALOGUE
from .characters import Character, extract_cast
from .casting import CastSheet, assign_voices, apply_overrides, castable_voices
from .synth_router import route_chunks, synthesize_routed_chunks
from .chapters import build_play_chapters
from .pipeline import build_play, load_play

__all__ = [
    "build_play", "load_play",
    "PlayDoc", "Act", "Scene", "Beat", "parse_play", "fetch_play", "CATALOGUE",
    "Character", "extract_cast",
    "CastSheet", "assign_voices", "apply_overrides", "castable_voices",
    "route_chunks", "synthesize_routed_chunks",
    "build_play_chapters",
]
