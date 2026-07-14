"""The shared agent runtime (ADR-0055): one deployment profile, one Pilot build, one shell.

Pre-0055 every agent's ``main.py`` carried a byte-copied ~100-line shell — deck read, config
load, knowledge-seam wiring, an 18-line kill-switch smear, telemetry, the ``agent(obs)``
callable. A flag omitted from one copy silently ran that agent's layer at the ctor default
(the 2026-07-03 dark-planner incident). This module is the one home: ``PROFILE`` is the
deployment truth (the Pilot ctor stays the raw-scoring layer), and ``make_agent(STRATEGY)``
is the whole shell — each ``main.py`` shrinks to importing its Strategy and calling it.
"""
from __future__ import annotations

import os

from common import telemetry
from common.cards import CardFunctions
from common.config import load_overrides_and_params
from common.deck_tracker import OwnCardModel
from common.effects import CardEffects
from common.pilot import Pilot
from common.strategy.general_strategy import GENERAL_STRATEGY
from common.value import ValueModel

# The validated-best deployment config every shipped agent runs: {Pilot ctor flag: value}.
# ON entries are A/B-cleared or user-decided (see each flag's ADR in the ctor's comments);
# armed-off entries ship dark until their own evidence gate clears. Every Pilot ctor flag
# param MUST appear here (tests/agents/test_runtime.py pins the signature both ways) — adding
# a feature means deciding its shipped value ONCE, for every agent at once.
PROFILE = {
    "search_budget": 0,
    "posture": True,                # ADR-0026 Read/Posture
    "lethal_verify": True,          # ADR-0030 engine-confirm direct lethal locks
    "lethal_seed_exact": True,      # ADR-0050 exact own deck/prize split seeds the verify
    "planner_engine_rank": True,    # ADR-0031 engine-sim ranks the Planner's candidates
    "planner_key_threat": True,     # ADR-0031 KO-the-key-threat Goal-Ladder rung
    "lethal_family": True,          # ADR-0037 the ONE win-generator family + verify-every-lock
    "lethal_veto": True,            # ADR-0037 replay the verified cascade
    "promote_ko_aware": True,       # Proposal C: KO-aware, boost-inclusive promote pick
    "boost_lethal": True,           # Proposal B: promote-+-damage-boost-Item win tier
    "retreat_enabler_lethal": True,  # ml f15: tutor/attach a retreat Tool to free a winning
                                    # retreat into a benched attacker (engine-confirmed on lock)
    "disruptor_lock_maneuver": True,  # dragapult f20: offensive T2 item-lock retreat-into-Budew
                                    # (ship-and-refine — kill-switch if its ladder value is weak)
    "matchup_targeting": True,      # ADR-0051 MatchupPlan target-priority spine (supersedes the
                                    # retired ADR-0038 brief_preevo/brief_engine levers)
    "objectives_race": True,        # ADR-0040 Tier-3 KO Race
    "objectives_path": True,        # ADR-0040 Prize-Path consumers
    "objectives_phases": True,      # ADR-0040 derived advisory phases
    "gamble_lines": True,           # ADR-0039 Tier-2 Gamble rung
    "snipe_prize_redundant": True,  # ADR-0044 Prize-Redundant Target (user decision 2026-07-06)
    "forced_promotion": True,       # ADR-0044 Forced-Promotion Read
    "match_planner_steer": True,    # ADR-0045 S3 Game Plan directs the Turn Goal
    "forgo_ko": True,               # ADR-0045 S4 forgo a non-winning KO
    "prize_economy_fetch": True,    # ADR-0048 cheap 1-prize attacker line
    "evolving_wincon_priority": True,  # snipe-the-evolving-threat stand-down (ms 85164131 f22)
    "value_model": False,           # ADR-0042 armed-off: a learned seam ships after its own A/B
    "escalation": False,            # ADR-0043 armed-off: needs search_budget>0
    "ko_target_whiff": True,        # BUILD 1 armed-ON 2026-07-14 (ladder-testing): KO-target tiebreak
                                    # toward the body the opponent is least able to replace (rebuild odds).
                                    # Data-ready (artifact.json ships 122 representative_build dossiers);
                                    # a pure equal-rank tiebreak that fails open on an unrecognized opponent.
    "opp_resource_reads": True,     # BUILD 2 armed-ON 2026-07-14 (ladder-testing): sub-prize nudge toward
                                    # KO/grind lines when the opponent is near deck-out (SOUND deck-out timing)
    "enabler_item_composer": True,  # BUILD 3 armed-ON 2026-07-14 (ladder-testing): ko_for_prizes composer
                                    # (Item-tutor / Rare-Candy → evolve → energy → KO; min-bound, sub-prize)
    "play_accel_lethal": True,      # armed-ON 2026-07-14 ladder-testing: count a play-based accelerator
                                    # (Crispin) as +1 attach in the KO budget; min-bound
}

