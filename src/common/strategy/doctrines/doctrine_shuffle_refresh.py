"""Shuffle-refresh probability helpers; Issue #459 retires its shared valuation rungs."""
from __future__ import annotations

from math import comb

from common.strategy.context import _PLAY
from common.strategy.refresh import refresh_branches


def _draw_branches(card_id, b):
    """Return my draw-count branches when the card's refresh rule is known."""
    branches = refresh_branches(card_id, b.my_prizes_remaining, b.opp_prizes_remaining)
    return None if branches is None else tuple(my_draw for my_draw, _opp in branches)


_MISS_PROB_THRESHOLD = 0.20


class ShuffleRefreshMixin:
    """Pilot helper for the shuffle-grown-pool probable-miss read."""

    def _refresh_probable_miss(self, option: dict, cid: int | None, tags: list, board, obs: dict,
                               plan) -> bool:
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
            return 1.0 - comb(pool - k, n) / comb(pool, n)

        return sum(p_hit(n) for n in branches) / len(branches) < _MISS_PROB_THRESHOLD


# Target-runtime shuffle valuations are composer-owned (Issue #459).
HYPOTHESES = []
