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
from common.value import ValueModel
from strategy import STRATEGY


def _read_deck() -> list[int]:
    path = "deck.csv" if os.path.exists("deck.csv") else "/kaggle_simulations/agent/deck.csv"
    with open(path) as fh:
        return [int(x) for x in fh.read().split("\n")[:60]]


# Built once at import (pregame window): eager-load engine-derived tables.
_all_attacks = all_attack()
_attacks = {a.attackId: a.damage for a in _all_attacks}
_attack_costs = {a.attackId: len(a.energies) for a in _all_attacks}
_recoil = {a.attackId: parse_attack_recoil(a.text) for a in _all_attacks}        # ADR-0022 #2
_bench_snipe = {a.attackId: parse_attack_bench_snipe(a.text) for a in _all_attacks}  # ADR-0022 #14
_attack_stats = build_attack_stats(_all_attacks, load_attack_overrides())   # ADR-0032: per-attack
                                                   # effect records — text seeds + engine-audited overrides
                                                   # (subsumes narrow ignores_active_effects feed)
# weight overrides (tuned.json, ADR-0018) + params (Strategy.params, ADR-0019), plus optional
# offline experiment overlay on top for local A/B (env AGENT_OVERLAY; ADR-0021). Inert on grader.
_overrides, _params = load_overrides_and_params(STRATEGY.params)
_provider = EngineCardStatProvider()   # shared by Pilot (stats) and Scout (threat/target resolution)
_scout = Scout(load_artifact(), provider=_provider)   # opponent recognition -> the Read (M2.0/ADR-0026);
                                                      # artifact bundled + load fail-safe to empty -> Posture off
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
    scout=_scout,                                     # opponent recognition -> the Read on Board (ADR-0026)
    briefs=_briefs,                                   # matched Matchup Brief on Board (ADR-0027), covers-routed
    posture=_params.get("posture", True),             # ADR-0026 kill-switch (overlay can force Posture off for A/B)
    lethal_verify=_params.get("lethal_verify", True),  # ADR-0030 kill-switch: engine-confirm direct
    lethal_seed_exact=_params.get("lethal_seed_exact", True),  # ADR-0050 kill-switch: seed the engine
                                                      # verify from the EXACT own deck/prize split (own_prizes)
                                                      # vs the id-sorted decklist prefix that hid the high-id band
                                                      # lethal locks (A/B-cleared 2026-07-02; overlay can force off)
    planner_engine_rank=_params.get("planner_engine_rank", True),  # ADR-0031 kill-switch: engine-sim
                                                      # ranks the Planner's candidates (A/B-cleared 2026-07-02)
    planner_key_threat=_params.get("planner_key_threat", True),  # ADR-0031 kill-switch: the
                                                      # KO-the-key-threat ladder rung (A/B-cleared 2026-07-02)
    lethal_family=_params.get("lethal_family", True),  # ADR-0037 kill-switch: the ONE win-generator
                                                      # family + verify-every-lock (A/B-cleared 2026-07-03:
                                                      # 2000 games 51%, 0 crashes)
    lethal_veto=_params.get("lethal_veto", True),     # ADR-0037 stage-3 kill-switch: replay the verified
                                                      # cascade (A/B-cleared 2026-07-03: 2000 games 52%,
                                                      # 0 crashes)
    brief_preevo=_params.get("brief_preevo", True),  # ADR-0038 kill-switch: Brief fragile_preevo lever
                                                      # (A/B-cleared 2026-07-04: 68% vs 69% baseline vs
                                                      # mega_lucario, mirror 52% — non-degradation + neutral)
    brief_engine=_params.get("brief_engine", False),  # ADR-0038 kill-switch: Brief engine lever, gated on
                                                      # opp_is_engine_dependent. DEFAULT OFF: the stress leg
                                                      # priced a WRONG assertion at ~4% (46%, CI 43-49) — arms
                                                      # via the first real true-asserting Brief's own A/B
    objectives_race=_params.get("objectives_race", True),  # ADR-0040 kill-switch: Tier-3 KO Race —
                                                      # wall attacks priced by best min-turn SEQUENCE
                                                      # (chip included), not the biggest single hit
    objectives_path=_params.get("objectives_path", True),  # ADR-0040 kill-switch: Prize-Path consumers
                                                      # (snipe-on-the-path, bench denial, planner bump)
    objectives_phases=_params.get("objectives_phases", True),  # ADR-0040 kill-switch: derived ADVISORY
                                                      # phases (STABILIZE/CLOSE + baseline_phases bands)
    gamble_lines=_params.get("gamble_lines", True),   # ADR-0039 kill-switch: Tier-2 Gamble rung —
                                                      # refresh-first when exact-odds EV beats the held line
    snipe_prize_redundant=_params.get("snipe_prize_redundant", True),  # ADR-0044 kill-switch: Prize-Redundant
                                                      # Target snipe suppression (deny the 2nd Mega). DEFAULT ON
                                                      # 2026-07-06 (user decision — verified via ladder-match
                                                      # corrections, not an A/B: mega_lucario too weak for the leg)
    forced_promotion=_params.get("forced_promotion", True),  # ADR-0044 kill-switch: Forced-Promotion Read
                                                      # (pre-chip the ready wincon they'll promote). DEFAULT ON 2026-07-06
    match_planner_steer=_params.get("match_planner_steer", True),  # ADR-0045 S3: Game Plan directs the Turn
                                                      # Goal (sub-prize bias). DEFAULT ON 2026-07-07 — matured via ladder
    forgo_ko=_params.get("forgo_ko", True),           # ADR-0045 S4: forgo a non-winning KO ('don't wake the
                                                      # giant') under the tight sound gate. DEFAULT ON 2026-07-07 (riskiest)
    value_model=(ValueModel.load() if _params.get("value_model", False) else None),  # ADR-0042 Tier-5:
                                                      # learned leaf; DEFAULT OFF (a learned seam ships
                                                      # only after its own ladder A/B) + absent-safe
    escalation=_params.get("escalation", False),      # ADR-0043 Tier-6: depth-2 tree on a close attack
                                                      # tie (needs search_budget>0); DEFAULT OFF
)
_TIER = 1 if _pilot.search_budget > 0 else 0
_TELEMETRY = os.environ.get("AGENT_NO_TELEMETRY") != "1"     # always-on Decision Telemetry (ADR-0019)
_MODEL = OwnCardModel(_pilot.deck)   # match-scoped own-card tracker; resolves prizes -> exact deck


def agent(obs_dict: dict) -> list[int]:
    _MODEL.observe(obs_dict)                    # maintain exact own-card model (sound; never raises)
    obs_dict["own_prizes"] = _MODEL.prize_export()   # annotate -> Board derives exact deck (None = fall back)
    decision = _pilot.explain(obs_dict)        # same choice as decide(); also yields trace
    if _TELEMETRY:
        telemetry.emit(decision, tier=_TIER)
    return decision.chosen
