"""Promote/retreat value oracle — docs/plans/promote-retreat-grill-spec.md §Settled design.

The retreat/promote decision as ONE equation in the Needs currency, shadowing the
`baseline_promote.py` / `baseline_retreat.py` rung ladder. It is a **two-sided window-rollout diff**
(grill ruling 2): the value of bringing body B to the Active Spot is what B's tenure earns me MINUS
what promoting it hands the opponent, netted against the current Active's forgone attack.

    retreat_value(B) =  my_yield(B)        readiness band — what B can DO this turn (attack / stall /
                                           charge-dividend), EV over closure (ruling 3). Sub-lethal ONLY:
                                           the WIN branch is the lethal solver's (ruling 4) and a provable
                                           KO is the turn planner's (ruling 5), so neither is priced here.
                      − their_yield(B)     prize B exposes × can-they-punish × prize-map asymmetry, PLUS
                                           the tempo an item-lock DENIES them (ruling 6 fold).
                      − retreat_cost       Energy paid to retreat (voluntary SWITCH only).
                      − stay_forgone       the current Active's forgone attack — ruling 1: an opportunity
                                           SUBTRACTION, not a veto (voluntary SWITCH only).

Emitted REPORTING-ONLY on `OptionTrace.promote_retreat_shadow` until the swap gate is green. Two curve
terms — the N-turn preservation dividend (my curve up) and the N-turn tempo slip (their curve down) —
are priced only as an IMMEDIATE 1-exchange slice here; their full form blocks on the unified Threat
Clock (`threat-clock-unification-handoff.md`). Calibrated at the old rung currency (the +50/+45/+40/
+20/−20 partial order of `baseline_promote.py`).
"""
from __future__ import annotations

from dataclasses import dataclass

# Calibration constants — the baseline_promote.py rung currency.
_READY = 40.0          # a ready wincon that can attack now (was `promote-the-ready-wincon` +40)
_BEST_BONUS = 5.0      # which-body tie-break among ready wincons (`is_best_promote_target`, the f104 fix)
_ACT = 15.0            # a non-wincon body that can act this turn (the interpose soaker's own body worth)
_STALL = 20.0          # a disposable staller / wall promoted (was `promote-the-staller` +20)
_DIVIDEND = 5.0        # IMMEDIATE preservation-dividend slice (accel charging the bench); N-turn deferred
_PRIZE_UNIT = 12.0     # their_yield per-prize exposure unit
_FATAL_STEP = 20.0     # the fatal-prize step edge (was `dont-promote-into-their-prize-reach` −20)
_PATH_TAX = 8.0        # onto-their-path positional brake (was `dont-promote-onto-their-path` −8)
_ITEM_LOCK_TEMPO = 12.0  # immediate item-lock denial slice (a turn of their development lost)
_NEAR_GOAL = 0.5       # prize-map super-linear weight, per prize inside the goal band
_GOAL_BAND = 2         # the opponent's last _GOAL_BAND prizes cost extra


@dataclass
class PromoteRetreatInputs:
    """The board facts a promote/retreat option's value reads — filled by the Pilot from the same
    Context flags the `baseline_promote` ladder consumes, so the equation stays a pure function."""
    is_switch: bool = False           # voluntary retreat (SWITCH) vs a forced promote (TO_ACTIVE)
    # --- my_yield: what body B earns as the new Active this turn (sub-lethal band) ---
    can_attack_now: bool = False      # `promote_target_can_attack` — B can pay a valued attack now
    is_wincon: bool = False           # `card_is_wincon`
    is_best_target: bool = False      # `is_best_promote_target` — the best benched wincon (per-option)
    is_staller: bool = False          # an opener/wall or item-lock disruptor (disposable)
    is_accelerator: bool = False      # `accel_source` in roles — charges the bench (dividend)
    bench_underpowered: bool = False  # `bench_wincon_underpowered` + `basic_energy_in_deck` — a target for it
    provable_ko: bool = False         # `promote_target_kos` — HANDED to the planner (ruling 5); suppresses
                                      # the fatal-prize step, never adds a lethal magnitude here
    fetch_enables_p: float = 0.0      # P(fetch the missing enabler THIS turn), from Odds + Closure (ruling 3)
    # --- their_yield: what promoting B hands the opponent ---
    prize_value: int = 1              # `card_prize_value` — prizes a KO of B yields
    opp_can_punish: bool = True       # NOT `opp_cannot_punish_wincon` — can they actually KO B next turn?
    opp_prizes_remaining: int = 6     # prize-map asymmetry input
    on_their_path: bool = False       # `promote_target_on_their_path`
    is_item_lock: bool = False        # `item_lock` tag — denies the opponent a development turn (ruling 6)
    # --- retreat cost + the forgone attack (voluntary SWITCH only) ---
    retreat_energy_worth: float = 0.0  # Energy paid to retreat, priced via card_worth
    stay_yield: float = 0.0           # my_yield(current Active, stay-and-attack) — sub-lethal band (ruling 1)


