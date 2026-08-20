"""Exact finite probability classes for hidden-zone draws and reveals."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from itertools import product
from math import comb


PROBABILITY_MIN = 0.0
PROBABILITY_MAX = 1.0
HYPERGEOMETRIC_MASS_TOLERANCE = 1e-12
DEFAULT_INFORMATION_OUTCOME_LIMIT = 16
STRATIFIED_BIN_MIDPOINT = 0.5


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


@dataclass(frozen=True)
class RevealSet:
    probability: float
    card_ids: tuple[int, ...]


@dataclass(frozen=True)
class DrawOutcome:
    probability: float
    card_ids: tuple[int, ...]
    exact: bool


def _combination_at_rank(total: int, draws: int, rank: int) -> tuple[int, ...]:
    """Unrank one lexicographic physical-card subset among ``comb(total, draws)`` subsets."""
    indices = []
    start = 0
    for remaining in range(draws, 0, -1):
        for index in range(start, total):
            suffixes = comb(total - index - 1, remaining - 1)
            if rank < suffixes:
                indices.append(index)
                start = index + 1
                break
            rank -= suffixes
    return tuple(indices)


def draw_outcomes(pool_ids, draws: int, *,
                  max_outcomes: int = DEFAULT_INFORMATION_OUTCOME_LIMIT) -> tuple[DrawOutcome, ...]:
    """Multivariate-hypergeometric outcomes, stratified when support exceeds the width cap."""
    pool = Counter(int(card_id) for card_id in pool_ids)
    total = sum(pool.values())
    draws = min(max(0, int(draws)), total)
    if draws == 0:
        return (DrawOutcome(PROBABILITY_MAX, (), True),)
    identities = tuple(sorted(pool))
    signatures = []

    def enumerate_counts(index, remaining, chosen):
        if len(signatures) > max_outcomes:
            return
        if index == len(identities):
            if remaining == 0:
                signatures.append(tuple(chosen))
            return
        card_id = identities[index]
        for count in range(min(pool[card_id], remaining) + 1):
            enumerate_counts(index + 1, remaining - count,
                             (*chosen, *((card_id,) * count)))

    enumerate_counts(0, draws, ())
    denominator = comb(total, draws)
    if len(signatures) <= max_outcomes:
        exact = []
        for signature in signatures:
            selected = Counter(signature)
            ways = 1
            for card_id, count in selected.items():
                ways *= comb(pool[card_id], count)
            exact.append(DrawOutcome(ways / denominator, signature, True))
        return tuple(exact)

    # One midpoint from each equal-mass stratum of physical-card subsets. Unlike seeded Monte Carlo,
    # a rare hand cannot consume several branches because of seed luck; unlike signature ordering,
    # no card identity or value determines the strata. Duplicate signatures are merged.
    expanded = tuple(sorted(pool.elements()))
    quantiles = tuple((index + STRATIFIED_BIN_MIDPOINT) / max_outcomes
                      for index in range(max_outcomes))
    representatives: Counter[tuple[int, ...]] = Counter()
    for quantile in quantiles:
        rank = min(denominator - 1, int(quantile * denominator))
        signature = tuple(expanded[index]
                          for index in _combination_at_rank(total, draws, rank))
        representatives[signature] += 1
    return tuple(DrawOutcome(count / max_outcomes, signature, False)
                 for signature, count in sorted(representatives.items()))


def reveal_sets(pool_ids, draws: int, eligible_ids) -> tuple[RevealSet, ...]:
    """Exact distribution of distinct selectable identities in a without-replacement window."""
    pool = Counter(int(card_id) for card_id in pool_ids)
    eligible = tuple(sorted(set(int(card_id) for card_id in eligible_ids) & set(pool)))
    total = sum(pool.values())
    draws = min(max(0, int(draws)), total)
    denominator = comb(total, draws) if total >= draws else 0
    if denominator == 0:
        return (RevealSet(PROBABILITY_MAX, ()),)
    ineligible = total - sum(pool[card_id] for card_id in eligible)
    grouped: dict[tuple[int, ...], int] = {}
    ranges = [range(min(pool[card_id], draws) + 1) for card_id in eligible]
    for counts in product(*ranges):
        remainder = draws - sum(counts)
        if not 0 <= remainder <= ineligible:
            continue
        ways = comb(ineligible, remainder)
        for card_id, count in zip(eligible, counts):
            ways *= comb(pool[card_id], count)
        if ways:
            signature = tuple(card_id for card_id, count in zip(eligible, counts) if count)
            grouped[signature] = grouped.get(signature, 0) + ways
    outcomes = tuple(RevealSet(ways / denominator, signature)
                     for signature, ways in sorted(grouped.items()))
    mass = sum(outcome.probability for outcome in outcomes)
    if abs(mass - PROBABILITY_MAX) > HYPERGEOMETRIC_MASS_TOLERANCE:
        raise ValueError(f"reveal outcome mass {mass} != 1")
    return outcomes


def hypergeometric_classes(pool_ids, draws: int,
                           groups: tuple[OutcomeGroup, ...]) -> tuple[DrawClass, ...]:
    """Exact count classes for caller-declared disjoint card sets plus explicit remainder."""
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


__all__ = (
    "DrawClass", "DrawOutcome", "OutcomeGroup", "RevealSet",
    "draw_outcomes", "hypergeometric_classes", "reveal_sets",
)
