"""Deploy DECIDER — ADR-0086 (grill: Issue #197). What is putting ONE body into ONE Bench slot worth?

    deploy(X) = BAND x ( assignment_relevance(X) + ability_relevance(X) )
                + accel_unlock(X)          # already damage
                - exposure(X)              # already damage

FOUR legs, not five (amendment B): `needs.deploy_marginal` is already netted, so a body's contribution
and what it DISPLACES are two readings of one quantity — subtracting them again double-counts.

The Worth legs are dimensionless RATIOS (`marginal / currency.DEPLOY_WORTH_SCALE`): the Worth points
cancel, so no `WORTH_DAMAGE_RATE` is needed and none exists. Relevance is SIGNED, unlike deny's [0,1]
— a deploy can be actively bad, and the equation must be able to say so.

NOT here: the empty-Bench guard. That is a loss, so it is a SOUND RUNG above this equation, never a
bounded leg inside it (decision 7). Pure over `DeployInputs`; the Pilot resolves the board.
"""
from __future__ import annotations

from dataclasses import dataclass

# Read through the MODULE, not `from currency import ...`: the scale-invariance test RE-POINTS the
# yardstick, and a bound name would silently defeat it.
from common import currency
from common.grading import halve as _halve


@dataclass
class DeployInputs:
    """Board facts the Pilot resolves. The two `*_marginal` fields are the only WORTH-denominated
    inputs — they cross the scale boundary as ratios, here, once."""

    #: `needs.deploy_marginal`: netted, capacity-bounded, SIGNED (negative = worth less than it displaces).
    assignment_marginal: float = 0.0

    #: Worth points of the best need a bench-drop Ability's fetch could fill; 0 when it supplies nothing.
    ability_marginal: float = 0.0

    #: P(the fetchable class is still in deck). A ranked consumer WEIGHTS, never gates (ADR-0074).
    ability_odds: float = 0.0

    #: Whether the bench-drop trigger can fire at all — the Pilot owns WHICH of the three reasons.
    ability_can_fire: bool = False

    #: This turn's one Supporter is spent, so a fetch banks for NEXT turn at the one-turn discount.
    supporter_quota_spent: bool = False

    #: DAMAGE the Attach Budget realises because a legal landing spot now exists (decision 8).
    accel_unlock: float = 0.0

    #: PRIZE-equivalents by which this deploy shortens the OPPONENT's cheapest Prize Path. Positive =
    #: a gift. Converted through `PRIZE_DAMAGE_RATE`, never the deploy band.
    exposure_prizes: float = 0.0

    #: `needs.phase_scale`; 1.0 is neutral.
    phase: float = 1.0


@dataclass
class DeployValue:
    """The per-leg breakdown plus the total. The breakdown is not decoration — a human rules the
    Decision Gate by reading it, so a bare total would make the gate unrulable."""

    assignment_relevance: float = 0.0
    ability_relevance: float = 0.0
    accel_unlock: float = 0.0
    exposure: float = 0.0
    total: float = 0.0

    def working(self) -> dict:
        """The legible working, for telemetry and the sweep's flip table."""
        return {"assignment_relevance": self.assignment_relevance,
                "ability_relevance": self.ability_relevance,
                "accel_unlock": self.accel_unlock,
                "exposure": self.exposure,
                "total": self.total}


def _relevance(worth_marginal: float) -> float:
    """A Worth-denominated marginal as a dimensionless, signed, saturating ratio. The yardstick is FIXED
    and board-independent (amendment C): a per-decision one reads 1.0 for the merely least-bad deploy."""
    scale = float(currency.DEPLOY_WORTH_SCALE)
    if scale <= 0:                                   # defensive: never divide by a re-banded zero
        return 0.0
    return max(-1.0, min(1.0, float(worth_marginal) / scale))


def deploy_value(inp: DeployInputs) -> DeployValue:
    """Price one candidate deploy, in the damage currency the tactical rungs already share."""
    assignment = _relevance(inp.assignment_marginal)

    ability = 0.0
    if inp.ability_can_fire:
        odds = max(0.0, min(1.0, float(inp.ability_odds)))
        ability = _relevance(inp.ability_marginal) * odds
        if inp.supporter_quota_spent:
            ability *= _halve(1)                     # next turn: the shared convention (ADR-0070 §6)

    accel = float(inp.accel_unlock)
    exposure = float(inp.exposure_prizes) * float(inp.phase) * currency.PRIZE_DAMAGE_RATE
    total = currency.deploy_relevance_to_damage(assignment + ability) + accel - exposure
    return DeployValue(assignment_relevance=assignment, ability_relevance=ability,
                       accel_unlock=accel, exposure=exposure, total=total)
