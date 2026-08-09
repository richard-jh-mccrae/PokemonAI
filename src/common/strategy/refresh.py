"""ORACLE: clause-driven hand-refresh swing — ADR-0060, Issue #468.

Judge / Harlequin / Unfair Stamp are symmetric REFILLS, not strips: both players shuffle and redraw,
so the whole value is one quantity, the net card swing
``(my_draw - my_hand) - (opp_draw - opp_hand)``. The card's own draw number IS the break-even, which
is why the retired hand-size thresholds matched no card.

Sign convention: a POSITIVE `opp_hand_size_delta` means they GREW their hand, i.e. it is FRESH.
"""
from __future__ import annotations

from collections.abc import Mapping

from common.effects import CardEffects


_EFFECTS = CardEffects.load()
_RIDERS = frozenset({"shuffle_own_hand_in", "shuffle_both_hands"})
_AMOUNT_CONDITIONS = frozenset({
    "coin_tails", "exactly_6_prizes_remaining", "opp_3_or_fewer_prizes",
    "hand_size_10_plus_after_draw",
})


def _positive_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def draw_shape_problem(clause: Mapping) -> str | None:
    """Why a scalar draw clause is unsupported, or ``None`` when its shape is decidable."""
    if clause.get("kind") != "draw":
        return "kind is not `draw`"
    if not _positive_int(clause.get("amount")):
        return "`amount` must be a positive integer"
    if clause.get("rider") not in (None, *_RIDERS):
        return f"rider {clause.get('rider')!r} is not a supported scalar draw rider"
    if clause.get("condition") not in (None, "pokemon_ko_last_turn"):
        return f"condition {clause.get('condition')!r} has no scalar draw reader"
    own_if = clause.get("amount_if")
    opp_if = clause.get("opponent_amount_if")
    for label, branch in (("amount_if", own_if), ("opponent_amount_if", opp_if)):
        if branch is None:
            continue
        if not isinstance(branch, Mapping):
            return f"`{label}` must be a condition map"
        if branch.get("condition") not in _AMOUNT_CONDITIONS:
            return f"`{label}` condition {branch.get('condition')!r} has no scalar draw reader"
        if set(branch) != {"condition", "amount"} or not _positive_int(branch.get("amount")):
            return f"`{label}` must contain one condition and one positive integer amount"
    opponent = clause.get("opponent_amount")
    if opponent is not None and not _positive_int(opponent):
        return "`opponent_amount` must be a positive integer"
    if opp_if is not None and opponent is None:
        return "`opponent_amount_if` requires `opponent_amount`"
    if opp_if is not None and own_if is None:
        return "`opponent_amount_if` requires `amount_if` for the shared branch"
    if own_if is not None and opp_if is not None and own_if["condition"] != opp_if["condition"]:
        return "own and opponent conditional amounts must use the same condition"
    both = clause.get("rider") == "shuffle_both_hands"
    if both != (opponent is not None):
        return "`shuffle_both_hands` and an explicit opponent amount must occur together"
    return None


def _condition_holds(condition: str, my_prizes: int, opp_prizes: int, *,
                     my_hand_size: int | None = None, base_amount: int = 0) -> bool:
    if condition == "exactly_6_prizes_remaining":
        return my_prizes == 6
    if condition == "opp_3_or_fewer_prizes":
        return 0 < opp_prizes <= 3
    if condition == "hand_size_10_plus_after_draw":
        # The Supporter itself leaves the hand before the printed base draw resolves.
        return my_hand_size is not None and max(0, my_hand_size - 1) + base_amount >= 10
    return False


def draw_branches(clause: Mapping, my_prizes_remaining: int,
                  opp_prizes_remaining: int, *,
                  my_hand_size: int | None = None) -> tuple[tuple[int, int], ...] | None:
    """Equally likely ``(mine, theirs)`` draw counts from one supported clause."""
    if draw_shape_problem(clause) is not None:
        return None
    base = (int(clause["amount"]), int(clause.get("opponent_amount") or 0))
    own_if = clause.get("amount_if")
    opp_if = clause.get("opponent_amount_if")
    condition = ((own_if or opp_if) or {}).get("condition")
    if condition is None:
        return (base,)
    alternate = (int((own_if or {}).get("amount", base[0])),
                 int((opp_if or {}).get("amount", base[1])))
    if condition == "coin_tails":
        return (base, alternate)
    return (alternate,) if _condition_holds(
        condition, my_prizes_remaining, opp_prizes_remaining,
        my_hand_size=my_hand_size, base_amount=base[0]) else (base,)


