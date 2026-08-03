"""Pure DRAW-exhaustion guard for ``tools/meta_tracker/probe_cards.py``.

The live ``probe_card`` drive can run until the deck itself caps a draw measurement. The pure
predicate rejects only that fingerprint: own DRAW logs exactly equal the pre-play deck count.
"""
import pytest

from meta_tracker.probe_cards import _draw_capture_is_deck_limited


def _rec(deck_count=None, logs=None, actor=0):
    rec = {"actor": actor, "logs": logs or []}
    if deck_count is not None:
        rec["deck_count"] = deck_count
    return rec


def _draw(player=0):
    return {"type": 4, "playerIndex": player}


@pytest.mark.req("REQ-EFFECT-0009")
def test_more_deck_than_drawn_is_clean():
    assert not _draw_capture_is_deck_limited(_rec(deck_count=3, logs=[_draw(), _draw()]))


@pytest.mark.req("REQ-EFFECT-0009")
def test_draw_count_equal_to_deck_count_is_deck_limited():
    assert _draw_capture_is_deck_limited(_rec(deck_count=2, logs=[_draw(), _draw()]))


@pytest.mark.req("REQ-EFFECT-0009")
def test_no_draws_are_not_deck_limited_even_with_empty_deck():
    assert not _draw_capture_is_deck_limited(_rec(deck_count=0, logs=[]))


@pytest.mark.req("REQ-EFFECT-0009")
def test_missing_deck_count_is_not_deck_limited():
    assert not _draw_capture_is_deck_limited(_rec(logs=[_draw()]))


@pytest.mark.req("REQ-EFFECT-0009")
def test_opponent_draws_do_not_count_against_actor_deck():
    assert not _draw_capture_is_deck_limited(_rec(deck_count=1, logs=[_draw(player=1)]))
