"""Bellman-only hidden-draw count classes."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from itertools import product
from math import comb


PROBABILITY_MAX = 1.0
HYPERGEOMETRIC_MASS_TOLERANCE = 1e-12


@dataclass(frozen=True)
class OutcomeGroup:
    key: str
    card_ids: tuple[int, ...]


@dataclass(frozen=True)
class DrawClass:
    probability: float
    counts: tuple[int, ...]
    remainder: int
    label: str


def hypergeometric_classes(pool_ids, draws: int,
                           groups: tuple[OutcomeGroup, ...]) -> tuple[DrawClass, ...]:
    pool = Counter(int(card_id) for card_id in pool_ids)
    sizes, claimed = [], set()
    for group in groups:
        ids = tuple(card_id for card_id in group.card_ids if card_id not in claimed)
        claimed.update(ids)
        sizes.append(sum(pool[card_id] for card_id in ids))
    total = sum(pool.values())
    draws = min(max(0, int(draws)), total)
    remainder_n = total - sum(sizes)
    denominator = comb(total, draws) if total >= draws else 0
    if denominator == 0:
        return (DrawClass(1.0, tuple(0 for _ in sizes), 0, "empty"),)
    outcomes = []
    ranges = [range(min(size, draws) + 1) for size in sizes]
    for counts in product(*ranges):
        remainder = draws - sum(counts)
        if not 0 <= remainder <= remainder_n:
            continue
        numerator = comb(remainder_n, remainder)
        for size, count in zip(sizes, counts):
            numerator *= comb(size, count)
        if not numerator:
            continue
        labels = [f"{group.key}={count}" for group, count in zip(groups, counts)]
        labels.append(f"other={remainder}")
        outcomes.append(DrawClass(numerator / denominator, tuple(counts), remainder,
                                  ",".join(labels)))
    mass = sum(outcome.probability for outcome in outcomes)
    if abs(mass - PROBABILITY_MAX) > HYPERGEOMETRIC_MASS_TOLERANCE:
        raise ValueError(f"hypergeometric outcome mass {mass} != 1")
    return tuple(outcomes)


__all__ = ("DrawClass", "OutcomeGroup", "hypergeometric_classes")
