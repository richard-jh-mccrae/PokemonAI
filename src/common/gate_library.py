"""Gate library — the DEADLINE leg of the card-worth oracle (ADR-0065; grill Rounds 8-9 of
``docs/archive/plans/hypergeometric-fetch-closure.md``; the scope/staging plan doc is retired — all four
gate legs are built, see ADR-0065 §Build status).

`keep_cost = role_value × [P(need met by deadline | keep) − P(met | shuffle)]`. The keep-value sites
already model the second bracket term as the closure re-access odds; this module supplies the FIRST —
``deploy_odds``, P(the card's ROLE is realisable by its deadline) — as a plain factor of the ONE
equation, never a new if/else rung (the currency-zone rule).

Stage 1 is the **evolution gate**: an evolution card realises its role only by being played onto a
base. If nothing it can be put onto can reach the board, the card is dead — its keep-value
collapses, so a refresh / gamble sheds it freely to dig, instead of hoarding it (ep83966336 f44, the
retired ``hold-wincon-dont-shuffle`` ``wincon_in_hand_undeployable`` stand-down, now graded). WHETHER
it can is `common.playability`'s question (ADR-0104), resolved by the caller and passed in as one
boolean; this module only prices the answer.

The **fetcher gate** (`fetch_deploy_odds`) is the searcher/recycler leg (scope doc stage 3, pulled
forward 2026-07-19 by the duplicate-copy reconciliation — acceptance pin ep83457493 f31): a fetch
Trainer whose EVERY target is provably dead realises no role either.

The **pressure gate** (`closing_gate_reaccess` — scope doc stage 3's fold, built 2026-07-19) is the
CLOSING edge (spec Round 8 §3): when the Active is doomed, the held cards that ANSWER the doom (the
successor wincon with its base in play; the clutch heal/switch) have a deadline a probabilistic
redraw cannot be banked against — their re-access credit zeroes, so they charge full worth. This
retired the flat `hold-successor-when-doomed` rung (ep83037962 f49) into the one equation.

The **quota gate** (`quota_window` — built 2026-07-19) derives the k-th-copy deadline of a
once-per-turn card (Energy attach / Supporter slot): later ranks earn turns of natural draws before
their deadline, so duplicate holds shed by RANK instead of uniformly.

Pure over card FACTS: the caller resolves base presence / target deadness / the doom read / copy
ranks from the Board / deck and passes booleans and integers. The one remaining gate-adjacent piece
— the discard-side deploy-now spike (`86091435-68`) — is owned by the discard convergence
(``docs/plans/seam-discard-convergence.md``), not this module's seam.
"""
from __future__ import annotations


def is_evolution(stat) -> bool:
    """True iff ``stat`` is an evolution (has a previous stage, ``CardStat.evolvesFrom``) — the only
    card class whose role realisation is gated on a separate base today."""
    return bool(stat is not None and getattr(stat, "evolvesFrom", None))


def deploy_odds(stat, *, playable: bool = True) -> float:
    """P(the card's ROLE can be realised by its deadline) — the deadline factor of ``keep_cost``.

    1.0 for a non-evolution (its role is realised by being held) or a PLAYABLE evolution. 0.0 for a
    provably UNPLAYABLE one — nothing it could be put onto can reach the board, so the card cannot
    realise its role at all (a dead card). Errs toward 1.0 (keep) — an unsure caller passes
    ``playable=True`` and nothing is discounted.

    ``playable`` used to be three zone booleans OR-ed together here (base in play / in hand /
    reachable in deck). Issue #288 moved that question whole into `common.playability`, because the
    OR was only the shallowest correct version of it: the real question walks the ``evolvesFrom``
    CHAIN and knows the Rare Candy escape, and a second, shallower answer living here would have
    disagreed with the eligibility gate about the very same card. This module keeps what it is for —
    the arithmetic of a gate — and none of the graph reasoning."""
    if not is_evolution(stat):
        return 1.0
    return 1.0 if playable else 0.0


def fetch_deploy_odds(*, targets_exhausted: bool = False) -> float:
    """P(a fetch TRAINER's role is realisable) — the searcher/recycler leg of the deadline gate.

    0.0 when EVERY target the card can pull is PROVABLY dead — the caller resolves that from the
    SAME sound predicates the play-side rungs already trust (`dont-search-an-empty-deck`'s
    deck-whiff set, `dont-recycle-the-dead`'s all-dead discard pool): a fetcher that can fetch
    nothing realises no role, so it sheds freely (its residual worth is Ultra-Ball fodder —
    corrections 85046350-79 / 85058574-16). 1.0 otherwise — errs toward keep, exactly like the
    evolution gate; an unsound or uncertain deadness read must stay ``False`` upstream."""
    return 0.0 if targets_exhausted else 1.0


def need_met_odds(*, need_met: bool = False) -> float:
    """The need-met gate — the fetcher gate's COUSIN, for a role already SATISFIED rather than a
    target provably dead. 0.0 when the card's reason-to-keep is already fulfilled by the board (a
    wincon-tutor whose wincon is IN HAND — its fetch has nothing left worth finding; ladder-win
    case ep82753102 f16), 1.0 otherwise. Errs toward keep — an uncertain 'need met' read stays
    ``False`` upstream."""
    return 0.0 if need_met else 1.0


def closing_gate_reaccess(reaccess: float, *, gate_closing: bool = False) -> float:
    """The pressure gate — the CLOSING edge (spec Round 8 §3: "a closing edge SPIKES keep-cost;
    decay constants are wrong-shaped for cliffs").

    ``P(met | shuffle)`` counts re-access only if it arrives before the card's gate closes. When
    the gate is closing NOW — the Active is doomed and this card is the answer (the successor
    win-condition with its base in play, ep83037962 f49; the clutch heal/switch) — a probabilistic
    redraw is not an answer the plan can bank on: the re-access credit is **0.0**, so ``keep_cost``
    charges the card's full role worth. Pass-through otherwise (the closure discount applies).
    The caller resolves ``gate_closing`` from sound Board facts and errs toward ``False`` (the
    cheaper, closure-discounted keep) when uncertain."""
    return 0.0 if gate_closing else reaccess


def quota_window(draws: int, copy_rank: int, *, quota_spent: bool = False,
                 draws_per_turn: int = 1) -> int:
    """The quota gate (spec Round 8 §2: resource quotas ARE gates): the re-access window for the
    ``copy_rank``-th held copy of a ONCE-PER-TURN card — 1 manual Energy attach, 1 Supporter per
    turn (rules.md §3). Its deadline sits ``copy_rank − 1`` turns away (+1 when this turn's quota
    is already spent), and every intervening turn adds ``draws_per_turn`` natural draws of
    re-access before that copy is needed — so "the 3rd hand Energy is near-free to shuffle: two
    turns of draws + closure stand before its deadline" is DERIVED, not asserted. Rank 1 with the
    quota live keeps the plain window (behaviour unchanged); the widening is the MINIMAL honest one
    (the guaranteed turn draw only — engines/tutors beyond it are not counted)."""
    turns_away = max(0, copy_rank - 1) + (1 if quota_spent else 0)
    return draws + turns_away * max(0, draws_per_turn)