def _refresh_clause(card_id: int) -> Mapping | None:
    if card_id is None:
        return None
    clauses = _EFFECTS.clauses(card_id)
    if _EFFECTS.clauses_cover(card_id) is not True or len(clauses) != 1:
        return None
    clause = clauses[0]
    return clause if clause.get("rider") in _RIDERS and draw_shape_problem(clause) is None else None


def refresh_branches(card_id, my_prizes_remaining: int, opp_prizes_remaining: int):
    """The card's equally-likely ``((my_draw, opp_draw), ...)`` branches on this board, or ``None``
    when the card is not a known shuffle-refresh (fail-silent: an unknown card makes no claim)."""
    clause = _refresh_clause(card_id)
    if clause is None:
        return None
    return draw_branches(clause, my_prizes_remaining, opp_prizes_remaining)


def opponent_shuffles(card_id) -> bool:
    """True when the card shuffles the OPPONENT's hand away too (Judge/Harlequin/Unfair Stamp) —
    the discriminator between a symmetric refill and a self-only refresh (Lillie's/Lacey)."""
    clause = _refresh_clause(card_id)
    return bool(clause and clause.get("rider") == "shuffle_both_hands")


def hand_swing(card_id, my_hand: int, opp_hand: int,
               my_prizes_remaining: int, opp_prizes_remaining: int) -> float | None:
    """Net card swing of playing this refresh, in CARDS, averaged over its coin branches.
    ``None`` when the card is not a known shuffle-refresh."""
    branches = refresh_branches(card_id, my_prizes_remaining, opp_prizes_remaining)
    if branches is None:
        return None
    opp_shuffles = opponent_shuffles(card_id)
    total = 0.0
    for my_draw, opp_draw in branches:
        opp_net = (opp_draw - opp_hand) if opp_shuffles else 0
        total += (my_draw - my_hand) - opp_net
    return total / len(branches)


def net_change(card_id, my_hand: int, opp_hand: int,
               my_prizes_remaining: int, opp_prizes_remaining: int):
    """``(my_net, opp_net)`` — each side's expected change in hand size; None for an unknown card.
    The scorer prices the halves separately: a card I SHED is curated, a card I DRAW is unseen."""
    branches = refresh_branches(card_id, my_prizes_remaining, opp_prizes_remaining)
    if branches is None:
        return None
    opp_shuffles = opponent_shuffles(card_id)
    mine = sum(my_draw - my_hand for my_draw, _o in branches) / len(branches)
    theirs = (sum(opp_draw - opp_hand for _m, opp_draw in branches) / len(branches)
              if opp_shuffles else 0.0)
    return mine, theirs


def own_draw_count(card_id, my_prizes_remaining: int, opp_prizes_remaining: int) -> float | None:
    """The card's OWN redraw count averaged over its coin branches, or None. The grab-time ceiling:
    `hand_swing` needs PLAY-time hand sizes, which a TO_HAND grab does not have."""
    branches = refresh_branches(card_id, my_prizes_remaining, opp_prizes_remaining)
    if branches is None:
        return None
    return sum(my_draw for my_draw, _o in branches) / len(branches)


def refills_opponent(card_id, opp_hand: int,
                     my_prizes_remaining: int, opp_prizes_remaining: int) -> bool:
    """Playing this refresh GROWS the opponent's hand (``opp_net > 0``). The sign gate for the favored
    tax, so it never fires on a STRIP of a stacked hand. False for a self-only or unknown card."""
    branches = refresh_branches(card_id, my_prizes_remaining, opp_prizes_remaining)
    if branches is None or not opponent_shuffles(card_id):
        return False
    opp_net = sum(opp_draw - opp_hand for _m, opp_draw in branches) / len(branches)
    return opp_net > 0


def fresh_cards(card_id, opp_hand: int, opp_hand_size_delta: int | None) -> int:
    """How many of the cards we are about to strip arrived in the opponent's hand LAST TURN.
    0 for a self-only refresh (we strip nothing) and 0 until a prior turn is known."""
    if not opponent_shuffles(card_id) or not opp_hand_size_delta:
        return 0
    return max(0, min(opp_hand_size_delta, opp_hand))
