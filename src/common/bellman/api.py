"""Stable public types for the isolated planner boundary (ADR-TEMP-507, M0).

M0 deliberately exposes no strategic implementation.  Later milestones fill this boundary without
changing callers or permitting a temporary legacy fallback.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol, Sequence


END_VALUE = 0.0


@dataclass(frozen=True, order=True)
class ActionIdentity:
    """Canonical public action label; engine-menu index is routing, never identity."""

    kind: str
    parts: tuple = ()


@dataclass(frozen=True)
class PlanRequest:
    """One live decision point plus deck-neutral knowledge providers."""

    observation: Mapping
    deck: tuple[int, ...]
    deck_name: str


@dataclass(frozen=True)
class RootDecision:
    """The next committed choice.  The planner always replans after the real transition."""

    chosen: tuple[int, ...]
    action: ActionIdentity
    value: float
    complete: bool
    diagnostics: Mapping


class BellmanUnavailable(RuntimeError):
    """Raised while the isolated prototype lacks an ordinary reachable mechanic."""


class BellmanPlanner(Protocol):
    """The only strategic interface Mega Starmie's eventual live route may call."""

    def decide(self, request: PlanRequest) -> RootDecision:
        ...


def require_consumed_cost(action: ActionIdentity, consumed: Sequence[str]) -> tuple[str, ...]:
    """M0 invariant: End alone may consume nothing; every other action names its resource."""

    costs = tuple(str(item) for item in consumed if str(item))
    if action.kind == "end":
        if costs:
            raise ValueError("End cannot consume a resource")
        return ()
    if not costs:
        raise ValueError(f"non-End action {action.kind!r} must name a consumed resource")
    return costs


__all__ = (
    "END_VALUE",
    "ActionIdentity",
    "BellmanPlanner",
    "BellmanUnavailable",
    "PlanRequest",
    "RootDecision",
    "require_consumed_cost",
)
