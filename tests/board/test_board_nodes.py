"""Construction: sides, masking-by-type, fact pinning, and both select dialects."""
from __future__ import annotations

from observation_helpers import engine_opt, opt

from common.board import BoardState
from common.cards import card_store

KNOWN, UNKNOWN = 66, 999_999


def body(card_id, serial, *, hp=100, max_hp=100, energies=(), energy_cards=(), tools=(), pre=()):
    return {"id": card_id, "serial": serial, "playerIndex": 0, "hp": hp, "maxHp": max_hp,
            "appearThisTurn": False, "energies": list(energies),
            "energyCards": [{"id": c, "serial": 700 + i} for i, c in enumerate(energy_cards)],
            "tools": [{"id": c, "serial": 750 + i} for i, c in enumerate(tools)],
            "preEvolution": [{"id": c, "serial": 770 + i} for i, c in enumerate(pre)]}


def player(*, active=None, bench=(), hand=(), discard=(), deck_count=10, prizes=3, own=True,
           hand_count=None):
    cards = [{"id": c, "serial": 800 + i, "playerIndex": 0} for i, c in enumerate(hand)]
    return {"active": [active] if active else [], "bench": list(bench), "benchMax": 5,
            "deckCount": deck_count, "prize": [None] * prizes,
            "discard": [{"id": c, "serial": 900 + i, "playerIndex": 0}
                        for i, c in enumerate(discard)],
            "handCount": len(hand) if hand_count is None else hand_count,
            "hand": cards if own else None, "poisoned": False, "burned": False,
            "asleep": False, "paralyzed": False, "confused": False}


def printout(*, me=None, them=None, turn=2, select=None, stadium=(), **top):
    current = {"turn": turn, "yourIndex": 0, "firstPlayer": 0, "supporterPlayed": False,
               "stadiumPlayed": False, "energyAttached": False, "retreated": False,
               "result": None, "stadium": list(stadium), "looking": None,
               "players": [me if me is not None else player(),
                           them if them is not None else player(own=False)]}
    return {"select": select, "logs": [], "current": current, **top}


def test_root_maps_both_sides_and_the_turn():
    board = BoardState.root(printout(
        me=player(active=body(KNOWN, 1), bench=[body(112, 2)], hand=[119, 119], discard=[120]),
        them=player(own=False, hand_count=4, prizes=2)))
    assert board.me.active.card.card_id == KNOWN and not board.me.active_hidden
    assert [b.card.card_id for b in board.me.bench] == [112]
    assert board.me.hand.count(119) == 2 and len(board.me.discard) == 1
    assert board.them.hand is None and board.them.hand_count == 4
    assert board.them.prize_count == 2
    assert board.turn.number == 2 and not board.turn.supporter_played


def test_facedown_active_is_hidden_even_to_its_owner():
    me = player()
    me["active"] = [None]
    board = BoardState.root(printout(me=me))
    assert board.me.active is None and board.me.active_hidden


def test_card_facts_pin_from_the_store_and_unknown_ids_degrade():
    board = BoardState.root(printout(me=player(active=body(KNOWN, 1), hand=[UNKNOWN])))
    assert board.me.active.card.facts is card_store()[KNOWN]
    assert board.me.hand.cards[0].facts is None


def test_opponent_hand_and_prize_contents_are_unrepresentable():
    """A full-truth frame's hidden zones must die at construction, not depend on the caller."""
    them = player(own=False)
    them["hand"] = [{"id": KNOWN, "serial": 5, "playerIndex": 1}]
    them["prize"] = [{"id": 112, "serial": 6, "playerIndex": 1}, None]
    board = BoardState.root(printout(them=them))
    assert board.them.hand is None
    assert board.them.prize_count == 2


def test_select_normalizes_both_engine_dialects():
    sparse = printout(select={"type": 1, "context": 0, "minCount": 1, "maxCount": 1,
                              "remainDamageCounter": 0, "remainEnergyCost": 0,
                              "option": [opt(7, index=2)], "deck": None,
                              "contextCard": None, "effect": None})
    padded = printout(select={"type": 1, "context": 0, "minCount": 1, "maxCount": 1,
                              "remainDamageCounter": 0, "remainEnergyCost": 0,
                              "option": [engine_opt(7, index=2)], "deck": None,
                              "contextCard": None, "effect": None})
    a, b = BoardState.root(sparse), BoardState.root(padded)
    assert a.select.options == b.select.options
    assert a.select.options[0].index == 2 and a.select.options[0].area is None


def test_deck_counts_match_decision_state():
    from common.state import DecisionState
    deck = (KNOWN,) * 3 + (112,) * 2 + (119,) * 4 + (120,) * 2
    obs = printout(me=player(active=body(KNOWN, 1, energy_cards=(120,)), bench=[body(112, 2)],
                             hand=[119], discard=[119]),
                   own_prizes={KNOWN: 1})
    board = BoardState.root(obs, decklist=deck)
    state = DecisionState.from_observation(obs, deck=deck, deck_name="probe")
    assert board.deck_counts == state.deck_counts
