"""mega_starmie — Kaggle agent hook. Emits always-on Decision Telemetry (ADR-0019;
AGENT_NO_TELEMETRY=1 silences it)."""

import os

from cg.api import all_attack
from common import telemetry
from common.cards import CardFunctions
from common.effects import CardEffects
from common.config import load_overrides_and_params
from common.deck_tracker import OwnCardModel
from common.strategy.general_strategy import GENERAL_STRATEGY
from common.pilot import Pilot
from common.scouting.provider import (
    EngineCardStatProvider, build_attack_stats, load_attack_overrides,
    parse_attack_bench_snipe, parse_attack_recoil)
from common.scouting.scout import Scout
from common.scouting.artifact import load_artifact
from common.scouting.briefs import load_briefs
from strategy import STRATEGY


def _read_deck() -> list[int]:
    path = "deck.csv" if os.path.exists("deck.csv") else "/kaggle_simulations/agent/deck.csv"
    with open(path) as fh:
        return [int(x) for x in fh.read().split("\n")[:60]]


# Built once at import (the pregame window): eager-load the engine-derived tables.
_all_attacks = all_attack()
_attacks = {a.attackId: a.damage for a in _all_attacks}
_attack_costs = {a.attackId: len(a.energies) for a in _all_attacks}
_recoil = {a.attackId: parse_attack_recoil(a.text) for a in _all_attacks}        # ADR-0022 #2
_bench_snipe = {a.attackId: parse_attack_bench_snipe(a.text) for a in _all_attacks}  # ADR-0022 #14
_attack_stats = build_attack_stats(_all_attacks, load_attack_overrides())   # ADR-0032: per-attack
                                                   # effect records — text seeds + engine-audited overrides
                                                   # (subsumes the narrow ignores_active_effects feed)
# weight overrides (tuned.json, ADR-0018) + params (Strategy.params, ADR-0019), with an optional
# offline experiment overlay layered on top for local A/B (env AGENT_OVERLAY; ADR-0021). Inert on the grader.
_overrides, _params = load_overrides_and_params(STRATEGY.params)
_provider = EngineCardStatProvider()   # shared by the Pilot (stats) and the Scout (threat/target resolution)
_scout = Scout(load_artifact(), provider=_provider)   # opponent recognition -> the Read (M2.0/ADR-0026);
                                                      # artifact is bundled + load is fail-safe to empty -> Posture off
_briefs = load_briefs()   # hand-authored Matchup Briefs (ADR-0027); covers-routed onto Board, empty -> inert
_pilot = Pilot(
    STRATEGY,
    _read_deck(),
    general_strategy=GENERAL_STRATEGY,
    overrides=_overrides,
    stats=_provider,
    functions=CardFunctions.load(),
    effects=CardEffects.load(),                       # ADR-0032 Effect Clauses (heal amounts/riders)
    attacks=_attacks,
    attack_costs=_attack_costs,
    recoil=_recoil,
    bench_snipe=_bench_snipe,
    attack_stats=_attack_stats,
    search_budget=_params.get("search_budget", 0),   # Tier from params (Strategy default or overlay; ADR-0019/0021)
    scout=_scout,                                     # opponent recognition → the Read on Board (ADR-0026)
    briefs=_briefs,                                   # matched Matchup Brief on Board (ADR-0027), covers-routed
    posture=_params.get("posture", True),             # ADR-0026 kill-switch (overlay can force Posture off for A/B)
)
_TIER = 1 if _pilot.search_budget > 0 else 0
_TELEMETRY = os.environ.get("AGENT_NO_TELEMETRY") != "1"     # always-on Decision Telemetry (ADR-0019)
_MODEL = OwnCardModel(_pilot.deck)   # match-scoped own-card tracker; resolves prizes -> exact deck


def agent(obs_dict: dict) -> list[int]:
    _MODEL.observe(obs_dict)                    # maintain the exact own-card model (sound; never raises)
    obs_dict["own_prizes"] = _MODEL.prize_export()   # annotate -> Board derives the exact deck (None = fall back)
    decision = _pilot.explain(obs_dict)        # same choice as decide(); also yields the trace
    if _TELEMETRY:
        telemetry.emit(decision, tier=_TIER)
    return decision.chosen
