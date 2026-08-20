"""The key: semantic identity ignores serials, owners, render order, and menu material."""
from __future__ import annotations

import copy

from test_board_nodes import body, player, printout

from common.board import BoardState


def _board(obs):
    return BoardState.root(obs)


def test_hand_order_and_serials_never_reach_the_key():
    base = printout(me=player(hand=[119, 120, 119]))
    permuted = copy.deepcopy(base)
    hand = permuted["current"]["players"][0]["hand"]
    hand.reverse()
    for i, card in enumerate(hand):
        card["serial"] = 1000 + i
    assert _board(base).key == _board(permuted).key


def test_bench_order_never_reaches_the_key():
    a = printout(me=player(bench=[body(112, 2), body(119, 3)]))
    b = printout(me=player(bench=[body(119, 3), body(112, 2)]))
    assert _board(a).key == _board(b).key


def test_damage_and_attack_locks_change_the_key():
    base = printout(me=player(active=body(66, 1)))
    damaged = copy.deepcopy(base)
    damaged["current"]["players"][0]["active"][0]["hp"] = 10
    locked = copy.deepcopy(base)
    locked["attack_locks"] = {"1": {"9001": 4}}
    keys = {_board(base).key, _board(damaged).key, _board(locked).key}
    assert len(keys) == 3


def test_deck_knowledge_reaches_the_key():
    obs = printout(me=player(hand=[119]))
    bare = BoardState.root(obs)
    deck_a = BoardState.root(obs, decklist=(119,) * 4 + (120,) * 2)
    deck_b = BoardState.root(obs, decklist=(119,) * 4 + (121,) * 2)
    assert len({bare.key, deck_a.key, deck_b.key}) == 3


def test_select_deck_listing_is_menu_material_but_the_context_card_is_not():
    base = printout(select={"type": 1, "context": 0, "minCount": 1, "maxCount": 1,
                            "remainDamageCounter": 0, "remainEnergyCost": 0,
                            "option": [{"type": 7, "index": 0}], "deck": None,
                            "contextCard": None, "effect": None})
    with_deck = copy.deepcopy(base)
    with_deck["select"]["deck"] = [{"id": 119, "serial": 40}]
    assert _board(base).key == _board(with_deck).key
    with_context = copy.deepcopy(base)
    with_context["select"]["contextCard"] = {"id": 1121, "serial": 41}
    assert _board(base).key != _board(with_context).key


def test_known_top_reaches_the_key_and_string_prize_keys_coerce():
    base = printout(me=player(hand=[119]))
    stacked = copy.deepcopy(base)
    stacked["known_top"] = [[41, 66]]
    assert _board(base).key != _board(stacked).key
    stringy = copy.deepcopy(base)
    stringy["own_prizes"] = {"66": 2}                      # JSON round trips keys to strings
    board = BoardState.root(stringy, decklist=(66,) * 3 + (119,))
    assert board.own_prizes == ((66, 2),)
    assert board.deck_counts == ((66, 1),)


def test_select_menu_material_never_reaches_the_key():
    a = printout(select={"type": 1, "context": 0, "minCount": 1, "maxCount": 1,
                         "remainDamageCounter": 0, "remainEnergyCost": 0,
                         "option": [{"type": 7, "index": 0}], "deck": None,
                         "contextCard": None, "effect": None})
    b = copy.deepcopy(a)
    b["select"]["option"] = [{"type": 7, "index": 0}, {"type": 7, "index": 1}]
    assert _board(a).key == _board(b).key
