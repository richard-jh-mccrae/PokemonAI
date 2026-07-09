"""Opponent Resources subsystem — `common.opponent_resources` (ADR-0047).

The opponent-side mirror of the own-deck models: a stateless probabilistic `copies_left_odds`
(the analog of `deck_odds`) and a match-scoped `OpponentResourceModel` (the analog of the
`deck_tracker`'s `OwnCardModel`). Lib-free synthetic observations. Two-tier epistemics: the
cross-turn signals are SOUND/observed, the copies estimate is PROBABILISTIC and fails OPEN.

Key opponent-side asymmetry vs the own side: the opponent's HAND is hidden (only `handCount` is
known), so an unseen copy may sit in their deck, prizes, OR hand — hand joins prizes in the
hidden non-deck pool.
"""
from collections import Counter

import pytest

from common.deck_odds import p_contains
from common.opponent_resources import (
    OpponentResourceModel,
    copies_left_odds,
    opp_visible_counts,
)


def _poke(cid, *, energies=(), tools=(), pre=()):
    return {"id": cid, "energyCards": [{"id": e} for e in energies],
            "tools": [{"id": t} for t in tools], "preEvolution": [{"id": p} for p in pre]}


def _opp(*, deck_count=30, prizes_hidden=6, hand_count=5, discard=(), active=None, bench=(),
         face_up_prizes=()):
    """A synthetic OPPONENT player dict (the `players[1 - yourIndex]` shape)."""
    prize = [None] * prizes_hidden + [{"id": c} for c in face_up_prizes]
    return {
        "active": [_poke(active)] if active is not None else [],
        "bench": [_poke(c) for c in bench],
        "discard": [{"id": c} for c in discard],
        "prize": prize,
        "handCount": hand_count,
        "deckCount": deck_count,
    }


# ============================================================ opp_visible_counts
@pytest.mark.req("REQ-OPP-0001")
def test_visible_counts_are_discard_board_and_faceup_prizes_never_hand():
    # The opponent's hand is hidden (only handCount known), so it is NOT visible; discard, every
    # board Pokemon + attached Energy/Tools/pre-evolution, and any FACE-UP prize are visible.
    opp = _opp(discard=[1, 1], active=2, bench=[3], face_up_prizes=[4],
               hand_count=7)
    opp["active"] = [_poke(2, energies=[5], tools=[6], pre=[7])]
    assert opp_visible_counts(opp) == Counter({1: 2, 2: 1, 3: 1, 4: 1, 5: 1, 6: 1, 7: 1})


# ============================================================ copies_left_odds (probabilistic)
@pytest.mark.req("REQ-OPP-0002")
def test_copies_odds_treats_hand_as_hidden_nondeck_pool_with_prizes():
    # 4 copies in the build, 1 visible in discard -> 3 unseen. deck 30, prizes 6, hand 5.
    # A card not in the deck is in a prize OR the hand, so the hidden non-deck pool is 6+5=11,
    # NOT just the 6 prizes (the own-side model, where hand is visible, would use 6).
    build = Counter({9: 4, 8: 3})
    opp = _opp(deck_count=30, prizes_hidden=6, hand_count=5, discard=[9])
    odds = copies_left_odds(build, opp)
    assert odds[9] == pytest.approx(p_contains(unseen_copies=3, prizes_hidden=11, deck_count=30))
    # (contrast: had hand been visible like the own side, it would be p_contains(3, 6, 30) — larger)
    assert odds[9] < p_contains(3, 6, 30)


@pytest.mark.req("REQ-OPP-0002")
def test_copies_odds_sound_at_extremes_and_accepts_a_multiset_iterable():
    # More unseen copies than hidden non-deck slots -> pigeonhole present (1.0); every copy visible -> 0.0.
    build = [7, 7, 7, 7]                       # a 4-copy multiset iterable (as representative_build ships)
    opp = _opp(deck_count=30, prizes_hidden=1, hand_count=0, discard=[])   # pool=1 < 4 unseen
    assert copies_left_odds(build, opp)[7] == 1.0
    opp_all_seen = _opp(deck_count=30, prizes_hidden=6, hand_count=5, discard=[7, 7, 7, 7])
    assert copies_left_odds(build, opp_all_seen)[7] == 0.0


@pytest.mark.req("REQ-OPP-0002")
def test_copies_odds_fails_open_on_bad_input():
    # Missing counts must never raise; the per-card hypergeometric collapses to the conservative 1.0
    # ("assume present") rather than a false 0 that would stand a real line down.
    assert copies_left_odds(Counter({1: 4}), {"deckCount": None, "prize": None}) == {1: 1.0}
    # A wholly malformed opp (None) can't even be read -> {} ; the caller's default reads as 1.0.
    assert copies_left_odds(Counter({1: 4}), None) == {}


