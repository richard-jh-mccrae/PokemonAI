"""Deck tracker (own-card perfect-information model) — `common.deck_tracker.OwnCardModel`.

Lib-free synthetic observations. The model resolves the fixed 6-card prize pile from a full search
reveal, then derives the exact deck every turn; soundness = it NEVER asserts a false certainty (it
drops the anchor on any desync). The Board consumes the resolved prizes for prize-EXACT deck knowledge.
"""
import pytest

from common.deck_tracker import OwnCardModel
from common.pilot import Pilot
from common.strategy import Strategy

# A small known "decklist": 3×id1, 3×id2, 4×id3 (10 cards). Same arithmetic as a real 60-card deck.
DECK = [1, 1, 1, 2, 2, 2, 3, 3, 3, 3]


def _poke(cid):
    return {"id": cid, "energyCards": [], "tools": [], "preEvolution": []}


def _obs(*, deck_count, prize, hand=(), discard=(), active=None, bench=(),
         reveal=None, effect=None, turn=2):
    """An observation the tracker reads: my zones + `deckCount` + (optionally) a search that reveals
    the deck (`reveal`) and names the resolving card (`effect`)."""
    me = {
        "hand": [{"id": c} for c in hand],
        "discard": [{"id": c} for c in discard],
        "active": [_poke(active)] if active is not None else [],
        "bench": [_poke(c) for c in bench],
        "prize": [None] * prize,
        "deckCount": deck_count,
    }
    select = {
        "context": 7, "option": [], "contextCard": None,
        "deck": [{"id": c} for c in reveal] if reveal is not None else None,
        "effect": {"id": effect} if effect is not None else None,
    }
    return {"current": {"turn": turn, "yourIndex": 0, "players": [me, None]}, "select": select}


# ----------------------------------------------------------------------- anchoring
@pytest.mark.req("REQ-GEN-0034")
def test_anchor_resolves_prizes_exactly_from_a_full_reveal():
    m = OwnCardModel(DECK)
    # visible {1:1}; the deck (6 cards) is revealed; prizes_remaining 3 -> prizes = decklist−deck−visible.
    m.observe(_obs(deck_count=6, prize=3, hand=[1], reveal=[2, 2, 3, 3, 3, 3]))
    assert m.prize_export() == {1: 2, 2: 1}            # the other 2× id1 and 1× id2 are prized


@pytest.mark.req("REQ-GEN-0034")
def test_resolving_effect_card_is_counted_as_visible():
    m = OwnCardModel(DECK)
    # The search card (id1) is resolving: not in the deck reveal, not in any zone — named by effect.
    # Without counting it the prize total would be 3 (≠ remaining 2) and would NOT anchor.
    m.observe(_obs(deck_count=7, prize=2, hand=[], effect=1, reveal=[1, 1, 2, 2, 2, 3, 3]))
    assert m.prize_export() == {3: 2}


@pytest.mark.req("REQ-GEN-0034")
def test_partial_reveal_does_not_anchor():
    m = OwnCardModel(DECK)
    # select.deck shorter than deckCount (a filtered candidate list) -> never anchor off a subset.
    m.observe(_obs(deck_count=6, prize=3, hand=[1], reveal=[2, 2]))
    assert m.prize_export() is None


# ----------------------------------------------------------------------- maintenance
@pytest.mark.req("REQ-GEN-0034")
def test_prize_take_reconciles_uniquely():
    m = OwnCardModel(DECK)
    m.observe(_obs(deck_count=6, prize=3, hand=[1], reveal=[2, 2, 3, 3, 3, 3]))   # prizes {1:2, 2:1}
    # A KO takes a prized id1 into hand (remaining 3->2, no reveal). Uniquely reconciled: drop one id1.
    m.observe(_obs(deck_count=6, prize=2, hand=[1, 1]))
    assert m.prize_export() == {1: 1, 2: 1}


