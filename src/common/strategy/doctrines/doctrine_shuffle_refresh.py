"""DOCTRINE: Shuffle-Refresh — ADR-0024. One file, end to end.

A Shuffle-Refresh Supporter shuffles your whole hand into the deck then draws (Lillie's Determination,
Judge, Harlequin, Lacey; Function Tag `shuffle_hand`). It presents NO select, so it is the Fetch
comparator's decision (A) ONLY — *whether to play it* — and it REUSES Fetch's `_grab_value_of` for the
gain side rather than restating a value model. Post-refutation (2026-06-30, ~3:1 mirror cost of
hoarding) the refresh is ENDORSED by default (`dig-before-commit` +20, hand-blind — tier-3 sequencing
means it only ever sees the residual dregs); the keep-value floors guard the narrow bad shuffles, and
Layer B (ADR-0024 amendment, revised at the 2026-07-03 A/B) adds ONE deck-side suppressor: the
post-anchor pull-EV `dont-refresh-into-a-probable-miss` over `_DRAW_COUNTS` (its K=0 case covers the
spent deck; the broader pre-anchor sound veto regressed and was deleted). `ShuffleRefreshMixin` is
the Pilot-side `_refresh_probable_miss`. See docs/general-strategy.md and
docs/adr/0024-shuffle-refresh-is-fetch-decision-a-over-keep-value.md.
"""
from __future__ import annotations

from math import comb

from common.strategy.context import _PLAY
from common.strategy.refresh import refresh_branches
from common.strategy.strategy import Hypothesis

def _draw_branches(card_id, b):
    """How many cards *I* draw, as the coin/condition BRANCHES (P averaged exactly over them).

    ADR-0060: the draw-count facts now live ONCE, in `strategy/refresh.py`, keyed per branch as
    (my_draw, opp_draw) — this reads MY half of them. The old id-keyed `_DRAW_COUNTS` dict here was
    a second copy of the same card text and had silently drifted: it was **missing Unfair Stamp
    (1080)** entirely, so `dont-refresh-into-a-probable-miss` could never fire on it.

    A shuffle_hand card with no facts gets NO probabilistic claim (fail-silent, unchanged)."""
    branches = refresh_branches(card_id, b.my_prizes_remaining, b.opp_prizes_remaining)
    return None if branches is None else tuple(my_draw for my_draw, _opp in branches)

# P(≥1 needed card among the N drawn) below this -> the refresh is a probable re-roll of dregs.
# Consistent with doctrine_fetch._WHIFF_PROB_THRESHOLD (the sibling search guard, ADR-0029).
_MISS_PROB_THRESHOLD = 0.20


class ShuffleRefreshMixin:
    """The Pilot-side closed-form half of the Shuffle-Refresh doctrine (mixed into `Pilot`). No new
    value model — `_refresh_probable_miss` reuses Fetch's `_grab_value_of`. Reads shared Pilot
    helpers + the per-decision `Board`. (`_deck_holds_a_need`/`_has_shuffle_refresh` DELETED with the
    `dont-refresh-for-nothing` rung at the 2026-07-03 A/B — see the HYPOTHESES note.)"""

    def _refresh_probable_miss(self, option: dict, cid: int | None, tags: list, board, obs: dict,
                               plan) -> bool:
        """POST-ANCHOR probabilistic pull-EV (ADR-0024 amendment): True iff this `shuffle_hand` PLAY's
        N-card draw PROBABLY misses every needed card — hypergeometric P(≥1 need in N) below
        `_MISS_PROB_THRESHOLD` over the shuffle-GROWN pool (deck + returned hand − the played card;
        returned dregs dilute, they never add needs — a held card is by definition not lacking).
        K = 0 (a provably-spent deck) gives P = 0 and fires. Requires the tracker anchor
        (`deck_known_counts`) and a verified draw-count (`refresh.refresh_branches`); silent otherwise."""
        if option.get("type") != _PLAY or "shuffle_hand" not in tags:
            return False
        counts = board.deck_known_counts
        branches = _draw_branches(cid, board)
        if not counts or branches is None:
            return False
        k = sum(n for c2, n in counts.items() if n > 0 and self._grab_value_of(obs, board, c2) > 0)
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        me = players[yi] if 0 <= yi < len(players) and players[yi] else {}
        pool = sum(counts.values()) + max(0, len(me.get("hand") or []) - 1)
        if pool <= 0:
            return False

        def p_hit(n: int) -> float:
            n = min(n, pool)
            if n <= 0:
                return 0.0
            return 1.0 - comb(pool - k, n) / comb(pool, n)   # comb(a<b)=0 -> P=1 when a draw must hit

        return sum(p_hit(n) for n in branches) / len(branches) < _MISS_PROB_THRESHOLD

    # `_hand_is_dead` (the full real-menu play-scan) RETIRED with its rung — see the HYPOTHESES note.


