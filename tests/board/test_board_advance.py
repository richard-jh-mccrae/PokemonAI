"""Advance: untouched pieces survive as the same objects, and the result equals a fresh build."""
from __future__ import annotations

import copy

from test_board_nodes import body, player, printout

from common.board import BoardState

DECK = (66,) * 3 + (112,) * 2 + (119,) * 4 + (120,) * 2


def _base():
    return printout(
        me=player(active=body(66, 1), bench=[body(112, 2), body(119, 3)], hand=[119, 120],
                  discard=[119]),
        them=player(own=False, active=body(121, 11), bench=[body(140, 12)]))


def test_untouched_pieces_are_the_parent_objects():
    root = BoardState.root(_base(), decklist=DECK)
    successor = copy.deepcopy(_base())
    successor["current"]["players"][0]["bench"][1]["hp"] = 40
    child = root.advance(successor)
    assert child.them is root.them
    assert child.me.hand is root.me.hand and child.me.discard is root.me.discard
    assert child.me.active is root.me.active
    assert child.me.bench[0] is root.me.bench[0]
    assert child.me.bench[1] is not root.me.bench[1] and child.me.bench[1].hp == 40
    assert child.changed == {("me", "bench")}


def test_advance_equals_a_fresh_root_build():
    root = BoardState.root(_base(), decklist=DECK)
    successor = copy.deepcopy(_base())
    successor["current"]["players"][0]["hand"] = successor["current"]["players"][0]["hand"][1:]
    successor["current"]["players"][0]["handCount"] = 1
    successor["current"]["supporterPlayed"] = True
    child = root.advance(successor)
    fresh = BoardState.root(successor, decklist=DECK)
    assert child == fresh
    assert child.key == fresh.key
    assert {("me", "hand"), ("me", "scalars"), ("turn",)} <= child.changed


def test_deck_counts_reused_when_no_own_piece_changed():
    root = BoardState.root(_base(), decklist=DECK)
    successor = copy.deepcopy(_base())
    successor["current"]["players"][1]["active"][0]["hp"] = 10
    child = root.advance(successor)
    assert child.deck_counts is root.deck_counts
    assert child.changed == {("them", "active")}


def test_deck_counts_recompute_when_my_hand_changed():
    root = BoardState.root(_base(), decklist=DECK)
    successor = copy.deepcopy(_base())
    successor["current"]["players"][0]["hand"].append(
        {"id": 66, "serial": 850, "playerIndex": 0})
    child = root.advance(successor)
    assert child.deck_counts != root.deck_counts
    assert child.me.hand.count(66) == 1
