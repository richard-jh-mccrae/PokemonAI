"""Live bench-damage reach from typed Attack clauses."""
from __future__ import annotations


def bench_reach(attack) -> int:
    """Maximum damage one attack can concentrate on a single Benched target."""
    snipe = attack.clause("bench_snipe")
    spread = attack.clause("bench_spread")
    snipe_amount = (int(snipe.amount or 0) if snipe is not None
                     and snipe.target != "own_bench" else 0)
    spread_amount = (int(spread.amount or 0) if spread is not None
                     and spread.target != "own_bench" else 0)
    return max(snipe_amount, spread_amount)


__all__ = ("bench_reach",)
