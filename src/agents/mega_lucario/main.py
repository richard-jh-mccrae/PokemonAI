"""mega_lucario — Kaggle agent hook. Emits always-on Decision Telemetry (ADR-0019;
AGENT_NO_TELEMETRY=1 silences it)."""

import os

from cg.api import all_attack
from common import telemetry
from common.cards import CardFunctions
from common.config import load_overrides_and_params
from common.general_strategy import GENERAL_STRATEGY
from common.pilot import Pilot
from common.scouting.provider import (
    EngineCardStatProvider, parse_attack_bench_snipe, parse_attack_recoil)
from strategy import STRATEGY


def _read_deck() -> list[int]:
    path = "deck.csv" if os.path.exists("deck.csv") else "/kaggle_simulations/agent/deck.csv"
    with open(path) as fh:
        return [int(x) for x in fh.read().split("\n")[:60]]


# Built once at import (the pregame window): eager-load the engine-derived tables.
_all_attacks = all_attack()
_attacks = {a.attackId: a.damage for a in _all_attacks}
_attack_costs = {a.attackId: len(a.energies) for a in _all_attacks}
_recoil = {a.attackId: parse_attack_recoil(a.text) for a in _all_attacks}        # ADR-0022 #2 (Wild Press 70)
_bench_snipe = {a.attackId: parse_attack_bench_snipe(a.text) for a in _all_attacks}  # ADR-0022 #14
# weight overrides (tuned.json, ADR-0018) + params (Strategy.params, ADR-0019), with an optional
# offline experiment overlay layered on top for local A/B (env AGENT_OVERLAY; ADR-0021). Inert on the grader.
_overrides, _params = load_overrides_and_params(STRATEGY.params)
_pilot = Pilot(
    STRATEGY,
    _read_deck(),
    general_strategy=GENERAL_STRATEGY,
    overrides=_overrides,
    stats=EngineCardStatProvider(),
    functions=CardFunctions.load(),
    attacks=_attacks,
    attack_costs=_attack_costs,
    recoil=_recoil,
    bench_snipe=_bench_snipe,
    search_budget=_params.get("search_budget", 0),   # Tier from params (Strategy default or overlay; ADR-0019/0021)
)
_TIER = 1 if _pilot.search_budget > 0 else 0
_TELEMETRY = os.environ.get("AGENT_NO_TELEMETRY") != "1"     # always-on Decision Telemetry (ADR-0019)


def agent(obs_dict: dict) -> list[int]:
    decision = _pilot.explain(obs_dict)        # same choice as decide(); also yields the trace
    if _TELEMETRY:
        telemetry.emit(decision, tier=_TIER)
    return decision.chosen
