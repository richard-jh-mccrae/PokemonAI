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
    "snipe_prize_reach": True,      # snipe-targeting grill armed-ON 2026-07-21 (dev-window): a PURE
                                    # Prize-Path tie-break — among prize-completing subsets tied on
                                    # turns, the +1 lands on the bench body my repeatable snipe rider
                                    # finishes soonest (rides free alongside my main KOs), not the
                                    # mask-order default (83667237-107: Makuhita over Lunatone). Never
                                    # changes my_path_turns/race_ahead; kill-switch → mask-order default.
    "forced_promotion": True,       # ADR-0044 Forced-Promotion Read
    "match_planner_steer": True,    # ADR-0045 S3 Game Plan directs the Turn Goal
    "forgo_ko": True,               # ADR-0045 S4 forgo a non-winning KO
    "prize_economy_fetch": True,    # ADR-0048 cheap 1-prize attacker line
    "evolving_wincon_priority": True,  # snipe-the-evolving-threat stand-down (ms 85164131 f22)
    "value_model": False,           # ADR-0042 armed-off: a learned seam ships after its own A/B
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
    "discard_keep_value": True,     # ADR-0065 seam-D armed-ON 2026-07-19 (ladder-testing): the
                                    # card-worth equation DECIDES the forced discard (keep_cost + pitch
                                    # term + the gates) in place of the tuned `_DISCARD` ladder.
                                    # Shadow-validated 11/12 vs the ladder's 9/12 on the corpus (+ the
                                    # user-endorsed 12th). In-place ladder A/B vs the flag-off ladder;
                                    # kill-switch if its ladder value is weak (the develop_rollout precedent).
                                    # SUPERSEDED as the discard decider by `needs_keep_value` below when
                                    # that is ON; stays the fallback + the gamble/refresh keep-value spine.
    "needs_keep_value": True,       # ADR-0065 WP-N4 armed-ON 2026-07-20 (dev-window ruling): the
                                    # keep-value v2 NEEDS-ASSIGNMENT (`_needs_v2`) DECIDES the forced
                                    # discard in place of v1's per-card gate composition — the global
                                    # exact-assignment marginal (`eq2_pick`), hedged at v1's post-gate
                                    # keep so it never prices below the shipped decider. The per-family
                                    # swap for the cleared discard family: agree_v2 12/12 vs v1 on the
                                    # replayable discard corpus, and the duplicate-pair set case flips
                                    # WITHOUT a new gate (v1's naivety, structurally gone). Kill-switch
                                    # (the develop_rollout precedent); OFF falls back to v1.
    "leaf_hand_value": False,       # ADR-0065 WP-N5b armed-OFF 2026-07-20: the develop-rung LEAF's
                                    # actionable-resource term — readiness consumes the needs module
                                    # (the held-hand slot coverage), the board-state-valuation fold.
                                    # Since the who's-Active build (thread 3, 2026-07-20) this flag ALSO
                                    # arms the hand-entangled who's-Active facets: the Active-quality
                                    # micro-credit (`_READINESS_MOBILITY_W`, mobility/energized-preevo)
                                    # and the switch-in-hand promotion ease — measured hand-blind they
                                    # trade shared-top frames whose labels pivot on hidden-hand context.
                                    # (The board-fact promotion-ease LIFT ships unconditionally.)
                                    # Gated on the leaf-lab bench (SOLE-top / distinct-values / Gate 0);
                                    # arms only when the bench clears it — a new positive leaf term can
                                    # void guards sized against the old scale (the grill's builder-gotcha).
    "develop_rollout": True,        # develop-rung armed-ON 2026-07-15 (ladder-testing): the within-turn
                                    # rollout rung — cost-measured affordable + crash-safe (60 games, 0
                                    # crashes; ~1s/game). In-place ladder A/B vs the prior flag-off
                                    # submission. Kill-switch if its ladder value is weak. Needs the live
                                    # search token, so it no-ops (defers) on offline correction retests
    "evolve_value": True,           # the EVOLVE DECIDER, shipped ON 2026-07-25 (ADR-0070, #140): the body-substituted
                                    # deploy delta + the odds-priced income. The sweep's 10 flips were
                                    # user-ruled (6 FIX, 0 regression) and the rungs it replaced are
                                    # DELETED, so OFF is DEGRADED MODE, not a rollback: evolve
                                    # endorsements go silent and only the _PLAY-side Gate speaks.
    "attach_value": True,           # the ATTACH DECIDER, shipped ON 2026-07-25 (ADR-0069, the FIRST
                                    # no-shadow decider swap): the axes-sum marginal (`_attach_value`)
                                    # IS the energy-attach decision — attack axis (tonight's
                                    # counterfactual under the full Attach Budget / typed slot-fraction
                                    # build / accel routing) + Retreat Equity + Ability Fuel −
                                    # evaporation, per-axis gated, scaled by `_ATTACH_VALUE_SCALE`.
                                    # Nineteen of the 23 baseline_energy rungs are DELETED, so this is
                                    # an EMERGENCY LEVER, not a comparison baseline: OFF is documented
                                    # degraded mode (attach endorsements silent, only the three
                                    # structure rungs speak), never a rollback to the deleted pile.
    "doom_matched_relax": True,     # doom-shadow grill armed-ON 2026-07-23: behind a γ-matched Brief
                                    # (and no discard-recur fuel) a worst-case `active_doomed` cry
                                    # stands only if the CHARGED Threat-Clock curve confirms it
                                    # (`_DOOM_CHARGED`: manual + one generic supporter-accel attach,
                                    # Ignition burst on Evolutions). RELAX-ONLY — clears phantom doom,
                                    # never adds one. Relaxes exactly the ruled-B disagreement frames
                                    # (bare Terapagos / 0e Archaludon); every ruled-C frame
                                    # (Hammer-lanche density, ×2-weak Mind Bend, 1e Metal Defender)
                                    # stays doomed. Unmatched → byte-identical worst-case (ADR-0064
                                    # §4: never relax on a guess)
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
