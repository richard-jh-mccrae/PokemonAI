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


def test_advance_folds_a_self_lock_out_of_the_logs():
    root = BoardState.root(_base(), decklist=DECK)
    successor = copy.deepcopy(_base())
    successor["logs"] = [{"type": 15, "serial": 1, "attackId": 983}]   # Mega Brave, self-locking
    child = root.advance(successor)
    assert child.attack_locks == (("1", (("983", 4),)),)               # barred on my next turn
    assert ("extras",) in child.changed
    assert child == BoardState.root(successor, decklist=DECK)


def test_a_parent_ledger_survives_quiet_logs():
    successor = copy.deepcopy(_base())
    successor["logs"] = [{"type": 15, "serial": 1, "attackId": 983}]
    child = BoardState.root(_base(), decklist=DECK).advance(successor)
    quiet = copy.deepcopy(_base())
    grandchild = child.advance(quiet)
    assert grandchild.attack_locks == child.attack_locks


def test_an_enriched_printout_ledger_is_authoritative():
    successor = copy.deepcopy(_base())
    successor["logs"] = [{"type": 15, "serial": 1, "attackId": 983}]
    child = BoardState.root(_base(), decklist=DECK).advance(successor)
    enriched = copy.deepcopy(_base())
    enriched["attack_locks"] = {"9": {"983": 9}}
    assert child.advance(enriched).attack_locks == (("9", (("983", 9),)),)


def test_a_none_bench_entry_never_resurrects_a_parent_body():
    base = printout(me=player(bench=[None, body(112, 2)]))
    root = BoardState.root(base)
    successor = copy.deepcopy(base)
    successor["current"]["players"][0]["bench"] = [None, body(119, 3)]
    child = root.advance(successor)
    fresh = BoardState.root(successor)
    assert [b.card.card_id for b in child.me.bench] == [119]
    assert child == fresh and child.key == fresh.key


def test_a_fully_quiet_advance_reuses_everything():
    root = BoardState.root(_base(), decklist=DECK)
    child = root.advance(copy.deepcopy(_base()))
    assert child.changed == frozenset()
    assert child.me is root.me and child.them is root.them and child.turn is root.turn
    assert child.deck_counts is root.deck_counts
    assert child.key == root.key


def test_advance_keeps_the_root_viewpoint():
    root = BoardState.root(_base(), decklist=DECK)
    confused = copy.deepcopy(_base())
    confused["current"]["yourIndex"] = 1        # a reprint may not reseat the viewer
    child = root.advance(confused)
    assert child.seat == 0 and child.me.hand is not None
    assert child.changed == frozenset()


def test_a_facedown_active_reveals_across_an_advance():
    hidden_me = player()
    hidden_me["active"] = [None]
    base = printout(me=hidden_me)
    root = BoardState.root(base)
    assert root.me.active is None and root.me.active_hidden
    successor = copy.deepcopy(base)
    successor["current"]["players"][0]["active"] = [body(66, 1)]
    child = root.advance(successor)
    assert child.me.active.card.card_id == 66 and not child.me.active_hidden
    assert ("me", "active") in child.changed and child.key != root.key


def test_a_promotion_rebuilds_active_and_bench_and_reuses_the_stayer():
    root = BoardState.root(_base(), decklist=DECK)
    successor = copy.deepcopy(_base())
    players = successor["current"]["players"]
    knocked_out = players[0]["active"][0]
    players[0]["discard"].append({"id": knocked_out["id"], "serial": knocked_out["serial"],
                                  "playerIndex": 0})
    players[0]["active"] = [players[0]["bench"][0]]          # 112 promotes
    players[0]["bench"] = players[0]["bench"][1:]            # 119 stays
    child = root.advance(successor)
    assert child.me.active.card.card_id == 112
    assert child.me.active.card.facts is not None
    assert child.me.bench[0] is root.me.bench[1]
    assert {("me", "active"), ("me", "bench")} <= child.changed
    assert child.deck_counts == root.deck_counts             # nothing left play