# ── keep-value floors (Layer A) + the Layer-B deck-side suppressors (ADR-0024 amendment) ──
HYPOTHESES = [
    Hypothesis(
        id="attach-before-hand-shuffle",
        rationale="Attach held Energy BEFORE playing a `shuffle_hand` card (Harlequin / Lillie's "
                  "Determination), since that card discards any Energy still in hand — playing it first "
                  "wastes the attach and can shuffle away a game-winning Energy. Fires only with a "
                  "reusable Energy in hand, not yet attached this turn; belt-and-suspenders with "
                  "`_finish_turn_last`'s structural tiering (tier 3 shuffle after tier-2 attach). Stands "
                  "down when the Energy has NO placeable home (`not energy_placeable`), so it never vetoes "
                  "a bench-finding refresh (ep83038055 f40).",
        when=lambda c: c.option_type == _PLAY and "shuffle_hand" in c.tags
        and c.board.reusable_energy_in_hand and not c.board.energy_attached
        and c.board.energy_placeable,
        weight=-60, status="testing"),
    # `hold-wincon-dont-shuffle` (−25), `hold-line-piece-dont-shuffle` (−25) and
    # `hold-wincon-with-base-dont-shuffle` (−15) RETIRED 2026-07-18 (ADR-0065): they were the flat
    # SHED's hand-QUALITY proxy — a fixed penalty for holding a specific good card that the flat
    # `_REFRESH_SHED × cards-lost` couldn't see. The SHED is GRADED (`pilot._refresh_shed_keepcost`;
    # since ADR-0101 the v2 assignment SET marginal over the whole hand, not a per-copy sum), so a held
    # wincon/line-piece is priced by what the board would actually lose — the guards fold into that one currency (the
    # currency-zone rule: replace the family, never bolt on beside it). `hold-successor-when-doomed`
    # (−35) RETIRED 2026-07-19 — the LAST flat refresh guard: its `active_doomed` premise is now the
    # PRESSURE GATE (`gate_library.closing_gate_reaccess` via `planner._gate_closing`, the Round-8 §3
    # closing-edge spike): under doom the held successor / clutch answers charge FULL role worth in
    # the graded SHED (re-access is not bankable against the doom deadline), so the fold is a
    # parameter of the one equation, not a rung. Anchor ep83037962 f49 re-audited (the substance pin
    # + the synthetic pair in test_blunder_20260701.py).
    # `dont-refresh-for-nothing` (−40, the sound deck_holds_a_need veto) was built THEN DELETED at the
    # 2026-07-03 A/B (43%/47% regressions): grab-rung "needs" under-count refresh VALUE for a deck
    # whose engine is the refresh itself, and the veto fired on that false premise all game. The
    # post-anchor rung below owns the whole deck side instead (its K=0 case covers the spent deck).
    Hypothesis(
        id="dont-refresh-into-a-probable-miss",
        rationale="Layer B's deck-side veto (ADR-0024 amendment), POST-ANCHOR only: the N-card draw "
                  "probably misses every needed card (`Context.refresh_probable_miss` — hypergeometric "
                  "P(≥1 need) < 0.20 over the shuffle-grown pool, N from the verified `_DRAW_COUNTS` "
                  "incl. the 8-draw windows; K = 0, the provably-spent deck, gives P = 0 and fires "
                  "too). −25 cancels the lone `dig-before-commit` +20 (a guess, not a fact — cf "
                  "`dont-search-a-probable-whiff`); disruption motives (+25/+18) still clear it. "
                  "A/B 2026-07-03: neutral (50%, CI 47-53) — the pre-anchor sound veto it replaced "
                  "regressed and was deleted.",
        when=lambda c: c.option_type == _PLAY and "shuffle_hand" in c.tags
        and c.refresh_probable_miss,
        weight=-25, status="testing"),
    # `refresh-when-hand-is-dead` (+8) RETIRED 2026-07-03 (ADR-0024 amendment): post-refutation the
    # +20 `dig-before-commit` endorsement plays a dead-hand refresh anyway (nothing else is endorsed),
    # so the rung and its full-menu `hand_is_dead` scan added compute and test surface, no behavior.
]
