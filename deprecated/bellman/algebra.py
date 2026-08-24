"""Bellman-only value and diagnostic algebra."""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping

from common.algebra import Terminal as NeutralTerminal


@dataclass(frozen=True)
class BellmanLedger:
    benefits: tuple[tuple[str, float], ...] = ()
    costs: tuple[tuple[str, float], ...] = ()
    continuation: float = 0.0

    def __post_init__(self) -> None:
        values = [value for _key, value in self.benefits + self.costs]
        values.append(self.continuation)
        if any(not math.isfinite(float(value)) for value in values):
            raise ValueError("ledger values must be finite")

    @property
    def immediate(self) -> float:
        return sum(value for _key, value in self.benefits) - sum(
            value for _key, value in self.costs)

    @property
    def total(self) -> float:
        return self.immediate + self.continuation

    def as_dict(self) -> dict:
        return {"benefits": dict(self.benefits), "costs": dict(self.costs),
                "immediate": self.immediate, "continuation": self.continuation,
                "total": self.total}


@dataclass(frozen=True)
class Terminal(NeutralTerminal):
    ledger: BellmanLedger = BellmanLedger()


@dataclass(frozen=True)
class ActionDiagnostic:
    action_key: str
    ledger: BellmanLedger
    complete: bool
    reason: str = ""
    branches: tuple[Mapping, ...] = ()
    decisions: float = 0.0


@dataclass(frozen=True)
class RootDiagnostics:
    chosen_key: str
    end: ActionDiagnostic
    alternatives: tuple[ActionDiagnostic, ...]
    nodes: int
    cache_hits: int
    stopped_reason: str


__all__ = ("ActionDiagnostic", "BellmanLedger", "RootDiagnostics", "Terminal")