def test_status_flips_and_their_prizes_reach_key_and_changed():
    root = BoardState.root(_base(), decklist=DECK)
    poisoned = copy.deepcopy(_base())
    poisoned["current"]["players"][0]["poisoned"] = True
    child = root.advance(poisoned)
    assert child.changed == {("me", "scalars")} and child.me.poisoned
    assert child.key != root.key
    prized = copy.deepcopy(_base())
    prized["current"]["players"][1]["prize"] = [None] * 2
    other = root.advance(prized)
    assert other.changed == {("them", "scalars")} and other.them.prize_count == 2
    assert other.key != root.key


def test_a_prize_take_keeps_the_unseen_pool_constant():
    deck = (66,) * 3 + (119,) * 2
    base = printout(me=player(hand=[119]), own_prizes={"66": 2})
    root = BoardState.root(base, decklist=deck)
    after = copy.deepcopy(base)
    after["own_prizes"] = {"66": 1}
    after["current"]["players"][0]["hand"].append({"id": 66, "serial": 860, "playerIndex": 0})
    after["current"]["players"][0]["handCount"] = 2
    child = root.advance(after)
    assert ("extras",) in child.changed
    # The prized 66 moved to hand: both deductions shift, the unseen pool is unmoved.
    assert child.deck_counts == root.deck_counts


def test_stadium_changes_are_tracked_and_quiet_ones_reused():
    base = printout(stadium=[{"id": 1252, "serial": 60, "playerIndex": 0}])
    root = BoardState.root(base)
    assert [card.card_id for card in root.stadium] == [1252]
    quiet = root.advance(copy.deepcopy(base))
    assert quiet.stadium is root.stadium
    successor = copy.deepcopy(base)
    successor["current"]["stadium"] = [{"id": 1260, "serial": 61, "playerIndex": 1}]
    child = root.advance(successor)
    assert child.changed == {("stadium",)}
    assert [card.card_id for card in child.stadium] == [1260]


def test_a_select_prompt_appearing_and_vanishing_is_tracked():
    root = BoardState.root(_base(), decklist=DECK)
    asked = copy.deepcopy(_base())
    asked["select"] = {"type": 1, "context": 0, "minCount": 1, "maxCount": 1,
                      "remainDamageCounter": 0, "remainEnergyCost": 0,
                      "option": [{"type": 7, "index": 0}], "deck": None,
                      "contextCard": None, "effect": None}
    child = root.advance(asked)
    assert child.select is not None and ("select",) in child.changed
    back = child.advance(copy.deepcopy(_base()))
    assert back.select is None and ("select",) in back.changed


def test_a_reordered_bench_reuses_nodes_and_keeps_the_key():
    root = BoardState.root(_base(), decklist=DECK)
    successor = copy.deepcopy(_base())
    successor["current"]["players"][0]["bench"].reverse()
    child = root.advance(successor)
    assert child.me.bench[0] is root.me.bench[1]
    assert child.me.bench[1] is root.me.bench[0]
    assert child.key == root.key
    assert child.changed == {("me", "bench")}


def test_a_three_step_chain_stays_equal_to_fresh_builds():
    step1 = copy.deepcopy(_base())
    step1["current"]["players"][0]["active"][0]["hp"] = 60
    step2 = copy.deepcopy(step1)
    step2["current"]["players"][0]["hand"].append({"id": 66, "serial": 850, "playerIndex": 0})
    step2["current"]["players"][0]["handCount"] = 3
    step3 = copy.deepcopy(step2)
    step3["current"]["supporterPlayed"] = True
    board = BoardState.root(_base(), decklist=DECK)
    for printout_step in (step1, step2, step3):
        board = board.advance(printout_step)
        fresh = BoardState.root(printout_step, decklist=DECK)
        assert board == fresh and board.key == fresh.key


def test_deck_counts_recompute_when_my_hand_changed():
    root = BoardState.root(_base(), decklist=DECK)
    successor = copy.deepcopy(_base())
    successor["current"]["players"][0]["hand"].append(
        {"id": 66, "serial": 850, "playerIndex": 0})
    child = root.advance(successor)
    assert child.deck_counts != root.deck_counts
    assert child.me.hand.count(66) == 1
