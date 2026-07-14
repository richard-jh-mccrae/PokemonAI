"""ORACLE: Hand-refresh swing — ADR-0060. The closed-form value of a shuffle-refresh.

Judge and Harlequin are **symmetric REFILLS, not strips**: each player shuffles their hand into
their deck and redraws, so both land on the card's draw count. The entire value of playing one is
therefore a single quantity — the net card swing:

    swing = my_net - opp_net,   my_net  = my_draw  - my_hand
                                opp_net = opp_draw - opp_hand   (0 when they don't shuffle)

- Judge (4/4)          -> swing = opp_hand - my_hand
- Harlequin (EV 4/4)   -> the same EV as Judge, plus a +/-2 coin variance (branches kept paired for
                          a later ADR-0039 gamble pass; ranked at EV today)
- Unfair Stamp (5/2)   -> swing = opp_hand - my_hand + 3   (and it is an ITEM, not a Supporter)
- Lillie's (6 self)    -> swing = 6 - my_hand   (8 at exactly six prizes)

The card's own draw number IS the break-even. That is why the pre-ADR-0060 thresholds
(`_STACKED_HAND` 6, `_REFRESH_HAND_FLOOR` 5, `_TAILORED_HAND` 3) matched no card: they were
hand-fitted constants standing in for a number the card already prints.

FRESHNESS. The count model cannot tell a FRESH big hand from a STALE one. `fresh_cards` counts how
many of the opponent's current cards arrived last turn (`opp_hand_size_delta`): stripping eight
cards they just drew denies live resources; stripping eight they have been stuck holding for three
turns denies cards they demonstrably cannot play. It only applies when we are actually stripping
them (a positive swing on a card that shuffles their hand).

This settles the sign convention that `opponent_resources.py` and `pilot.py` used to contradict each
other on: **a POSITIVE delta means they GREW their hand, i.e. it is fresh.**
"""
from __future__ import annotations

# DRAW-COUNT facts, id-keyed, verified at data/EN_Card_Data.csv. Each entry:
#   (opp_shuffles, branches(my_prizes_remaining, opp_prizes_remaining) -> ((my_draw, opp_draw), ...))
# Branches are EQUALLY LIKELY (a coin); a single branch is deterministic. `opp_shuffles=False` means
# the opponent's hand is untouched, so their net change is 0 -- NOT `0 - opp_hand`.
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
    """``(my_net, opp_net)`` — each side's expected change in hand size. ``None`` for an unknown card.

    The two halves are NOT worth the same per card, which is why the scorer prices them separately
    rather than collapsing them into `hand_swing`:

    - a card I SHED is one I chose to hold — known, curated, certain value walking away;
    - a card I DRAW is unseen — speculative, and only as good as what the deck can still supply
      (which is what the `hold-*-dont-shuffle` / `dont-refresh-into-a-probable-miss` guards
      adjudicate). Crediting it per-card would swamp exactly those guards.

    `hand_swing` (my_net - opp_net) remains the honest CARD-COUNT statement and is what the card
    facts are checked against; the scorer's asymmetry is a value judgement layered on top of it.
    """
    branches = refresh_branches(card_id, my_prizes_remaining, opp_prizes_remaining)
    if branches is None:
        return None
    opp_shuffles = opponent_shuffles(card_id)
    mine = sum(my_draw - my_hand for my_draw, _o in branches) / len(branches)
    theirs = (sum(opp_draw - opp_hand for _m, opp_draw in branches) / len(branches)
              if opp_shuffles else 0.0)
    return mine, theirs


def fresh_cards(card_id, opp_hand: int, opp_hand_size_delta: int | None) -> int:
    """How many of the cards we are about to strip arrived in the opponent's hand LAST TURN.
    0 for a self-only refresh (we strip nothing) and 0 until a prior turn is known."""
    if not opponent_shuffles(card_id) or not opp_hand_size_delta:
        return 0
    return max(0, min(opp_hand_size_delta, opp_hand))
