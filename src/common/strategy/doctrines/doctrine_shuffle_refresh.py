"""Shuffle-refresh probability helpers; Issue #459 retires its shared valuation rungs."""
from __future__ import annotations

from math import comb

from common.strategy.context import _ATTACK, _END, _MAIN, _PLAY
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
        k = sum(n for c2, n in counts.items()
                if n > 0 and self._grab_value_of(board, c2, plan, obs=obs) > 0)
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

    def _refresh_sequence_override(self, obs: dict, select: dict, options: list, traces: list,
                                   composed_index: int):
        """Reject a cost-negative refresh whose only continuation already exists at the root.

        A shuffle is a reveal boundary: the composer may value its unknown post-draw hand while
        carrying the same root attack as continuation.  The live refresh oracle already prices the
        known hand lost and expected draw.  When that net is non-positive, the refresh is pure cost;
        take the available terminal action (or End) instead.
        """
        if ((select or {}).get("context") != _MAIN
                or not (0 <= composed_index < len(options))):
            return None
        option, trace = options[composed_index], traces[composed_index]
        cid = getattr(trace, "card_id", None)
        tags = set(self.functions.tags(cid)) if (self.functions and cid is not None) else set()
        if (option.get("type") != _PLAY or "shuffle_hand" not in tags
                or float(getattr(trace, "score", 0.0) or 0.0) > 0.0):
            return None
        attacks = [i for i, candidate in enumerate(options)
                   if candidate.get("type") == _ATTACK
                   and float(getattr(traces[i], "tactical", 0.0) or 0.0) > 0.0]
        if attacks:
            winner = max(attacks, key=lambda i: (traces[i].tactical, traces[i].score, -i))
        else:
            winner = next((i for i, candidate in enumerate(options)
                           if candidate.get("type") == _END), None)
        if winner is None or winner == composed_index:
            return None
        return winner, "cost-benefit: decline non-positive refresh; take the existing turn ender"


# Target-runtime shuffle valuations are composer-owned (Issue #459).
HYPOTHESES = []
