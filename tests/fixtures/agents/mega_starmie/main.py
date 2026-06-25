"""mega_starmie — Kaggle agent hook. Emits always-on Decision Telemetry (ADR-0019;
AGENT_NO_TELEMETRY=1 silences it)."""

import json
import os

from cg.api import all_attack
from common import telemetry
from common.cards import CardFunctions
from common.general_strategy import GENERAL_STRATEGY
from common.pilot import Pilot
from common.scouting.provider import EngineCardStatProvider
from strategy import STRATEGY


def _read_deck() -> list[int]:
    path = "deck.csv" if os.path.exists("deck.csv") else "/kaggle_simulations/agent/deck.csv"
    with open(path) as fh:
        return [int(x) for x in fh.read().split("\n")[:60]]


def _read_tuned() -> dict:
    """Machine weight overrides ({hyp_id: weight}) the Tuner shipped, if any (ADR-0018)."""
    for path in ("tuned.json", "/kaggle_simulations/agent/tuned.json"):
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
    return {}


# Built once at import (the pregame window): eager-load the engine-derived tables.
_all_attacks = all_attack()
_attacks = {a.attackId: a.damage for a in _all_attacks}
_attack_costs = {a.attackId: len(a.energies) for a in _all_attacks}
_pilot = Pilot(
    STRATEGY,
    _read_deck(),
    general_strategy=GENERAL_STRATEGY,
    overrides=_read_tuned(),
    stats=EngineCardStatProvider(),
    functions=CardFunctions.load(),
    attacks=_attacks,
    attack_costs=_attack_costs,
    search_budget=STRATEGY.params.get("search_budget", 0),   # Tier declared in Strategy (ADR-0019)
)
_TIER = 1 if _pilot.search_budget > 0 else 0
_TELEMETRY = os.environ.get("AGENT_NO_TELEMETRY") != "1"     # always-on Decision Telemetry (ADR-0019)


def agent(obs_dict: dict) -> list[int]:
    decision = _pilot.explain(obs_dict)        # same choice as decide(); also yields the trace
    if _TELEMETRY:
        telemetry.emit(decision, tier=_TIER)
    return decision.chosen
