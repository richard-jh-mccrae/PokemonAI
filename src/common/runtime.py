"""The shared agent runtime (ADR-0055): one deployment profile, one Pilot build, one shell.

``PROFILE`` is the deployment truth — the Pilot ctor stays the raw-scoring layer — and
``make_agent(STRATEGY)`` is the whole shell, so each ``main.py`` is one import and one call.
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

# The validated-best deployment config every shipped agent runs: {Pilot ctor flag: value}. Every
# Pilot ctor flag MUST appear here (`tests/agents/test_runtime.py` pins the signature both ways).
PROFILE = {
    "search_budget": 0,
    "posture": True,                # ADR-0026 Read/Posture
    "lethal_verify": True,          # ADR-0030 engine-confirm direct lethal locks
    "lethal_seed_exact": True,      # ADR-0050 exact own deck/prize split seeds the verify
    "planner_key_threat": True,     # ADR-0031 KO-the-key-threat Goal-Ladder rung
    "lethal_family": True,          # ADR-0037 the ONE win-generator family + verify-every-lock
    "lethal_veto": True,            # ADR-0037 replay the verified cascade
    "promote_ko_aware": True,       # KO-aware, boost-inclusive promote pick
    "boost_lethal": True,           # promote-+-damage-boost-Item win tier
    "retreat_enabler_lethal": True,  # tutor/attach a retreat Tool to free a winning retreat into a
                                    # benched attacker (engine-confirmed on lock)
    "disruptor_lock_maneuver": True,  # offensive T2 item-lock retreat-into-Budew (ship-and-refine)
    "matchup_targeting": True,      # ADR-0051 MatchupPlan target-priority spine
    "objectives_race": True,        # ADR-0040 Tier-3 KO Race
    "objectives_path": True,        # ADR-0040 Prize-Path consumers
    "objectives_phases": True,      # ADR-0040 derived advisory phases
    "gamble_lines": True,           # ADR-0039 Tier-2 Gamble rung
    "snipe_prize_redundant": True,  # ADR-0044 Prize-Redundant Target
    "snipe_prize_reach": True,      # a PURE Prize-Path tie-break among subsets tied on turns; never
                                    # changes my_path_turns/race_ahead. OFF = mask-order default.
    "forced_promotion": True,       # ADR-0044 Forced-Promotion Read
    "match_planner_steer": True,    # ADR-0045 S3 Game Plan directs the Turn Goal
    "prize_economy_fetch": True,    # ADR-0048 cheap 1-prize attacker line
    # `evolving_wincon_priority` RETIRED by ADR-0085 Amendment G: the deletion pass removed the rungs
    # whose stand-down it gated, leaving the flag inert.
    "value_model": False,           # ADR-0042 armed-OFF: a learned seam ships after its own A/B
    "ko_target_whiff": True,        # KO-target tiebreak toward the least-replaceable body; a pure
                                    # equal-rank tiebreak that fails OPEN on an unrecognized opponent
    "opp_resource_reads": True,     # sub-prize nudge toward KO/grind lines near their deck-out
    "enabler_item_composer": True,  # the ko_for_prizes composer (min-bound, sub-prize)
    "leaf_hand_value": False,       # ADR-0065 WP-N5b armed-OFF: the LEAF's actionable-resource term
                                    # plus the hand-entangled who's-Active facets. Arms only when the
                                    # leaf-lab bench clears it (a new leaf term can void old guards).
    "copy_top_value": True,         # Issue #289 known-top carry; an unknown top stays fail-closed
    "evolve_value": True,           # the EVOLVE DECIDER (ADR-0070). The rungs it replaced are
                                    # DELETED, so OFF is DEGRADED MODE, not a rollback.
    "deploy_value": True,           # the DEPLOY DECIDER (ADR-0086), owning all THREE bench entry
                                    # points. Every rung it replaces is DELETED — OFF is DEGRADED MODE.
    "attach_value": True,           # the ATTACH DECIDER (ADR-0069). 19 of the 23 baseline_energy
                                    # rungs are DELETED — an EMERGENCY LEVER, never a baseline.
    "promote_retreat_value": True,  # the PROMOTE/RETREAT DECIDER (ADR-0100). Eleven of the twelve
                                    # rungs are DELETED, so OFF is DEGRADED MODE, not a rollback.
    "doom_matched_relax": True,     # behind a γ-matched Brief a worst-case `active_doomed` stands
                                    # only if the CHARGED curve confirms it. RELAX-ONLY; unmatched is
                                    # byte-identical worst-case (ADR-0064 §4: never relax on a guess).
    "recur_fuel_relax": True,       # ADR-0076: quantifies `_doom_recur_fueled`'s all-or-nothing
                                    # relax-block against the real discard-recur reload.
    "scaled_threat_rank": True,     # Issue #213: price threat through the Damage Formula, retiring
                                    # the `_HAND_SIZE_ATTACKER_BOOST` proxy it would double-count.
    "gust_target_slots": True,      # ADR-0076: a `gust_target` kind keep-priced against the real
                                    # per-body `opponent_target_value`, not the flat `deny` tier.
    "deny_strip_delta": True,       # ADR-0078/0084. Armed TOGETHER with `deny_relevance`, never
                                    # alone: its only consumer lives inside `if self.deny_relevance:`,
                                    # and that flag alone leaves the target-pick tie on option order.
    "snipe_relevance": True,        # ADR-0085: the Snipe Relevance scalar DECIDES the DAMAGE
                                    # bench-target select. The six rungs and the MatchupPlan steer are
                                    # DELETED, so OFF is DEGRADED MODE, never a rollback.
    "deny_relevance": True,         # ADR-0080/0093: all three deny surfaces score off the relevance
                                    # read. ⚠️ OFF is DEGRADED MODE, never a rollback — Issue #228
                                    # DELETED the ADR-0062 magnitude oracle this replaced.
    "leaf_followups": False,         # Issue #387: deck opt-in for composer-owned seeded CARD menus
                                    # and leaf-owned multi-picks; Mega Starmie validates first.
}
# `deferred_target_expansion` RETIRED (Issue #446): ADR-0121 armed it off until a consumer existed;
# Issue #386's composer opts in per call, so the flag gated nothing and read as a live kill-switch.

_ENGINE = object()   # sentinel: build the engine-backed seam unless the caller injects one


def build_pilot(strategy, deck, *, params=None, overrides=None,
                stats=_ENGINE, scout=_ENGINE, briefs=_ENGINE) -> Pilot:
    """The one deployed-Pilot build. Each PROFILE flag reads ``params.get(flag, PROFILE[flag])``,
    so overlay/deck params can force any switch (the battle.py A/B lever, ADR-0021)."""
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
    """The whole agent shell. ``deck.csv`` comes from cwd (the harness/grader contract: cwd = the
    bundle dir); the built Pilot stays reachable as ``agent.pilot`` for probes and tools."""
    overrides, params = load_overrides_and_params(strategy.params)
    pilot = build_pilot(strategy, _read_deck(), params=params, overrides=overrides)
    tier = 1 if pilot.search_budget > 0 else 0
    telemetry_on = os.environ.get("AGENT_NO_TELEMETRY") != "1"
    native_telemetry = pilot.strategy.params.get("bellman_turn_planner") is True
    model = OwnCardModel(pilot.deck)   # match-scoped own-card tracker; resolves prizes -> exact deck

    def agent(obs_dict: dict) -> list[int]:
        model.observe(obs_dict)                     # maintain exact own-card model (sound; never raises)
        obs_dict["own_prizes"] = model.prize_export()   # annotate -> Board derives exact deck (None = fall back)
        decision = pilot.explain(obs_dict)          # same choice as decide(); also yields trace
        if telemetry_on:
            emitter = telemetry.emit_native if native_telemetry else telemetry.emit
            emitter(decision, tier=tier)
        return decision.chosen

    agent.pilot = pilot
    return agent
