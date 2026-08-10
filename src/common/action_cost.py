"""Strict residual cost for actions whose consumed resource has no priced magnitude.

Card actions are excluded: their held-card Worth belongs to the hand/leaf evaluators.  Manual
Retreat is excluded too: the promote/retreat equation already charges its allowance.  This module
only closes the remaining ordinal gap for a turn-ending attack and an activated Ability allowance.
"""
from __future__ import annotations

from common.apply_option import SCORE_PLACES
from common.currency import PRIZE_DAMAGE_RATE
from common.strategy.context import _ABILITY, _ATTACK


# One decimal order above the shared float-noise floor: enough to make a consumed resource strictly
# worse than End without asserting a tuned gameplay magnitude or overturning any measured delta.
ACTION_OPPORTUNITY_COST_PRIZES = 10.0 ** (1 - SCORE_PLACES)
ACTION_OPPORTUNITY_COST_DAMAGE = ACTION_OPPORTUNITY_COST_PRIZES * PRIZE_DAMAGE_RATE

_RESIDUAL_COST_KINDS = frozenset({_ABILITY, _ATTACK})


def residual_cost_prizes(option_type: int | None) -> float:
    """Ordinal prize cost where no specialised/card evaluator already owns the resource."""
    return ACTION_OPPORTUNITY_COST_PRIZES if option_type in _RESIDUAL_COST_KINDS else 0.0


def residual_cost_damage(option_type: int | None) -> float:
    """The same residual in Pilot's damage/tactical currency."""
    return ACTION_OPPORTUNITY_COST_DAMAGE if option_type in _RESIDUAL_COST_KINDS else 0.0


__all__ = (
    "ACTION_OPPORTUNITY_COST_PRIZES", "ACTION_OPPORTUNITY_COST_DAMAGE",
    "residual_cost_prizes", "residual_cost_damage",
)
