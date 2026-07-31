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
    # `evolving_wincon_priority` was RETIRED by ADR-0085 Amendment G (Issue #188). It gated the
    # stand-down that kept the current-attacker rungs from burying `snipe-the-evolving-threat`;
    # the deletion pass removed those rungs, leaving the flag inert — it changed no pick on the
    # ms 85164131 f22 CRITICAL it exists for, with the scalar reaching Staryu either way.
    "value_model": False,           # ADR-0042 armed-off: a learned seam ships after its own A/B
    "ko_target_whiff": True,        # BUILD 1 armed-ON 2026-07-14 (ladder-testing): KO-target tiebreak
                                    # toward the body the opponent is least able to replace (rebuild odds).
                                    # Data-ready (artifact.json ships 122 representative_build dossiers);
                                    # a pure equal-rank tiebreak that fails open on an unrecognized opponent.
    "opp_resource_reads": True,     # BUILD 2 armed-ON 2026-07-14 (ladder-testing): sub-prize nudge toward
                                    # KO/grind lines when the opponent is near deck-out (SOUND deck-out timing)
    "enabler_item_composer": True,  # BUILD 3 armed-ON 2026-07-14 (ladder-testing): ko_for_prizes composer
                                    # (Item-tutor / Rare-Candy → evolve → energy → KO; min-bound, sub-prize)
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
                                    # submission. Kill-switch if its ladder value is weak.
                                    # ⚠ It does NOT "no-op on offline correction retests" as this comment
                                    # claimed until 2026-07-27 (#160 caught the claim, #178 the damage):
                                    # the 5 seeded correction fixtures DO carry `search_begin_input`
                                    # (ADR-0050), so the rung fires on them and its pick was decided by
                                    # the engine's shuffle. Since #178 it defers whenever ANY candidate's
                                    # sim rode that shuffle, so a retest is reproducible again.
    "leaf_option_equivalence": True,  # ADR-0091 (Issue #247), ON at build: options a board cannot
                                    # tell apart are ONE decision, so the develop rung sims one
                                    # representative per Option Equivalence Class and fans the class
                                    # MAXIMUM out to every member. ON rather than armed-off because this
                                    # is not a new positive leaf term awaiting ladder evidence (the
                                    # `leaf_hand_value` shape) — it DELETES an inconsistency, and the
                                    # corrected value is one the simulator itself proved reachable:
                                    # `81903490|0|decision|49` scored 1167.0 / 95.4 / 95.4 on three
                                    # byte-identical Riolu. Evidence gate = both ADR-0072 instruments
                                    # plus the human flip review, not a win-rate run. Also narrows #178's
                                    # all-or-nothing defer to the sims the rung actually consults, so it
                                    # defers LESS often. Root cause (the order-dependent rollout) = #254.
    "evolve_value": True,           # the EVOLVE DECIDER, shipped ON 2026-07-25 (ADR-0070, #140): the body-substituted
                                    # deploy delta + the odds-priced income. The sweep's 10 flips were
                                    # user-ruled (6 FIX, 0 regression) and the rungs it replaced are
                                    # DELETED, so OFF is DEGRADED MODE, not a rollback: evolve
                                    # endorsements go silent and only the _PLAY-side Gate speaks.
    "deploy_value": True,           # the DEPLOY DECIDER, shipped ON 2026-07-30 (ADR-0086, #197): the Bench
                                    # marginal — netted Needs assignment + bench-drop Ability,
                                    # both dimensionless ratios through DEPLOY_BAND, plus the
                                    # damage-native accel unlock and Prize-Path exposure. The nine
                                    # rungs it replaces are DELETED (`keep-a-bench` excepted — decision 7
                                    # keeps it as a sound rung), so OFF is DEGRADED MODE, not a rollback:
                                    # bench endorsements go silent and only the empty-Bench guard speaks.
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
    "promote_retreat_value": True,  # the PROMOTE/RETREAT DECIDER, shipped ON 2026-07-27 (ADR-0073, #141):
                                    # the Sub-lethal Residual — `my_yield + closure − exposure +
                                    # tempo_denied − fatal`, plus `preservation − retreat_cost` at the
                                    # whether-site — in the same damage currency as the attach and evolve
                                    # marginals, at a DERIVED 100 damage/prize. ONE evaluator serves the
                                    # body pick, the whether-to-retreat question and the forced promote,
                                    # which is what makes the two-site divergence structurally impossible.
                                    # Eleven of the twelve promote/retreat rungs are DELETED (only
                                    # `retreat-to-wall-the-line` survives, as #165's Maneuver), so OFF is
                                    # documented DEGRADED MODE, not a rollback: promote/retreat goes quiet
                                    # and only the surviving Maneuver rung speaks. An incident lever,
                                    # never a comparison baseline.
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
    "recur_fuel_relax": True,       # ADR-0076 (#186), armed-ON 2026-07-27: quantifies
                                    # `_doom_recur_fueled`'s all-or-nothing relax-block — augments a
                                    # possible refueler's Energy with its real discard-recur reload
                                    # before the CHARGED relax check runs, instead of always standing
                                    # down. Corpus-swept clean (0/331 decision flips, by
                                    # `threat_sweep.py --slots` — a mode DELETED by Issue
                                    # #243: once this flag shipped ON here, the sweep
                                    # compared the PROFILE against a forced-ON copy of
                                    # itself, so its 0 flips became true by construction
                                    # rather than by measurement; the reading above stands,
                                    # it was taken while this shipped OFF) AND cleared the
                                    # ADR-0072 mid-build
                                    # paired-A/B gauntlet tripwire (`gauntlet_ab.py`, flag-overlay
                                    # variant — this swap deletes nothing, so the flag-overlay
                                    # instrument is the correct fit, not the build-vs-build
                                    # `gauntlet_swap_ab.py`): aggregate delta +2.4%, 95% CI
                                    # [-1.1%, +5.9%], 0 crashes/2400 games — comfortably clears the
                                    # crashes==0 AND CI-lo>=-5% Tripwire (no delta clause mid-build).
    "scaled_threat_rank": True,     # Issue #213, armed-ON 2026-07-30: the threat rank and the
                                    # forced-promotion read price a body through the Damage Formula
                                    # against the live board (`CombatMath.threat_ceiling` /
                                    # `forward_threat_ceiling`) instead of printed `maxDamage` + the
                                    # provider's printed forward index. Retires the flat
                                    # `_HAND_SIZE_ATTACKER_BOOST` (+500), a proxy for exactly the
                                    # fact the scaled read now computes — keeping both would
                                    # double-count one card fact, and the proxy could never
                                    # generalise past the single card its Function Tag covered.
                                    # Ships ON because OFF makes the change a no-op on the board and
                                    # both merit gates measure the ON behaviour; the switch survives
                                    # as an incident lever, restoring the printed-only read exactly.
    "gust_target_slots": True,      # ADR-0076 (#186), armed-ON 2026-07-27: generalizes `deny_slot`
                                    # to a `gust_target` kind — held gust-effect Trainer cards
                                    # keep-price against the real per-body `opponent_target_value`
                                    # instead of the flat `deny` disruption tier. Corpus-swept clean
                                    # (0/331 decision flips) AND cleared the ADR-0072 mid-build
                                    # tripwire: aggregate delta -0.75%, 95% CI [-4.3%, +2.8%],
                                    # 0 crashes/2400 games — CI-lo -4.3% clears the -5% floor.
                                    # NOTE: one single matchup (mega_lucario vs mega_starmie) swung
                                    # -11.5pp — the Tripwire screens catastrophes, not regressions,
                                    # so this is flagged for the ladder-corrections loop to watch,
                                    # not a reason to hold the flag back given the aggregate clears.
    "deny_strip_delta": True,       # ADR-0078 / Issue #199 (S3c). ADR-0084 (Issue #217) gave it its first
                                    # and only consumer — the target pick's lexicographic tiebreak,
                                    # which orders a tie on the clock and never GATES one (a
                                    # `strip_shift > 0` keep-price gate would suppress 128 of 218
                                    # relevance-positive corpus rows: the clock is blind to Ability
                                    # mutes, sub-turn setbacks, and plan damage that does not delay MY
                                    # defeat — decision 7, recommended, ACCEPTED, then REVERSED on
                                    # measurement). **ARMED-ON 2026-07-31 (Issue #228), so that
                                    # consumer is LIVE.** Arming was chartered by ADR-0084 decision 6
                                    # and blocked by the Discrimination Gate; the pre-registered
                                    # ship-dark fallback was taken and Issue #228 discharged it.
                                    # Armed TOGETHER with `deny_relevance` and never alone: this
                                    # flag's only consumer lives inside `if self.deny_relevance:`, so
                                    # alone it is inert — and `deny_relevance` alone would leave the
                                    # target pick's tie resolved by engine option order, the exact
                                    # ADR-0062 defect ("the argmax fell through to index 0 and we
                                    # stripped whatever Energy happened to land first") the tiebreak
                                    # was built to close. Evidence is on `deny_relevance` below.
                                    # Originally: adds the deny
                                    # instrument's STRIP delta to `_opponent_target_rows` beside the
                                    # removal delta #186 built (a Hammer strips one Energy off a body
                                    # that STAYS, so the removal delta is not its slice). Nothing
                                    # reads the new fields — Issue #187 is the consumer and is itself
                                    # blocked on Issue #199 — so ON changes no decision; it only costs one
                                    # extra `turns_to_ko_me` per ENERGIZED opponent body per
                                    # decision. OFF until Issue #199's gate 1 rules the read
                                    # admissible. That measurement was RUN and the answer
                                    # recorded in ADR-0080 ("deny is a categorical relevance
                                    # instrument, not a magnitude one" — the rate ruled
                                    # MOOT); its probe `deny_gate1.py` was deleted by
                                    # Issue #243, the ADR being the artifact.
    "snipe_relevance": True,        # ADR-0085 / Issue #188 (S4-snipe), armed-ON 2026-07-30: the **Snipe
                                    # Relevance** scalar DECIDES the DAMAGE bench-target select in
                                    # place of `baseline_snipe.py`'s six additive target rungs + the
                                    # ADR-0051 MatchupPlan steer, which all stand down together.
                                    # Snipe is the SECOND instrument to hit ADR-0062's "no monotone
                                    # pricing of magnitude alone can separate them" wall, so it takes
                                    # Deny Relevance's categorical shape rather than the shared prize
                                    # marginal (which measured 7/19 against the rungs' 17/19 and
                                    # restored a fixed ADR-0044 blunder on 83667237-107).
                                    # All three ADR-0072 bars cleared before arming (Amendment C).
                                    # The six rungs, the MatchupPlan steer, `_SNIPE_THREAT_PRIZE_FLOOR`
                                    # and `_MATCHUP_PRIORITY_SCALE` are now DELETED (#136 directive 1,
                                    # Amendment E), so **OFF is documented DEGRADED MODE, never a
                                    # rollback** — the `attach_value` / `evolve_value` /
                                    # `promote_retreat_value` precedent. See Amendment E3 for the one
                                    # OPEN consequence: the Brief steer is a MULTIPLIER, so it goes
                                    # inert when `their_plan` is 0 for every offered target.
    "deny_relevance": True,         # ADR-0080 / Issue #199 (S3c) + Issue #187.
                                    # **ARMED-ON 2026-07-31 (Issue #228, ADR-TEMP-228), closing
                                    # Phase 1e.** ADR-0084 (Issue #217) chartered the arming, the
                                    # Discrimination Gate blocked it, and the ADR's pre-registered
                                    # ship-dark fallback was taken. Issue #228 re-measured against
                                    # the `a8da62d` baseline and found the blocker was a DEFECT, not
                                    # the leaf card-worth interaction ADR-0084 Amendment B point 3
                                    # diagnosed (that reading — "every deny component is individually
                                    # correct, the keep price legitimately falls 5.0 -> 1.929" — is
                                    # WRONG; the keep price is a different surface and is not what
                                    # moved the leaf). THREE frames moved, not one, every one by
                                    # exactly `_PLANNER_SURVIVAL_W` 50.0: `_opponent_target_rows`
                                    # returned None mid-sim, `deny_relevance_best` could not express
                                    # absence, and the fire rung read the dataclass default as a
                                    # measured whiff — declining strips worth +22.50 and +74.50, one
                                    # of which the human ruled a correct Hammer play. Fixed, then
                                    # armed. Evidence, all at `baed389` vs baseline `a8da62d`:
                                    #   fix in / flags OFF   Discrimination PASS, 0 picks moved
                                    #   fix in / flags ARMED Discrimination PASS, 0 unruled, 0 ruled
                                    #   armed                Decision Gate  PASS, 372 frames,
                                    #                        agree 250/346 -> 250/346, 0 picks moved
                                    # Both gates were RE-RUN on the final post-deletion tree (the
                                    # runs above predate it) and PASS unchanged. Mid-build Tripwire
                                    # (ADR-0072 decision 1), 2400 games from a worktree pinned at the
                                    # final commit: delta +1.17 pp, 95% CI [-2.36, +4.70],
                                    # crashes 0 -> TRIPWIRE True. Excludes catastrophes only; merit
                                    # is the two per-frame gates, not this number.
                                    # The staged OFF run is what makes the armed run attributable
                                    # (ADR-TEMP-228 decision 5) — the fix and the arming share one
                                    # branch, so the OFF arm accounts for everything the repair moved
                                    # before the arming is measured at all. Mid-sim read cost 101s ->
                                    # 118s (~1.17x), well under decision 3's pre-registered 2x
                                    # fallback trigger, so the read stays LIVE mid-sim.
                                    # Rule 11's warning is now 5-for-5: Issue #187's arming exposed
                                    # three defects its pure tests could not reach, Issue #217's
                                    # exposed a fourth (ADR-0080's mandated `_DENIAL_FORWARD` discount
                                    # was never applied to the armed read at all), and Issue #228's
                                    # exposed a fifth — plus a sixth SURFACE, since `gust_target`
                                    # went silent mid-sim the same way with its flag shipped ON.
                                    # Emits the
                                    # **Deny Relevance** read — *is this Energy doing important work
                                    # for the opponent's plan?* — on `_opponent_target_rows`. The
                                    # read that REPLACED deny's magnitude: Issue #199's grill measured the
                                    # Worth Damage Rate underivable (the sole DISCARD-context Hammer
                                    # frame prices 0.000 under BOTH instruments, so the rate divides
                                    # out) and the user's doctrine reframed deny as a liveness gate,
                                    # a redundancy gate and a relevance read — none of which crosses
                                    # a scale boundary, so no bridge is needed.
                                    # SINCE Issue #187 this is no longer compute-only: ON, all three
                                    # deny surfaces score off the read instead of the ADR-0062
                                    # magnitude oracle — the keep Slot (`tier x relevance`, still
                                    # graded `/2^t`), the fire rung (`K x affordable relevance`, and
                                    # only the AFFORDABLE reading — see ADR-0080 Amendment B) and the
                                    # target pick (pure `argmax relevance`, no area weight). Armed,
                                    # every Hammer-bearing corrections frame reproduces the OFF
                                    # decision (12 frames, 0 changed), so the ADR-0062 deny 5/5
                                    # holds; it costs one line-attack scan per ENERGIZED opponent
                                    # body per decision, resolved once behind
                                    # `_opponent_target_cache`. OFF is byte-identical: no fields
                                    # emitted, no gate computed, magnitude oracle still live.
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
