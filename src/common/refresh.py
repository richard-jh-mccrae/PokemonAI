"""Describe a shuffle-refresh as printed counts; valuation lives with each brain."""
from __future__ import annotations

from .observation.provider import provider_payload as _payload

from .algebra import Refresh
from .cards import card_store, play_clauses
from .cards.functions.draw import draw_branches, draw_shape_problem


SHUFFLE_OWN_HAND_RIDER = "shuffle_own_hand_in"
SHUFFLE_BOTH_HANDS_RIDER = "shuffle_both_hands"
SHUFFLE_RIDERS = frozenset({SHUFFLE_OWN_HAND_RIDER, SHUFFLE_BOTH_HANDS_RIDER})


def played_card_id(state, action) -> int | None:
    """Resolve a MAIN play through the public hand/menu, without engine-private state."""
    if action.identity.kind != "play" or len(action.selection) != 1:
        return None
    observation = _payload(state)
    options = ((observation.get("select") or {}).get("option") or ())
    option_index = action.selection[0]
    if not 0 <= option_index < len(options):
        return None
    option = options[option_index]
    hand_index = option.get("index")
    current = observation.get("current") or {}
    option_seat = option.get("playerIndex")
    seat = state.root_seat if option_seat is None else int(option_seat)
    players = current.get("players") or ()
    player = players[seat] if 0 <= seat < len(players) and players[seat] else {}
    hand = player.get("hand") or ()
    if not isinstance(hand_index, int) or not 0 <= hand_index < len(hand) or not hand[hand_index]:
        return None
    return int(hand[hand_index]["id"])


def refresh_transition(state, action, cards=None) -> Refresh | None:
    """Describe a generic shuffle-refresh as printed counts, with no sampled successor."""
    card_id = played_card_id(state, action)
    cards = card_store() if cards is None else cards
    clauses = play_clauses(cards.get(int(card_id))) if card_id is not None else ()
    candidates = tuple(clause for clause in clauses
                       if clause.kind == "draw" and clause.rider in SHUFFLE_RIDERS)
    if len(candidates) != 1 or draw_shape_problem(candidates[0]) is not None:
        return None
    current = _payload(state).get("current") or {}
    players = current.get("players") or ()
    mine = players[state.root_seat] if len(players) > state.root_seat else {}
    opponent = players[1 - state.root_seat] if len(players) > 1 else {}
    branches = draw_branches(
        candidates[0], len(mine.get("prize") or ()), len(opponent.get("prize") or ()),
        my_hand_size=len(mine.get("hand") or ()),
        cards_leaving_hand=1,
    )
    if not branches:
        return None
    return Refresh(card_id, branches,
                   candidates[0].rider == SHUFFLE_BOTH_HANDS_RIDER)


__all__ = ("SHUFFLE_BOTH_HANDS_RIDER", "SHUFFLE_OWN_HAND_RIDER", "SHUFFLE_RIDERS",
           "played_card_id", "refresh_transition")
