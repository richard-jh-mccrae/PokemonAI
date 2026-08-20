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


def test_seat_one_viewer_maps_sides_and_deck_counts():
    mine = player(active=body(66, 21), hand=[119], discard=[120])
    theirs = player(own=False, hand_count=5)
    obs = printout(me=theirs, them=mine)
    obs["current"]["yourIndex"] = 1
    board = BoardState.root(obs, decklist=(66,) * 2 + (119,) * 2 + (120,) * 2)
    assert board.seat == 1
    assert board.me.active.card.card_id == 66 and board.me.hand.count(119) == 1
    assert board.them.hand is None and board.them.hand_count == 5
    assert board.deck_counts == ((66, 1), (119, 1), (120, 1))


def test_stadium_ownership_gates_the_deck_deduction():
    deck = (1252, 1252)
    theirs = printout(stadium=[{"id": 1252, "serial": 60, "playerIndex": 1}])
    assert BoardState.root(theirs, decklist=deck).deck_counts == ((1252, 2),)
    mine = printout(stadium=[{"id": 1252, "serial": 60, "playerIndex": 0}])
    assert BoardState.root(mine, decklist=deck).deck_counts == ((1252, 1),)
    unstamped = printout(stadium=[{"id": 1252, "serial": 60}])   # no owner: counts as mine
    assert BoardState.root(unstamped, decklist=deck).deck_counts == ((1252, 1),)


def test_body_riders_pin_facts_and_reach_the_key():
    base = printout(me=player(active=body(66, 1, energy_cards=(3,), tools=(1174,), pre=(305,))))
    board = BoardState.root(base)
    active = board.me.active
    assert [card.card_id for card in active.energy_cards] == [3]
    assert active.tools[0].facts is card_store()[1174]
    assert active.pre_evolution[0].card_id == 305
    import copy
    untooled = copy.deepcopy(base)
    untooled["current"]["players"][0]["active"][0]["tools"] = []
    assert BoardState.root(untooled).key != board.key


def test_root_degrades_on_an_empty_or_truncated_printout():
    empty = BoardState.root({})
    assert empty.me.active is None and empty.me.hand is None
    assert len(empty.them.discard) == 0 and isinstance(empty.key, str)
    solo = BoardState.root({"current": {"yourIndex": 0, "players": [player()]}})
    assert solo.me.hand is not None and solo.them.hand_count == 0


def test_looking_carries_visible_cards_and_hides_hidden_ones():
    seen = printout()
    seen["current"]["looking"] = [{"id": KNOWN, "serial": 30}, {"id": 112, "serial": 31}]
    hidden = printout()
    hidden["current"]["looking"] = [None, None]
    a, b = BoardState.root(seen), BoardState.root(hidden)
    assert a.looking.count == 2 and [c.card_id for c in a.looking.cards] == [KNOWN, 112]
    assert b.looking.count == 2 and b.looking.cards is None
    assert a.key != b.key


def test_deck_counts_match_decision_state():
    from common.state import DecisionState
    deck = (KNOWN,) * 3 + (112,) * 2 + (119,) * 4 + (120,) * 2
    obs = printout(me=player(active=body(KNOWN, 1, energy_cards=(120,)), bench=[body(112, 2)],
                             hand=[119], discard=[119]),
                   own_prizes={KNOWN: 1})
    board = BoardState.root(obs, decklist=deck)
    state = DecisionState.from_observation(obs, deck=deck, deck_name="probe")
    assert board.deck_counts == state.deck_counts
