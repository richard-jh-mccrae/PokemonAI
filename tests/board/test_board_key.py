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


def test_select_menu_material_never_reaches_the_key():
    a = printout(select={"type": 1, "context": 0, "minCount": 1, "maxCount": 1,
                         "remainDamageCounter": 0, "remainEnergyCost": 0,
                         "option": [{"type": 7, "index": 0}], "deck": None,
                         "contextCard": None, "effect": None})
    b = copy.deepcopy(a)
    b["select"]["option"] = [{"type": 7, "index": 0}, {"type": 7, "index": 1}]
    assert _board(a).key == _board(b).key
