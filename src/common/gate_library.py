"""Gate library — the DEADLINE leg of the card-worth oracle (ADR-0065 §Round 8-9;
``docs/plans/gate-library-scope.md``).

`keep_cost = role_value × [P(need met by deadline | keep) − P(met | shuffle)]`. The keep-value sites
already model the second bracket term as the closure re-access odds; this module supplies the FIRST —
``deploy_odds``, P(the card's ROLE is realisable by its deadline) — as a plain factor of the ONE
equation, never a new if/else rung (the currency-zone rule).

Stage 1 is the **evolution gate**: an evolution card realises its role only by being played onto a
base. If that base is provably gone (not in play, hand, or the deck), the card is dead — its keep-value
collapses, so a refresh / gamble sheds it freely to dig, instead of hoarding it (ep83966336 f44, the
retired ``hold-wincon-dont-shuffle`` ``wincon_in_hand_undeployable`` stand-down, now graded).

Pure over card FACTS: the caller resolves base presence from the Board / deck and passes the three
booleans. Later stages (quota / recycler / pressure gates) extend the same ``deploy_odds`` seam.

The discard convergence (ADR-0066) adds ``role_met_bracket`` — the WHOLE bracket
``P(met | keep) − P(met | pitch)`` for a forced-discard pitch, composed from the same premise
vocabulary the retired `_DISCARD` ladder carried: the deploy-NOW spike, the job-done gates, the
surplus-energy gate, and the cover discounts. Still pure: the caller (the fetch doctrine) resolves
every fact from the Board / obs and passes booleans + odds.
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


def role_met_bracket(*, job_done: bool = False, deployable: bool = True,
                     evolvable_now: bool = False, sole_cover: bool = False,
                     energy_surplus: bool = False, covered: bool = False,
                     reaccess_odds: float = 0.0) -> float:
    """``P(role met by its deadline | keep) − P(met | pitch)`` for a forced-discard pitch — the
    bracket of the ONE keep-cost equation (ADR-0066), composed from premise gates in priority order:

    - ``job_done``    → 0.0: the role is already realised or void (a wincon tutor with the wincon in
      hand, a setup-only opener mid-game, a burst Energy on a fully-powered Active) — keeping the
      card adds nothing, so it pitches free.
    - ``not deployable`` → 0.0: the Stage-1 evolution gate — the role can NEVER be realised (base
      gone from every zone), a dead card.
    - ``evolvable_now and sole_cover`` → 1.0: the deploy-NOW spike. An in-play body this card can
      evolve THIS turn, and no other held copy covers the play — keeping meets the deadline with
      certainty, pitching forfeits it (re-access cannot land this turn). Full worth.
    - ``energy_surplus`` → 0.0: a typed Basic Energy on a board that is not energy-starved cycles
      freely (the starved keep is the caller passing ``energy_surplus=False`` only when my Active
      carries zero Energy).
    - ``covered`` → 0.0: an in-play or another in-hand copy already carries the job, so
      ``P(met | pitch) = P(met | keep)`` — the marginal copy pitches FREE, tying (at 0) with the
      no-claim crowd rather than out-keeping it (ep82867148 f48: the duplicate Lillie's goes before
      a lone disruptor only via the tie, exactly the retired ladder's net effect).
    - otherwise ``(1 − reaccess_odds)``.

    Pure over passed facts; clamped to [0, 1]."""
    if job_done or not deployable:
        return 0.0
    if evolvable_now and sole_cover:
        return 1.0
    if energy_surplus or covered:
        return 0.0
    return max(0.0, min(1.0, 1.0 - reaccess_odds))
