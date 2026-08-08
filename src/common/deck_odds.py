"""Odds — pure own-deck math (the ADR-0065 glossary term): the chance of drawing or reaching something
by a given draw window. No opinion about value (that is Worth, `card_worth.py`).

Three families, and nothing here ever raises. The first two fail in OPPOSITE directions; the third is
the first one's complement, so its 1.0 is the same refusal to endorse:

* the draw-window hypergeometrics are ENDORSERS — bad input → 0.0, so a gamble never fires on garbage.
* the window MISS (a dig's whiff, ADR-0133) is that same direction read the other way up — bad input
  → 1.0, "the look found nothing", so a dig is priced at its empty-handed board rather than a hit.
* the prize-split content estimate (ADR-0029) is a SUPPRESSOR — bad input → 1.0 ("assume present"), so
  a search is never stood down on garbage. It agrees with `deck_tracker`'s sound oracle at every
  extreme and only fills the uncertain middle that oracle declines to answer.

Pure, lib-free (``math.comb``), stateless.
"""
from __future__ import annotations

from math import comb


def draw_hit_probability(copies, pool, draws) -> float:
    """P(≥1 of ``copies`` among ``draws`` from ``pool``) — exact hypergeometric (ADR-0039). Overdraws
    clamp; bad input → 0.0, the ENDORSER direction, which is the MISS's 1.0 read the other way up."""
    return 1.0 - window_miss_probability(copies, pool, draws)


def window_miss_probability(marked, pool, window) -> float:
    """P(none of ``marked`` copies sit in a ``window``-card look at ``pool`` — a dig's whiff, and the
    bracket its every outcome class differences from (ADR-0133). Bad input → 1.0: a bad look finds nothing."""
    try:
        k, p, n = int(marked), int(pool), int(window)
    except Exception:
        return 1.0
    n = min(n, p)
    if n <= 0 or k <= 0:
        return 1.0
    if p - k < n:
        return 0.0
    return comb(p - k, n) / comb(p, n)


def draw_hit_with_engines(outs, pool, draws, engines, windows) -> float:
    """WP4's Stage-2 draw-engine two-window closed form (ADR-0065). EXACT at depth 1 (``outs`` and
    ``engines`` are DISJOINT); deeper stages approximate — measured error ≈ +0.6pp. Bad input → 0.0."""
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
    weight = (window_miss_probability(o, p, n)
              - window_miss_probability(o + e, p, n))   # missed, but drew ≥1 usable engine
    for k, m in enumerate(ws):
        pool_k -= drawn
        if pool_k <= 0 or weight <= 0.0 or m <= 0:
            break
        total += weight * draw_hit_probability(o, pool_k, m)
        e_left = e - (k + 1)                             # one engine consumed per activation
        if e_left <= 0:
            break
        weight *= (window_miss_probability(o, pool_k, m)
                   - window_miss_probability(o + e_left, pool_k, m))
        drawn = min(m, pool_k)
    return max(0.0, min(1.0, total))


def p_contains_at_least(unseen_copies, prizes_hidden, deck_count, k: int = 1) -> float:
    """P(my deck still holds at least ``k`` copies) — the hypergeometric CDF of the prize split, not just
    its ≥1 tail (a multi-card delivery may take TWO copies). Bad input → 1.0, the SUPPRESSOR direction."""
    try:
        u, hidden, d, need = (int(unseen_copies), int(prizes_hidden),
                              int(deck_count), int(k))
    except Exception:
        return 1.0
    if need <= 0:
        return 1.0                       # ">= 0 copies" is vacuously true
    if u < need or d < need:
        return 0.0                       # fewer unseen copies than asked, or a deck too small
    if hidden <= 0:
        return 1.0                       # no hidden prizes -> every unseen copy is in the deck
    if u - hidden >= need:
        return 1.0                       # pigeonhole: at most `hidden` copies can be prized
    h = d + hidden
    try:
        # `comb` returns 0 whenever u-j exceeds the prize slots, so the range needs no second bound.
        hit = sum(comb(d, j) * comb(hidden, u - j) for j in range(need, min(u, d) + 1))
        splits = comb(h, u)              # u <= h here (u <= hidden + d), so this is > 0
    except Exception:
        return 1.0
    if splits <= 0:
        return 1.0
    return max(0.0, min(1.0, hit / splits))


def p_contains(unseen_copies, prizes_hidden, deck_count) -> float:
    """P(my deck still contains ≥1 copy of a card) — the ``k = 1`` case of :func:`p_contains_at_least`,
    DELEGATED rather than restated so two closed forms of one model cannot drift."""
    return p_contains_at_least(unseen_copies, prizes_hidden, deck_count, 1)


def contains_odds(decklist, visible, deck_count, prizes_hidden) -> dict:
    """``{card_id: p_contains(...)}`` over ``decklist``, with ``visible`` counting copies provably
    outside deck+prizes. The Board exposes it as ``deck_contains_odds`` (ADR-0029)."""
    return {cid: p_contains(total - visible.get(cid, 0), prizes_hidden, deck_count)
            for cid, total in decklist.items()}