# ============================================================ OpponentResourceModel (match-scoped)
def _obs(opp, *, turn=2, has_select=True, my_prizes=6, logs=()):
    """A full observation the model reads: opponent at ``players[1]`` (yourIndex 0). ``has_select`` off
    == the initial deck-submission step (match start)."""
    me = {"prize": [None] * my_prizes, "active": [], "bench": [], "discard": [],
          "handCount": 7, "deckCount": 40}
    return {"current": {"turn": turn, "yourIndex": 0, "players": [me, opp]},
            "select": {} if has_select else None, "logs": list(logs)}


@pytest.mark.req("REQ-OPP-0003")
def test_sound_current_values_track_the_latest_opponent_snapshot():
    m = OpponentResourceModel()
    m.observe(_obs(_opp(deck_count=42, hand_count=5), turn=2))
    assert m.deck_count == 42
    assert m.hand_size == 5
    m.observe(_obs(_opp(deck_count=39, hand_count=6), turn=4))
    assert m.deck_count == 39           # sound: just the latest observed value
    assert m.hand_size == 6


@pytest.mark.req("REQ-OPP-0003")
def test_reset_on_match_start_and_on_turn_going_backwards():
    m = OpponentResourceModel()
    m.observe(_obs(_opp(deck_count=30), turn=8))
    assert m.deck_count == 30
    # The deck-submission step (no `select`) marks a fresh game -> forget everything.
    m.observe(_obs(_opp(deck_count=60), turn=1, has_select=False))
    assert m.deck_count is None
    # And a turn counter going backwards (local self-play reuses one process) also resets.
    m.observe(_obs(_opp(deck_count=55), turn=9))
    m.observe(_obs(_opp(deck_count=58), turn=2))
    assert m.hand_size_delta is None    # prior-turn snapshot was dropped by the reset


@pytest.mark.req("REQ-OPP-0004")
def test_hand_and_discard_deltas_are_measured_across_distinct_turns():
    m = OpponentResourceModel()
    m.observe(_obs(_opp(hand_count=5, discard=[1, 2, 3]), turn=2))
    assert m.hand_size_delta is None and m.discard_delta is None    # no prior turn yet
    m.observe(_obs(_opp(hand_count=8, discard=[1, 2, 3, 4, 5, 6]), turn=4))
    assert m.hand_size_delta == 3            # 8 - 5 (previous distinct turn)
    assert m.discard_delta == 3 and m.last_turn_dumped is True       # grew by 3 (>=2)


@pytest.mark.req("REQ-OPP-0004")
def test_delta_uses_previous_turn_not_within_turn_changes():
    m = OpponentResourceModel()
    m.observe(_obs(_opp(hand_count=5), turn=2))
    m.observe(_obs(_opp(hand_count=8), turn=4))          # new turn -> prev snapshot = 5
    m.observe(_obs(_opp(hand_count=7), turn=4))          # same turn: they played a card, 8 -> 7
    assert m.hand_size_delta == 2            # 7 - 5, NOT 7 - 8 (compares to the previous distinct turn)


@pytest.mark.req("REQ-OPP-0004")
def test_small_discard_growth_is_not_a_dump():
    m = OpponentResourceModel()
    m.observe(_obs(_opp(discard=[1]), turn=2))
    m.observe(_obs(_opp(discard=[1, 2]), turn=4))        # grew by 1 -> not a dump
    assert m.discard_delta == 1 and m.last_turn_dumped is False


@pytest.mark.req("REQ-OPP-0005")
def test_took_ko_this_turn_when_my_prize_pile_shrinks_within_the_turn():
    m = OpponentResourceModel()
    m.observe(_obs(_opp(), turn=5, my_prizes=6))         # my turn starts: 6 prizes left
    assert m.took_ko_this_turn is False
    m.observe(_obs(_opp(), turn=5, my_prizes=5))         # I KO'd -> took a prize this turn
    assert m.took_ko_this_turn is True
    m.observe(_obs(_opp(), turn=6, my_prizes=5))         # opponent's turn: flag clears (new turn)
    assert m.took_ko_this_turn is False


@pytest.mark.req("REQ-OPP-0006")
def test_deckout_in_turns_from_the_decline_rate():
    m = OpponentResourceModel()
    m.observe(_obs(_opp(deck_count=40), turn=2))
    assert m.deckout_in_turns is None                    # one sample -> no estimate
    m.observe(_obs(_opp(deck_count=32), turn=6))         # -8 over 4 turns -> 2/turn; 32/2 = 16
    assert m.deckout_in_turns == 16


@pytest.mark.req("REQ-OPP-0006")
def test_deckout_is_silent_when_the_deck_is_not_declining():
    m = OpponentResourceModel()
    m.observe(_obs(_opp(deck_count=30), turn=2))
    m.observe(_obs(_opp(deck_count=33), turn=4))         # grew (shuffle-in) -> no sound rate -> None
    assert m.deckout_in_turns is None
