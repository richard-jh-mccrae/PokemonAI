"""Scouting: recognize the opponent's deck and produce the Read.

See ../CONTEXT.md for the glossary and docs/scouting.md for the design. Public
surface: ``Scout``, ``Read`` (+ ``Intel`` / ``EvoPath``), ``load_artifact`` /
``Artifact``, and the card-stat providers. Importing this package never loads the
native engine.
"""
from .artifact import Artifact, load_artifact
from .matchup import matchup_favorability
from .provider import CardStat, DictCardStatProvider, EngineCardStatProvider
from .read import EvoPath, Intel, Read
from .scout import Scout

__all__ = [
    "Scout", "Read", "Intel", "EvoPath",
    "Artifact", "load_artifact", "matchup_favorability",
    "CardStat", "DictCardStatProvider", "EngineCardStatProvider",
]
