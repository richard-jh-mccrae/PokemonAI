"""Live bench-damage reach from typed Attack clauses."""
from __future__ import annotations


def bench_reach(attack) -> int:
    """Maximum damage one attack can concentrate on a single Benched target."""
    snipe = attack.clause("bench_snipe")
    spread = attack.clause("bench_spread")
    return max(int(snipe.amount or 0) if snipe is not None else 0,
               int(spread.amount or 0) if spread is not None else 0)


__all__ = ("bench_reach",)
