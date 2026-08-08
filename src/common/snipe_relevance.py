"""Snipe Relevance — *does damaging this body matter to their plan and to my prize route?* (ADR-0085).
A ``[0, 1]`` scalar SCALING an incumbent constant, never a magnitude: two corpus frames offer
identical inputs and the human rules them opposite ways, so no monotone pricing separates them.

    relevance  = their_plan x my_route
    their_plan = max(imminence, forward, forced) x brief
    my_route   = max(ko_delta, reach, share, prevent_ex)

A PRODUCT where deny is a MAX, because the two sides are CONJUNCTIVE: a terrifying body I have no
route through and a harmless body sitting on my route are both bad snipes. That makes the additive
failure mode unrepresentable rather than capped; `max` still governs WITHIN each side.

This module owns the scoring, the `Pilot` owns the board plumbing. No constant is introduced, and
`_ENERGIZED_SNIPE_TIER` / `_PREVENT_EX_SNIPE_BOOST` deliberately STAY at `Pilot._body_threat_rank`:
snipe-NAMED but Planner-SHARED, so retiring them is a Planner change owing its own gate."""
from __future__ import annotations

import math
from dataclasses import dataclass

from common.currency import tiebreak_bonus
from common.deny_relevance import MAX_ATTACK_DAMAGE, normalize

#: IDENTICAL to the normalizer, so ``K x relevance`` recovers the setback in DAMAGE — no parameter.
K = MAX_ATTACK_DAMAGE


def ko_delta(turns_before: float | None, turns_after: float | None) -> float:
    """A chip is worth something only if it takes a TURN off the clock; None before = no route."""
    if not turns_before or turns_after is None:
        return 0.0
    return min(1.0, max(0.0, (float(turns_before) - float(turns_after)) / float(turns_before)))


def rider_reach(hp_remaining: int, rider_damage: int) -> float:
    """``1 / ceil(hp / rider)``; 0 when the rider deals nothing, so no provider invents a route."""
    if not hp_remaining or not rider_damage:
        return 0.0
    return 1.0 / math.ceil(hp_remaining / rider_damage)


def prize_share(prize_value: int, prizes_needed: int) -> float:
    """Capped at 1.0 — the `prize_advance` overshoot expressed as saturation, not as a gate."""
    if prizes_needed <= 0:
        return 0.0
    return min(1.0, max(0.0, float(prize_value) / float(prizes_needed)))


def brief_tiebreak(peers: list[tuple[float, float]], mine_relevance: float,
                   mine_priority: float) -> float:
    """Ordering BENEATH relevance, never a term in it: an EXACT tie plus a STRICT maximum, and
    deliberately no sign or ``> 0`` guard."""
    tied = [p for r, p in peers if r == mine_relevance]
    if len(tied) < 2:
        return 0.0                                  # nothing tied with me — relevance already decided
    best = max(tied)
    if mine_priority != best or sum(1 for p in tied if p == best) > 1:
        return 0.0                                  # not the winner, or tied on the Brief as well
    return tiebreak_bonus([r for r, _p in peers], K)


@dataclass(frozen=True)
class TheirPlanInputs:
    """Sourced from the Threat Clock, not `Pilot._body_threat_rank`; the Pilot fills them in."""
    #: A CEILING on how HARD they hit, a slow clock on how SOON. None = UNKNOWN, so NO discount.
    incoming_damage: int = 0
    turns_to_afford: int | None = None
    #: The developing-wincon leg's input, filled by `Pilot._snipe_relevance_terms`.
    forward_damage: int = 0
    #: Chip the pre-evo only while the evolved wincon is NOT already on board (ADR-0044).
    is_strongest_forward: bool = False
    forward_form_in_play: bool = False
    #: GRADED here, never a flat 1.0 (decision 10).
    is_forced_promotion: bool = False
    #: **Leg-scoped**: these zero the imminence leg only; a whole-target gate is refuted.
    prize_redundant: bool = False
    promotion_mirage: bool = False
    #: Used ONLY to stand a positive Brief boost down. The Tera veto itself is an ORDERING, never a
    #: zero here — a benched Tera that is the only offered target must remain selectable.
    is_tera: bool = False
    #: The matched Brief priority, signed and already scaled. A POSITIVE one stands down on a
    #: redundant / mirage / Tera body; a NEGATIVE (``avoid``) one always applies. Only the SIGN is read.
    brief_priority: float = 0.0

    def brief_boost_gated(self) -> bool:
        """A NEGATIVE (``avoid``) priority is unaffected: a booster scales, never overrides."""
        return self.prize_redundant or self.promotion_mirage or self.is_tera


@dataclass(frozen=True)
class MyRouteInputs:
    """The board facts the **my_route** side reads — *does hurting it advance MY prize route?*"""
    #: Before and after the TWO-chip window: a ONE-chip read scores a corpus answer at zero.
    turns_to_ko_before: float | None = None
    turns_to_ko_after: float | None = None
    #: The `reach` leg — the body's HP against my REPEATABLE bench rider.
    hp_remaining: int = 0
    rider_damage: int = 0
    #: The `share` leg — this body's prizes against what I still NEED.
    prize_value: int = 1
    prizes_needed: int = 6
    #: My route through it closes PERMANENTLY once it evolves, so this turn is the last it exists.
    prevents_my_ex: bool = False


def target_relevance(*, plan: TheirPlanInputs, route: MyRouteInputs,
                     brief_boost: float = 1.0) -> dict:
    """Both sides are REQUIRED: a defaulted one lets a call site drop half a conjunctive product."""
    # ── their_plan. The ADR-0044 reads suppress the IMMINENCE claim only, not a developing wincon.
    if plan.prize_redundant or plan.promotion_mirage:
        imminence = 0.0
    else:
        # `None` is UNKNOWN, not "it can never attack": discounting it would be fail-OPEN.
        t = 0 if plan.turns_to_afford is None else max(0, int(plan.turns_to_afford))
        imminence = normalize(plan.incoming_damage) / (2 ** t)

    forward = (normalize(plan.forward_damage)
               if (plan.is_strongest_forward and not plan.forward_form_in_play) else 0.0)

    # GRADED, and with no imminence discount: a forced promotion IS the timing claim (decision 10).
    forced = normalize(plan.incoming_damage) if plan.is_forced_promotion else 0.0

    their_plan = max(imminence, forward, forced)

    # Only the SIGN is read: scaling the raw priority would need a rate nothing derives.
    multiplier = 1.0
    if plan.brief_priority > 0 and not plan.brief_boost_gated():
        multiplier = max(0.0, float(brief_boost))
    elif plan.brief_priority < 0 and brief_boost:
        multiplier = 1.0 / float(brief_boost)      # the mirror, so one constant governs both directions
    their_plan = min(1.0, their_plan * multiplier)

    # ── my_route ──────────────────────────────────────────────────────────────────────────────
    delta = ko_delta(route.turns_to_ko_before, route.turns_to_ko_after)
    reach = rider_reach(route.hp_remaining, route.rider_damage)
    share = prize_share(route.prize_value, route.prizes_needed)
    # Maximal: once the line reaches its `prevent_ex_damage` form my ex attacker can never damage it.
    prevent_ex = 1.0 if route.prevents_my_ex else 0.0
    my_route = max(delta, reach, share, prevent_ex)

    return {"relevance": their_plan * my_route,
            "their_plan": their_plan, "my_route": my_route,
            "imminence": imminence, "forward": forward, "forced": forced,
            "ko_delta": delta, "reach": reach, "share": share, "prevent_ex": prevent_ex,
            "brief_multiplier": multiplier}
