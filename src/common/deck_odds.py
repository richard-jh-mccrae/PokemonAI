"""Probabilistic own-deck content estimate — the COMPLEMENT to the sound deck tracker (ADR-0029).

`deck_tracker.OwnCardModel` is **certain-or-silent**: it resolves the prize split EXACTLY (only after a
search reveals the whole deck) and otherwise reports the sound pigeonhole bounds — it never guesses
(`Board.deck_definitely_empty_of` / `deck_definitely_has` are sound, see ADR-0023, the
sound-deck-emptiness-oracle memory). That is the right epistemics for an availability *gate* (never
suppress a search that COULD still hit). But prizes are usually hidden early, so the sound oracle is
silent on the common "should I keep hunting card C?" question — e.g. play a 2nd Buddy-Buddy Poffin that
*might* whiff because the last Staryu *might* be prized.

This module answers that PROBABILISTIC question the sound oracle declines. **Model:** a card's UNSEEN
copies (decklist − visible) are split between the hidden deck and the face-down prizes. Treating the
``prizes_hidden`` face-down slots as a uniformly random subset of the ``deck_count + prizes_hidden``
unseen positions (exchangeability), the count of those copies that are prized is hypergeometric, so

    P(deck still holds ≥1 copy of C) = 1 − C(K, u) / C(H, u),   K = prizes_hidden, H = deck_count + K, u = unseen

It **agrees with the sound oracle at the extremes** — never contradicts it, only fills the uncertain
middle: ``u == 0`` → 0.0 (every copy seen ⇒ sound-empty), ``u > K`` → 1.0 (more unseen copies than
prize slots ⇒ pigeonhole-present), ``K == 0`` → 1.0 (no hidden prizes ⇒ every unseen copy is in the
deck), ``deck_count == 0`` → 0.0 (an empty deck holds nothing; all unseen copies are prized).

Pure, lib-free (``math.comb``), **never raises** (grader safety): any bad input collapses to **1.0**
("assume present"), the conservative direction — a probabilistic suppressor must never stand a search
down on garbage. Stateless: a snapshot function of the visible board, not match-scoped state.
"""
from __future__ import annotations

from math import comb


def draw_hit_probability(copies, pool, draws) -> float:
    """P(≥1 of ``copies`` target cards among ``draws`` cards drawn from a ``pool``) — the exact
    hypergeometric ``1 − C(pool−copies, draws) / C(pool, draws)`` behind a Gamble Line's Outcome
    Classes (ADR-0039). Draws beyond the pool are clamped; never raises — bad input → **0.0**, the
    conservative direction for an ENDORSER (a gamble must never fire on garbage; contrast
    ``p_contains``'s 1.0 default, which guards a SUPPRESSOR)."""
    try:
        c, p, n = int(copies), int(pool), int(draws)
    except Exception:
        return 0.0
    if c <= 0 or p <= 0:
        return 0.0
    n = min(n, p)
    if n <= 0:
        return 0.0
    if c >= p:
        return 1.0
    return 1.0 - comb(p - c, n) / comb(p, n)


def p_contains(unseen_copies, prizes_hidden, deck_count) -> float:
    """P(my deck still contains ≥1 copy of a card) from the hypergeometric split of its ``unseen_copies``
    over the ``deck_count + prizes_hidden`` hidden positions (of which ``prizes_hidden`` are face-down
    prizes). Returns a float in ``[0, 1]``; never raises (any bad input → 1.0, "assume present")."""
    try:
        u, k, d = int(unseen_copies), int(prizes_hidden), int(deck_count)
    except Exception:
        return 1.0
    if u <= 0:
        return 0.0                       # every copy seen outside deck -> sound-EMPTY
    if d <= 0:
        return 0.0                       # deck empty -> holds nothing (all unseen are prized)
    if k <= 0:
        return 1.0                       # no hidden prizes -> every unseen copy is in deck
    if u > k:
        return 1.0                       # more unseen copies than prize slots -> pigeonhole: ≥1 in deck
    h = d + k
    try:
        p_all_prized = comb(k, u) / comb(h, u)   # u ≤ k ≤ h -> comb(h, u) > 0, no division by zero
    except Exception:
        return 1.0
    return max(0.0, min(1.0, 1.0 - p_all_prized))


def contains_odds(decklist, visible, deck_count, prizes_hidden) -> dict:
    """``{card_id: p_contains(...)}`` over every card in ``decklist`` (a ``{id: count}`` mapping), using
    ``visible`` (a ``{id: count}`` of copies provably outside deck+prizes) for the unseen count. The
    per-card form the Board exposes as ``deck_contains_odds`` (ADR-0029)."""
    return {cid: p_contains(total - visible.get(cid, 0), prizes_hidden, deck_count)
            for cid, total in decklist.items()}
