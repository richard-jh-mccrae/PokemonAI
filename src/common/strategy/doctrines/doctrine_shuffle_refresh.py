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
from common.strategy.strategy import Hypothesis

# DRAW-COUNT facts, id-keyed, verified at data/EN_Card_Data.csv 2026-07-03 (ADR-0024 amendment).
# Each entry -> the coin/condition BRANCHES of "how many I draw" (P averaged exactly over branches).
# A shuffle_hand card absent here gets NO probabilistic claim (fail-silent; the sound veto still covers).
_DRAW_COUNTS = {
    1227: lambda b: (8,) if b.my_prizes_remaining == 6 else (6,),        # Lillie's Determination
    1199: lambda b: (8,) if 0 < b.opp_prizes_remaining <= 3 else (4,),   # Lacey
    1213: lambda b: (4,),                                                # Judge
    1223: lambda b: (3, 5),                                              # Harlequin (coin)
}

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
        (`deck_known_counts`) and a verified draw-count (`_DRAW_COUNTS`); silent otherwise."""
        if option.get("type") != _PLAY or "shuffle_hand" not in tags:
            return False
        counts = board.deck_known_counts
        branches = _DRAW_COUNTS.get(cid)
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

        ns = branches(board)
        return sum(p_hit(n) for n in ns) / len(ns) < _MISS_PROB_THRESHOLD

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
    Hypothesis(
        id="hold-wincon-dont-shuffle",
        rationale="Don't shuffle a usable win-condition (a Line payoff) out of hand with a `shuffle_hand` "
                  "Supporter — refilling sends it back into the deck, costing the turn to deploy it, so "
                  "hold it and dig another way. Moderate (nets negative against `dig-before-commit` but "
                  "not absolute, so a genuinely dead hand still refills); stands down when the "
                  "win-condition is already in PLAY (`wincon_in_play`) — a redundant hand duplicate is "
                  "safe to shuffle (the ep82226759 Harlequin shape: Mega Starmie ex Active, second copy in "
                  "hand).",
        when=lambda c: c.option_type == _PLAY and "shuffle_hand" in c.tags
        and c.board.wincon_in_hand and not c.board.wincon_in_play,
        weight=-25, status="assumed"),
    Hypothesis(
        id="hold-line-piece-dont-shuffle",
        rationale="Don't shuffle away a hand holding a win-condition LINE piece you just dug for — a base "
                  "or mid-Line pre-evolution (`line_preevo_in_hand`, e.g. a fetched Drakloak) — with a "
                  "`shuffle_hand` refresh: refilling sends it back into the deck, wasting the dig "
                  "(ep83686860 f13: Ultra Ball'd 2 Energy for a Drakloak, then Lillie's shuffled it away "
                  "for zero gain). The LINE-piece mirror of `hold-wincon-dont-shuffle` (the payoff case); "
                  "−25 nets below `dig-before-commit` (+20). Stands down once the win-condition is IN PLAY "
                  "(a redundant hand duplicate is safe to cycle).",
        when=lambda c: c.option_type == _PLAY and "shuffle_hand" in c.tags
        and c.board.line_preevo_in_hand and not c.board.wincon_in_play,
        weight=-25, status="assumed"),
    Hypothesis(
        id="hold-wincon-with-base-dont-shuffle",
        rationale="Strengthen `hold-wincon-dont-shuffle` when the win-condition's base is ALREADY IN PLAY "
                  "to evolve onto next turn (`line_preevo_in_play`, e.g. benched Staryu under a Mega "
                  "Starmie ex in hand) — this is a concrete imminent evolution, not just recoverable "
                  "tempo, so hold firmly and develop instead. Stacks on the base hold (−25) to net the "
                  "shuffle below 0 even against `dig-before-commit` (+20), tiering it below the attack "
                  "(ep82867148 f52: 3 Mega in hand, benched Staryu, Turbo Flare available); narrow to "
                  "base-in-play, else the moderate hold still allows a dead-hand refill.",
        when=lambda c: c.option_type == _PLAY and "shuffle_hand" in c.tags
        and c.board.wincon_in_hand and c.board.line_preevo_in_play and not c.board.wincon_in_play,
        weight=-15, status="testing"),
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
    Hypothesis(
        id="hold-successor-when-doomed",
        rationale="Don't shuffle away the hand when the Active win-condition is DOOMED and the hand holds "
                  "the rebuild successor (`wincon_in_hand` PLUS `line_preevo_in_play`) — the case the "
                  "other holds miss, since they stand down once the win-condition is in PLAY, but an "
                  "about-to-be-KO'd in-play copy makes the hand copy the NEXT attacker, not a redundant "
                  "duplicate: hold the successor and develop instead (ep83037962 f49 — Harlequin "
                  "gambling away a benchable Mega Starmie ex + two Water). Weighted (−35) to net below "
                  "0 against `dig-before-commit` (+20); narrow, so a healthy board still cycles freely.",
        when=lambda c: c.option_type == _PLAY and "shuffle_hand" in c.tags
        and c.board.active_doomed and c.board.wincon_in_hand and c.board.line_preevo_in_play,
        weight=-35, status="testing"),
]