_ENGINE = object()   # sentinel: build the engine-backed seam unless the caller injects one


def build_pilot(strategy, deck, *, params=None, overrides=None,
                stats=_ENGINE, scout=_ENGINE, briefs=_ENGINE) -> Pilot:
    """The one deployed-Pilot build: PROFILE flags, per-flag overridable through ``params``.

    Args:
        strategy: the deck's Strategy (its ``params`` are the default flag overrides).
        deck: the 60-card decklist.
        params: the already-merged params dict (Strategy + AGENT_OVERLAY, from
            ``load_overrides_and_params``); defaults to ``strategy.params``. Each PROFILE
            flag reads ``params.get(flag, PROFILE[flag])`` — overlay/deck params keep
            forcing any switch (the battle.py A/B lever, ADR-0021).
        overrides: tuned weight overrides (tuned.json, ADR-0018); None = authored seeds.
        stats / scout / briefs: knowledge-seam injection for tests and tools; left at the
            sentinel they build engine-backed exactly as every main.py did — provider warmed
            in the pregame window, Scout over the shipped artifact, Briefs covers-routed.
    """
    merged = dict(strategy.params) if params is None else params
    flags = {k: merged.get(k, v) for k, v in PROFILE.items()}
    # ADR-0042: the profile carries the GATE; only a True gate loads the model (absent-safe).
    flags["value_model"] = ValueModel.load() if flags["value_model"] else None
    if stats is _ENGINE:
        from common.scouting.provider import EngineCardStatProvider
        stats = EngineCardStatProvider()
        stats.warm()   # pregame window: build the engine card/attack tables now, not on turn 1
    if scout is _ENGINE:
        from common.scouting.artifact import load_artifact
        from common.scouting.scout import Scout
        scout = Scout(load_artifact(), provider=stats)
    if briefs is _ENGINE:
        from common.scouting.briefs import load_briefs
        briefs = load_briefs()
    return Pilot(strategy, deck, general_strategy=GENERAL_STRATEGY, overrides=overrides,
                 stats=stats, functions=CardFunctions.load(), effects=CardEffects.load(),
                 scout=scout, briefs=briefs, **flags)


def _read_deck() -> list[int]:
    path = "deck.csv" if os.path.exists("deck.csv") else "/kaggle_simulations/agent/deck.csv"
    with open(path) as fh:
        return [int(x) for x in fh.read().split("\n")[:60]]


def make_agent(strategy):
    """The whole agent shell: ``main.py`` is ``agent = make_agent(STRATEGY)`` and nothing else.

    Resolves (overrides, params) with the optional AGENT_OVERLAY (ADR-0021), reads ``deck.csv``
    from cwd (the harness/grader contract: cwd = the bundle dir), builds the deployed Pilot
    (``build_pilot`` — PROFILE flags, engine-backed seams, provider warmed), and returns the
    1-arg ``agent(obs)`` callable every harness loads and calls. The built Pilot stays
    reachable as ``agent.pilot`` (probe/tool surface). Emits always-on Decision Telemetry
    (ADR-0019; ``AGENT_NO_TELEMETRY=1`` silences it, resolved now, at build)."""
    overrides, params = load_overrides_and_params(strategy.params)
    pilot = build_pilot(strategy, _read_deck(), params=params, overrides=overrides)
    tier = 1 if pilot.search_budget > 0 else 0
    telemetry_on = os.environ.get("AGENT_NO_TELEMETRY") != "1"
    model = OwnCardModel(pilot.deck)   # match-scoped own-card tracker; resolves prizes -> exact deck

    def agent(obs_dict: dict) -> list[int]:
        model.observe(obs_dict)                     # maintain exact own-card model (sound; never raises)
        obs_dict["own_prizes"] = model.prize_export()   # annotate -> Board derives exact deck (None = fall back)
        decision = pilot.explain(obs_dict)          # same choice as decide(); also yields trace
        if telemetry_on:
            telemetry.emit(decision, tier=tier)
        return decision.chosen

    agent.pilot = pilot
    return agent