@pytest.mark.req("REQ-GEN-0034")
def test_prize_take_falls_back_when_ambiguous():
    m = OwnCardModel(DECK)
    # prizes {3:2}; id3 is also still in the deck, so after a take the lost copy is ambiguous -> fall back.
    m.observe(_obs(deck_count=2, prize=2, hand=[1, 1, 1, 2, 2, 2], reveal=[3, 3]))
    assert m.prize_export() == {3: 2}
    m.observe(_obs(deck_count=2, prize=1, hand=[1, 1, 1, 2, 2, 2, 3]))
    assert m.prize_export() is None                   # which prized id3 was taken is unknowable -> no guess


@pytest.mark.req("REQ-GEN-0034")
def test_desync_drops_the_anchor():
    m = OwnCardModel(DECK)
    m.observe(_obs(deck_count=6, prize=3, hand=[1], reveal=[2, 2, 3, 3, 3, 3]))   # prizes {1:2, 2:1}
    assert m.prize_export() is not None
    # All 3× id1 now visible while 2 were "prized" and the prize count didn't drop -> contradiction.
    m.observe(_obs(deck_count=4, prize=3, hand=[1, 1, 1]))
    assert m.prize_export() is None


@pytest.mark.req("REQ-GEN-0034")
def test_reset_on_match_start_and_turn_backwards():
    m = OwnCardModel(DECK)
    m.observe(_obs(deck_count=6, prize=3, hand=[1], reveal=[2, 2, 3, 3, 3, 3]))
    assert m.prize_export() is not None
    m.observe({"select": None})                       # deck-submission step = a new match
    assert m.prize_export() is None

    m.observe(_obs(deck_count=6, prize=3, hand=[1], reveal=[2, 2, 3, 3, 3, 3], turn=5))
    assert m.prize_export() is not None
    m.observe(_obs(deck_count=6, prize=3, hand=[1], turn=1))   # turn went backwards -> reset, no reveal
    assert m.prize_export() is None


@pytest.mark.req("REQ-GEN-0034")
def test_observe_never_raises_on_garbage():
    m = OwnCardModel(DECK)
    for bad in ({}, {"select": {}}, {"current": None, "select": {"deck": [None]}}, {"select": {"deck": 5}}):
        m.observe(bad)                                # must not raise (grader safety)
    assert m.prize_export() is None


# ----------------------------------------------------------------------- Board integration
def _board_obs(*, hand=(), discard=(), active=None, bench=(), prizes=None):
    me = {
        "hand": [{"id": c} for c in hand], "discard": [{"id": c} for c in discard],
        "active": [_poke(active)] if active is not None else [],
        "bench": [_poke(c) for c in bench],
        "prize": [None] * (sum(prizes.values()) if prizes else 0), "deckCount": 0,
    }
    return {"current": {"turn": 2, "yourIndex": 0, "players": [me, None]},
            "select": {"context": 0, "option": [{"type": 14}]}, "own_prizes": prizes}


@pytest.mark.req("REQ-GEN-0034")
def test_board_is_prize_exact_with_the_tracker_annotation():
    pilot = Pilot(Strategy(), deck=DECK)
    # visible {1:1, 2:1}; resolved prizes {1:2, 2:1} -> deck = {1:0, 2:1, 3:4}.
    b = pilot._board(_board_obs(hand=[1], active=2, prizes={1: 2, 2: 1}))
    assert b.deck_definitely_empty_of(1)              # 1 visible + 2 prized -> EXACTLY 0 in deck
    assert not b.deck_definitely_empty_of(2)
    assert b.deck_definitely_has(2) and b.deck_definitely_has(3)
    assert not b.deck_definitely_has(1)               # all id1 accounted (visible + prized)


@pytest.mark.req("REQ-GEN-0034")
def test_board_without_annotation_keeps_the_sound_stateless_oracle():
    pilot = Pilot(Strategy(), deck=DECK)
    # No own_prizes: stateless. id1 has 1 visible of 3 -> the rest could be prized -> NOT empty,
    # and no positive claim is made (deck_definitely_has is False without certainty).
    b = pilot._board(_board_obs(hand=[1], active=2, prizes=None))
    assert not b.deck_definitely_empty_of(1)
    assert b.deck_known_counts is None
    assert not b.deck_definitely_has(2)
