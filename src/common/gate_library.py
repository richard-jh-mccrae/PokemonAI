"""Gate library — the DEADLINE leg of the card-worth oracle (ADR-0065).

`keep_cost = role_value × [P(need met by deadline | keep) − P(met | shuffle)]`. The keep-value sites
already model the second bracket term as the closure re-access odds; this module supplies the FIRST,
as a plain FACTOR of the one equation and never a new if/else rung (the currency-zone rule).

Four gates: the EVOLUTION gate (an evolution with no reachable base is a dead card), the FETCHER gate
(a searcher whose every target is provably dead), the PRESSURE gate (a closing edge SPIKES keep-cost
— decay constants are wrong-shaped for cliffs), and the QUOTA gate (later copies of a once-per-turn
card earn turns of natural draws before their deadline).

Pure over card FACTS: the caller resolves every predicate and passes booleans and integers.
"""
from __future__ import annotations


def is_evolution(stat) -> bool:
    """True iff ``stat`` is an evolution — the only card class whose role realisation is gated on a
    separate base today."""
    return bool(stat is not None and getattr(stat, "evolvesFrom", None))


def deploy_odds(stat, *, playable: bool = True) -> float:
    """P(the card's ROLE can be realised by its deadline). ``playable`` is `common.playability`'s
    answer (ADR-0104), never re-derived here. Errs toward 1.0 (keep)."""
    if not is_evolution(stat):
        return 1.0
    return 1.0 if playable else 0.0


def fetch_deploy_odds(*, targets_exhausted: bool = False) -> float:
    """P(a fetch TRAINER's role is realisable): 0.0 when EVERY target it can pull is PROVABLY dead.
    Errs toward keep — an unsound or uncertain deadness read must stay ``False`` upstream."""
    return 0.0 if targets_exhausted else 1.0


def need_met_odds(*, need_met: bool = False) -> float:
    """The need-met gate — the fetcher gate's COUSIN, for a role already SATISFIED rather than a target
    provably dead. Errs toward keep."""
    return 0.0 if need_met else 1.0


def closing_gate_reaccess(reaccess: float, *, gate_closing: bool = False) -> float:
    """The pressure gate: with the gate closing NOW a probabilistic redraw is not an answer the plan can
    bank on, so re-access credit is 0.0 and ``keep_cost`` charges full worth. Errs toward ``False``."""
    return 0.0 if gate_closing else reaccess


def quota_window(draws: int, copy_rank: int, *, quota_spent: bool = False,
                 draws_per_turn: int = 1) -> int:
    """The quota gate: the re-access window for the ``copy_rank``-th copy of a ONCE-PER-TURN card. Its
    deadline sits ``copy_rank − 1`` turns away, each adding ``draws_per_turn`` guaranteed draws."""
    turns_away = max(0, copy_rank - 1) + (1 if quota_spent else 0)
    return draws + turns_away * max(0, draws_per_turn)
