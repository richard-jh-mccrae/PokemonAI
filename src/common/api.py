"""Stable public types for the isolated planner boundary (ADR-0139, M0).

M0 deliberately exposes no strategic implementation.  Later milestones fill this boundary without
changing callers or permitting a temporary legacy fallback.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol


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
class PlanStep:
    expected_state_key: str
    legal_menu_digest: str
    chosen: tuple[int, ...]
    action: ActionIdentity
    profile_hash: str
    turn: int
    seat: int
    value: float = 0.0


@dataclass(frozen=True)
class RootDecision:
    """The next committed choice plus its guarded deterministic continuation."""

    chosen: tuple[int, ...]
    action: ActionIdentity
    value: float
    complete: bool
    diagnostics: Mapping
    plan_suffix: tuple[PlanStep, ...] = ()


class BellmanUnavailable(RuntimeError):
    """Raised while the isolated prototype lacks an ordinary reachable mechanic."""


class BellmanPlanner(Protocol):
    """Deck-neutral strategic boundary."""

    def decide(self, request: PlanRequest) -> RootDecision:
        ...


__all__ = (
    "END_VALUE",
    "ActionIdentity",
    "BellmanPlanner",
    "BellmanUnavailable",
    "PlanRequest",
    "PlanStep",
    "RootDecision",
)
