"""ORACLE: Hand-refresh swing — ADR-0060. The closed-form value of a shuffle-refresh.

Judge / Harlequin / Unfair Stamp are symmetric REFILLS, not strips: both players shuffle and redraw,
so the whole value is one quantity, the net card swing
``(my_draw - my_hand) - (opp_draw - opp_hand)``. The card's own draw number IS the break-even, which
is why the retired hand-size thresholds matched no card.

Sign convention: a POSITIVE `opp_hand_size_delta` means they GREW their hand, i.e. it is FRESH.
"""
from __future__ import annotations

# DRAW-COUNT facts, verified at data/EN_Card_Data.csv:
#   {id: (opp_shuffles, branches(my_prizes, opp_prizes) -> ((my_draw, opp_draw), ...))}, coin-equal.
_REFRESH = {
    # "Each player shuffles their hand into their deck and draws 4 cards."
    1213: (True, lambda mp, op: ((4, 4),)),                                     # Judge
    # "...flip a coin. If heads, you draw 5 cards, and your opponent draws 3 cards.
    #  If tails, you draw 3 cards, and your opponent draws 5 cards."
    1223: (True, lambda mp, op: ((5, 3), (3, 5))),                              # Harlequin
    # "...you draw 5 cards, and your opponent draws 2 cards."  (ACE SPEC Item; the engine gates its
    # play-legality on a KO against us last turn, so we never need to test that here.)
    1080: (True, lambda mp, op: ((5, 2),)),                                     # Unfair Stamp
    # "Shuffle your hand into your deck. Then, draw 6 cards. If you have exactly 6 Prize cards
    #  remaining, draw 8 cards instead."
    1227: (False, lambda mp, op: (((8, 0),) if mp == 6 else ((6, 0),))),        # Lillie's Determination
    # "Shuffle your hand into your deck. Then, draw 4 cards. If your opponent has 3 or fewer Prize
    #  cards remaining, draw 8 cards instead."
    1199: (False, lambda mp, op: (((8, 0),) if 0 < op <= 3 else ((4, 0),))),    # Lacey
}


def refresh_branches(card_id, my_prizes_remaining: int, opp_prizes_remaining: int):
    """The card's equally-likely ``((my_draw, opp_draw), ...)`` branches on this board, or ``None``
    when the card is not a known shuffle-refresh (fail-silent: an unknown card makes no claim)."""
    rec = _REFRESH.get(card_id)
    if rec is None:
        return None
    return rec[1](my_prizes_remaining, opp_prizes_remaining)


def opponent_shuffles(card_id) -> bool:
    """True when the card shuffles the OPPONENT's hand away too (Judge/Harlequin/Unfair Stamp) —
    the discriminator between a symmetric refill and a self-only refresh (Lillie's/Lacey)."""
    rec = _REFRESH.get(card_id)
    return bool(rec and rec[0])


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
