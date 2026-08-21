"""Offline scouting artifacts and card-stat adapters used by the Opponent Model."""
from .artifact import Artifact, load_artifact
from .provider import CardStat, DictCardStatProvider, EngineCardStatProvider

__all__ = [
    "Artifact", "load_artifact",
    "CardStat", "DictCardStatProvider", "EngineCardStatProvider",
]
