"""Gate library — the DEADLINE leg of the card-worth oracle (ADR-0065; grill Rounds 8-9 of
``docs/plans/hypergeometric-fetch-closure.md``; scope + staging ``docs/plans/gate-library-scope.md``).

`keep_cost = role_value × [P(need met by deadline | keep) − P(met | shuffle)]`. The keep-value sites
already model the second bracket term as the closure re-access odds; this module supplies the FIRST —
``deploy_odds``, P(the card's ROLE is realisable by its deadline) — as a plain factor of the ONE
equation, never a new if/else rung (the currency-zone rule).

Stage 1 is the **evolution gate**: an evolution card realises its role only by being played onto a
base. If that base is provably gone (not in play, hand, or the deck), the card is dead — its keep-value
collapses, so a refresh / gamble sheds it freely to dig, instead of hoarding it (ep83966336 f44, the
retired ``hold-wincon-dont-shuffle`` ``wincon_in_hand_undeployable`` stand-down, now graded).

The **fetcher gate** (`fetch_deploy_odds`) is the searcher/recycler leg (scope doc stage 3, pulled
forward 2026-07-19 by the duplicate-copy reconciliation — acceptance pin ep83457493 f31): a fetch
Trainer whose EVERY target is provably dead realises no role either.

Pure over card FACTS: the caller resolves base presence / target deadness from the Board / deck and
passes booleans. Later stages (quota / pressure gates) extend the same ``deploy_odds`` seam.
"""
from __future__ import annotations


def is_evolution(stat) -> bool:
    """True iff ``stat`` is an evolution (has a previous stage, ``CardStat.evolvesFrom``) — the only
    card class whose role realisation is gated on a separate base today."""
    return bool(stat is not None and getattr(stat, "evolvesFrom", None))


def deploy_odds(stat, *, base_in_play: bool = False, base_in_hand: bool = False,
                base_reachable_in_deck: bool = False) -> float:
    """P(the card's ROLE can be realised by its deadline) — the deadline factor of ``keep_cost``.

    1.0 for a non-evolution (its role is realised by being held) or a DEPLOYABLE evolution — its base
    is on board, in hand, or still reachable in the deck (any one suffices). 0.0 for a provably
    UNDEPLOYABLE evolution — the base is gone from every retrievable zone, so the card cannot realise
    its role at all (a dead card). Errs toward 1.0 (keep) — a caller unsure of base presence passes
    ``base_reachable_in_deck=True`` and nothing is discounted."""
    if not is_evolution(stat):
        return 1.0
    return 1.0 if (base_in_play or base_in_hand or base_reachable_in_deck) else 0.0


def fetch_deploy_odds(*, targets_exhausted: bool = False) -> float:
    """P(a fetch TRAINER's role is realisable) — the searcher/recycler leg of the deadline gate.

    0.0 when EVERY target the card can pull is PROVABLY dead — the caller resolves that from the
    SAME sound predicates the play-side rungs already trust (`dont-search-an-empty-deck`'s
    deck-whiff set, `dont-recycle-the-dead`'s all-dead discard pool): a fetcher that can fetch
    nothing realises no role, so it sheds freely (its residual worth is Ultra-Ball fodder —
    corrections 85046350-79 / 85058574-16). 1.0 otherwise — errs toward keep, exactly like the
    evolution gate; an unsound or uncertain deadness read must stay ``False`` upstream."""
    return 0.0 if targets_exhausted else 1.0
