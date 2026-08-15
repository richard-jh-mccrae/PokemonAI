"""Declarative deck inputs for the shared Bellman runtime."""

from .strategy import Line, PrizePlan, Ready, Roles, Strategy
from .strategies import (
    ActivationCondition, DesiredFact, StrategyHint, StrategyOverride,
    strategy_hint_from_dict,
)

__all__ = [
    "ActivationCondition", "DesiredFact", "Line", "StrategyHint", "PrizePlan", "Ready",
    "Roles", "Strategy", "StrategyOverride", "strategy_hint_from_dict",
]
