"""DOCTRINE: Shuffle-Refresh — ADR-0024. One file, end to end.

A Shuffle-Refresh Supporter shuffles your whole hand into the deck then draws (Function Tag
`shuffle_hand`). It presents NO select, so it is Fetch's whether-to-play decision only, and it REUSES
Fetch's `_grab_value_of` for the gain side rather than restating a value model. The refresh is ENDORSED
by default; the keep-value floors guard the narrow bad shuffles and Layer B adds one deck-side veto.
"""
from __future__ import annotations

from math import comb

from common.strategy.context import _PLAY
from common.strategy.refresh import refresh_branches
from common.strategy.strategy import Hypothesis

def _draw_branches(card_id, b):
    """How many cards *I* draw, as the coin/condition BRANCHES. A shuffle_hand card with no facts in
    `strategy/refresh.py` gets NO probabilistic claim (fail-silent)."""
    branches = refresh_branches(card_id, b.my_prizes_remaining, b.opp_prizes_remaining)
    return None if branches is None else tuple(my_draw for my_draw, _opp in branches)

# P(≥1 needed card among the N drawn) below this -> the refresh is a probable re-roll of dregs.
# Consistent with doctrine_fetch._WHIFF_PROB_THRESHOLD (the sibling search guard, ADR-0029).
_MISS_PROB_THRESHOLD = 0.20


class ShuffleRefreshMixin:
    """The Pilot-side closed-form half of the Shuffle-Refresh doctrine (mixed into `Pilot`). No new value
    model — `_refresh_probable_miss` reuses Fetch's `_grab_value_of`."""

    def _refresh_probable_miss(self, option: dict, cid: int | None, tags: list, board, obs: dict,
                               plan) -> bool:
        """POST-ANCHOR probabilistic pull-EV (ADR-0024 amendment): True iff this PLAY's draw PROBABLY misses
        every needed card, over the shuffle-GROWN pool. Silent without the tracker anchor or a draw-count."""
        if option.get("type") != _PLAY or "shuffle_hand" not in tags:
            return False
        counts = board.deck_known_counts
        branches = _draw_branches(cid, board)
        if not counts or branches is None:
            return False
        k = sum(n for c2, n in counts.items() if n > 0 and self._grab_value_of(board, c2, plan) > 0)
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
    # Four flat hold-guards RETIRED (ADR-0065, ADR-0101) — the GRADED SHED prices them. `dont-refresh-for-
    # nothing` (−40) was built THEN DELETED at the 2026-07-03 A/B; the rung below owns the whole deck side.
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
    # `refresh-when-hand-is-dead` (+8) RETIRED (ADR-0024 amendment): `dig-before-commit` plays a
    # dead-hand refresh anyway, so the rung and its full-menu scan added compute, no behavior.
]
