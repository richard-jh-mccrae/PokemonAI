"""Deny Relevance — *is this Energy doing work for the opponent's plan?* (ADR-0080, Issue #199).

A scalar in ``[0, 1]`` per ``(body, Energy)`` pair that SCALES the incumbent constants — deliberately
NOT a magnitude on the damage scale, so no Worth-Damage-Rate bridge is needed and none ships. This
module owns the scoring; the Pilot owns the board plumbing.

ATTACK LEG: relevant when removing the Energy puts an attack of the body's LINE further out of reach
— it pays a specific-type slot the body is not surplus in, or every typed slot is already covered and
the COUNT binds. Deliberately NOT a plain affordability diff: a bare total-count rule flags a lone
Energy on a pure-colourless cost and a stray off-type one on a half-paid cost, both against the
doctrine. The whole-LINE scan ranks a banked ``{F}`` on a pre-evo above a current-form attacker's.

ABILITY LEG: stripping the LAST Energy of a type an Ability is gated on MUTES it — the mirror of the
attach marginal's dormant-Ability predicate, off the same `CardStat.abilityEnergyTypes` field. Known
gaps: a STATIC buff Ability is under-rated, and rainbow Special Energy scores 0 (no ONE colour)."""
from __future__ import annotations

import math

#: The relevance NORMALIZER — the largest attack damage printed in the card set, DERIVED not tuned
#: (`test_deny_relevance.py` recomputes it from the CSV). Never an exchange rate.
MAX_ATTACK_DAMAGE = 350.0


def normalize(setback_damage: float) -> float:
    """Map a damage setback into the ``[0, 1]`` relevance band. BOTH legs run through it."""
    return min(1.0, max(0.0, float(setback_damage) / MAX_ATTACK_DAMAGE))


def strip_relevance(*, energy_type, type_count: int, line_attacks, ability_types=(),
                    total_attached: int = 0, attached_counts=None, forward_discount: float) -> dict:
    """Relevance of removing ONE Energy of ``energy_type`` from a body, with its legs. ``energy_type``
    is an EnergyType code, NEVER a card id. ``forward_discount`` has no default, deliberately (#217)."""
    blank = {"relevance": 0.0, "attack_leg": 0.0, "ability_leg": 0.0,
             "setback_damage": 0, "forward_setback": 0, "affordable_setback": 0,
             "affordable_relevance": 0.0}
    if energy_type in (None, 0) or type_count <= 0:
        return blank
    counts = attached_counts or {}

    # Split by SOURCE so the forward contribution can be DISCOUNTED rather than credited in full
    # (ADR-0080 decision 2; crediting it in full doubles a forward threat — Issue #217).
    own_setback = forward_setback = 0
    own_affordable = forward_affordable = 0
    body_best = 0
    for damage, need, total_cost, is_forward in line_attacks:
        body_best = max(body_best, int(damage))
        breaks_it = False
        if not need:
            # Pure-colourless: no TYPE critical path, but the COUNT can bind — and only on EXACT
            # equality, which is what separates a 3-of-3 nuke from an unaffordable 1-of-3 (ADR-0080 B).
            if total_attached == total_cost:
                breaks_it = True
        else:
            typed_slot = type_count <= need.get(energy_type, 0)
            # Guarded on FULL type coverage, so a body still missing a colour is bound by the TYPE
            # rather than the count.
            type_ready = all(counts.get(t, 0) >= n for t, n in need.items())
            count_binds = type_ready and total_attached <= total_cost
            breaks_it = typed_slot or count_binds
        if breaks_it:
            if is_forward:
                forward_setback = max(forward_setback, int(damage))
            else:
                own_setback = max(own_setback, int(damage))
            # AFFORDABLE-only mirror, for consumers deciding whether to SPEND the card NOW; full
            # relevance credits BANKED potential, which is the right read for KEEPING it (ADR-0080 B).
            if total_attached >= total_cost:
                if is_forward:
                    forward_affordable = max(forward_affordable, int(damage))
                else:
                    own_affordable = max(own_affordable, int(damage))
    # A DISCOUNT, never a deletion: the lower bound ADR-0063 derived must still PLAY the Hammer off a
    # pre-evo's banked Energy.
    setback = max(own_setback, forward_discount * forward_setback)
    affordable_setback = max(own_affordable, forward_discount * forward_affordable)
    attack = normalize(setback)

    # The mute. Only the LAST Energy of the gated type switches an Ability off: "any {D} attached"
    # survives while a second {D} remains, so a strip off a doubled-up body mutes nothing.
    ability = 0.0
    if energy_type in (ability_types or ()) and type_count == 1:
        # Strictly above its OWN body's best attack leg and nothing further: `nextafter` asserts an
        # ORDER without asserting a magnitude, so no tunable constant enters.
        ability = math.nextafter(normalize(body_best), 1.0)

    return {"relevance": max(attack, ability), "attack_leg": attack, "ability_leg": ability,
            "setback_damage": setback, "forward_setback": forward_setback,
            "affordable_setback": affordable_setback,
            # The mute rides along: switching off a live Ability takes effect immediately, so it is
            # never "potential" the way a banked attack is.
            "affordable_relevance": max(normalize(affordable_setback), ability)}
