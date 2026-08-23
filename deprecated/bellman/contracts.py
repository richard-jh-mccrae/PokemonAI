from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol

from common.api import ActionIdentity


END_VALUE = 0.0


@dataclass(frozen=True)
class PlanRequest:
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
    chosen: tuple[int, ...]
    action: ActionIdentity
    value: float
    complete: bool
    diagnostics: Mapping
    plan_suffix: tuple[PlanStep, ...] = ()


class BellmanUnavailable(RuntimeError):
    pass


class BellmanPlanner(Protocol):
    def decide(self, request: PlanRequest) -> RootDecision: ...


__all__ = ("END_VALUE", "BellmanPlanner", "BellmanUnavailable", "PlanRequest", "PlanStep",
           "RootDecision")
