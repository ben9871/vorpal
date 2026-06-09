"""vorpal.play — theatrical mode: play ingestion and multi-voice dramatization."""

from .models import PlayDoc, Act, Scene, Beat
from .parser import parse_play
from .fetcher import fetch_play, CATALOGUE

__all__ = ["PlayDoc", "Act", "Scene", "Beat", "parse_play", "fetch_play", "CATALOGUE"]