@dataclass
class PromoteRetreatValue:
    """The promote/retreat value with its inner terms (shadow-trace legibility, ADR-0019 full
    working). ``total`` is the transparent net."""
    my_yield: float = 0.0
    their_yield: float = 0.0
    tempo_denied: float = 0.0
    retreat_cost: float = 0.0
    stay_forgone: float = 0.0
    total: float = 0.0


def _prize_map_weight(opp_prizes_remaining: int) -> float:
    """Super-linear near the opponent's goal: 1.0 in the open game, escalating over their last
    `_GOAL_BAND` prizes (their last prizes are the ones that cost them the match to give up)."""
    return 1.0 + _NEAR_GOAL * max(0, _GOAL_BAND - max(0, int(opp_prizes_remaining)))


def promote_retreat_value(inp: PromoteRetreatInputs) -> PromoteRetreatValue:
    """The value of a promote/retreat option in the one currency (see module docstring)."""
    # --- my_yield: readiness band (sub-lethal; win/KO handed up, rulings 4/5) ---
    my = 0.0
    if inp.is_wincon and inp.can_attack_now:
        my += _READY + (_BEST_BONUS if inp.is_best_target else 0.0)
    elif inp.can_attack_now:
        my += _ACT
    if inp.is_staller:
        my += _STALL
    if inp.is_accelerator and inp.bench_underpowered:
        my += _DIVIDEND                              # IMMEDIATE dividend slice (N-turn -> Threat Clock)
    if inp.is_wincon and not inp.can_attack_now and inp.fetch_enables_p > 0.0:
        # EV over closure (ruling 3): the fetch that would ready B, weighted by its odds — NOT the
        # fail-closed floor. Capped at the ready credit: closure can never beat actually being ready.
        my += max(0.0, min(1.0, inp.fetch_enables_p)) * _READY

    # --- their_yield: prize exposure + prize-map asymmetry, plus the path brake ---
    their = 0.0
    if inp.opp_can_punish:
        their += inp.prize_value * _PRIZE_UNIT * _prize_map_weight(inp.opp_prizes_remaining)
        # the fatal-prize step (dont-promote-into-their-prize-reach): KOing B ends the game. Stands
        # down on a provable KO trade (ruling 5 — trading KOs while ahead is fine).
        if (not inp.provable_ko) and inp.prize_value >= inp.opp_prizes_remaining >= 2:
            their += _FATAL_STEP
    if inp.on_their_path:
        their += _PATH_TAX

    # --- tempo-denied (ruling 6 fold): an item-lock denies the opponent a development turn, in the
    # same currency, bounded by the prizes they have left (can't deny more than remains). ---
    tempo = 0.0
    if inp.is_item_lock:
        tempo = min(_ITEM_LOCK_TEMPO, max(0, int(inp.opp_prizes_remaining)) * _PRIZE_UNIT)

    # --- retreat cost + the forgone attack (voluntary SWITCH only; ruling 1) ---
    retreat_cost = inp.retreat_energy_worth if inp.is_switch else 0.0
    stay_forgone = max(0.0, inp.stay_yield) if inp.is_switch else 0.0

    total = my - their + tempo - retreat_cost - stay_forgone
    return PromoteRetreatValue(my_yield=my, their_yield=their, tempo_denied=tempo,
                               retreat_cost=retreat_cost, stay_forgone=stay_forgone, total=total)
