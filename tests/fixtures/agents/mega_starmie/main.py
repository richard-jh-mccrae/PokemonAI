"""mega_starmie — Kaggle agent hook. Wires deck.csv + strategy.py into the shared Pilot.

Thin by design (ADR-0008): all decision logic lives in `common/`; the deck contributes
only its `deck.csv` and declarative `strategy.py`.
"""
import os

from cg.api import all_attack
from common.cards import CardFunctions
from common.pilot import Pilot
from common.scouting.provider import EngineCardStatProvider
from strategy import STRATEGY


def _read_deck() -> list[int]:
    path = "deck.csv" if os.path.exists("deck.csv") else "/kaggle_simulations/agent/deck.csv"
    with open(path) as fh:
        return [int(x) for x in fh.read().split("\n")[:60]]


# Built once at import (the pregame window): eager-load the engine-derived tables.
_attacks = {a.attackId: a.damage for a in all_attack()}
_pilot = Pilot(
    STRATEGY,
    _read_deck(),
    stats=EngineCardStatProvider(),
    functions=CardFunctions.load(),
    attacks=_attacks,
    search_budget=0,
)


def agent(obs_dict: dict) -> list[int]:
    return _pilot.decide(obs_dict)
