"""PROTOTYPE: one hard decision clock with fair root-action slices.

Question: can a never-reset wall clock preserve correction quality at 5/7/10/15 seconds while
preventing wide root menus from consuming the full match bank?
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FairBudgetPrototype:
    seconds: float

    def hard_deadline(self, started: float) -> float:
        return started + max(0.0, float(self.seconds))

    @staticmethod
    def root_deadline(now: float, hard_deadline: float, roots_remaining: int) -> float:
        share = max(0.0, hard_deadline - now) / max(1, int(roots_remaining))
        return min(hard_deadline, now + share)


__all__ = ("FairBudgetPrototype",)
