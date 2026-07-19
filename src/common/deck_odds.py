"""Odds — pure own-deck math (the ADR-0065 glossary term): the chance of drawing, reaching, or
rebuilding something by a given draw window. No opinion about value (that is Worth, `card_worth.py`).

Two families, two fail directions (grader safety — nothing here ever raises):

* **Draw-window hypergeometrics** — `draw_hit_probability` (P(≥1 target in the drawn window), the
  form behind a Gamble Line's Outcome Classes, ADR-0039) and `draw_hit_with_engines` (the Stage-2
  draw-engine two-window closed form, WP4). ENDORSERS: bad input → **0.0** — a gamble must never
  fire on garbage.
* **The prize-split content estimate** — `p_contains` / `contains_odds`, the probabilistic
  COMPLEMENT to the sound deck tracker (ADR-0029), detailed below. SUPPRESSORS: bad input → **1.0**
  ("assume present") — a probabilistic suppressor must never stand a search down on garbage.

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

Pure, lib-free (``math.comb``), stateless: snapshot functions of the visible board, never
match-scoped state. Each function's docstring states its own conservative fail direction.
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


def _none_of(k, pool, n) -> float:
    """P(none of ``k`` marked cards among ``n`` drawn from ``pool``) — the miss ratio both bracket
    terms of the Stage-2 form are built from. Overdraws clamp; drawing more than ``pool − k`` cards
    must include a marked one (0.0)."""
    n = min(n, pool)
    if n <= 0:
        return 1.0
    if pool - k < n:
        return 0.0
    return comb(pool - k, n) / comb(pool, n)


def draw_hit_with_engines(outs, pool, draws, engines, windows) -> float:
    """WP4 — the Stage-2 draw-engine **two-window closed form** (hypergeometric-fetch-closure §Stage 2):

        P(assemble) = P(≥1 out in n)
                    + [P(no out in n) − P(no out ∧ no usable engine in n)] × P(≥1 out in m | pool−n)

    iterated once per board-supported engine stage (``windows`` — the caller derives the depth from
    eligible pre-evo/engine pairings, never a constant). ``outs`` and ``engines`` are DISJOINT card
    classes, so at depth 1 the form is EXACT (conditioning on a missed window leaves the outs uniform
    in the thinned pool — pinned against exhaustive enumeration). Deeper stages reuse the same two
    ``comb`` ratios over the thinned pool with one engine consumed per stage — the engine-availability
    term there is the documented approximation (the spec's measured depth-2 magnitude ≈ +0.6pp).
    Window-2 outs are the SAME class outs (the full Stage-1 union — spec §recursion point 4).
    Degenerates to ``draw_hit_probability`` with no engines/windows; bad input → 0.0 (an endorser
    fails closed); the total is clamped to a probability."""
    try:
        o, p, n, e = int(outs), int(pool), int(draws), int(engines)
        ws = tuple(int(w) for w in windows)
    except Exception:
        return 0.0
    if o <= 0 or p <= 0 or n <= 0:
        return 0.0
    base = draw_hit_probability(o, p, n)
    if e <= 0 or not ws:
        return base
    total = base
    pool_k = p
    drawn = min(n, p)
    weight = _none_of(o, p, n) - _none_of(o + e, p, n)   # missed, but drew ≥1 usable engine
    for k, m in enumerate(ws):
        pool_k -= drawn
        if pool_k <= 0 or weight <= 0.0 or m <= 0:
            break
        total += weight * draw_hit_probability(o, pool_k, m)
        e_left = e - (k + 1)                             # one engine consumed per activation
        if e_left <= 0:
            break
        weight *= _none_of(o, pool_k, m) - _none_of(o + e_left, pool_k, m)
        drawn = min(m, pool_k)
    return max(0.0, min(1.0, total))


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
