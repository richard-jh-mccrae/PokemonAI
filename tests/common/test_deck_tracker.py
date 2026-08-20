from __future__ import annotations

import json

from cg.api import AreaType, LogType

from common.deck_tracker import OwnCardModel
from common.effects import CardEffects
from common.state import DecisionState
from build_card_effects import DEFAULT_MEASURED, DEFAULT_OUT, DEFAULT_OVERRIDES, render


ME = 0
STACKER = 1188
FIRST = 144
SECOND = 377
DECK = int(AreaType.DECK)
HAND = int(AreaType.HAND)


def _obs(*logs, effect=None):
    select = {"effect": {"id": effect}} if effect is not None else {}
    return {
        "logs": list(logs), "select": select,
        "current": {"turn": 2, "yourIndex": ME, "players": [
            {"hand": [], "discard": [], "active": [], "bench": [], "prize": [None] * 6},
            {},
        ]},
    }


def _move(card_id, serial, *, source=DECK, destination=DECK):
    return {"type": int(LogType.MOVE_CARD), "playerIndex": ME, "cardId": card_id,
            "serial": serial, "fromArea": source, "toArea": destination}


def _draw(card_id, serial):
    return {"type": int(LogType.DRAW), "playerIndex": ME, "cardId": card_id,
            "serial": serial}


def _tracker():
    effects = CardEffects({STACKER: [{"kind": "fetch", "zone": "deck",
                                      "dest": "deck_top", "amount": 2}]})
    return OwnCardModel([STACKER, FIRST, SECOND] + [1] * 57, effects=effects)


def test_deck_tracker_owns_ordered_known_top_and_consumes_draws_once():
    tracker = _tracker()
    tracker.observe(_obs(effect=STACKER))
    tracker.observe(_obs(_move(FIRST, 41), _move(SECOND, 42)))
    assert tracker.known_top_export() == ((41, FIRST), (42, SECOND))

    tracker.observe(_obs(_draw(FIRST, 41)))
    assert tracker.known_top_export() == ((42, SECOND),)

    tracker.observe(_obs(_draw(SECOND, 42)))
    assert tracker.known_top_export() is None


def test_known_top_clears_on_shuffle_unknown_movement_or_serial_mismatch():
    cases = (
        {"type": int(LogType.SHUFFLE), "playerIndex": ME},
        _move(FIRST, 99, source=HAND, destination=DECK),
        _draw(FIRST, 99),
    )
    for event in cases:
        tracker = _tracker()
        tracker.observe(_obs(effect=STACKER))
        tracker.observe(_obs(_move(FIRST, 41)))
        tracker.observe(_obs(event))
        assert tracker.known_top_export() is None


def test_non_stacker_cannot_create_known_top():
    tracker = _tracker()
    tracker.observe(_obs(effect=SECOND))
    tracker.observe(_obs(_move(FIRST, 41)))
    assert tracker.known_top_export() is None


def test_known_top_uses_the_source_from_the_prompt_before_the_log_delta():
    tracker = _tracker()

    tracker.observe(_obs(effect=STACKER))
    tracker.observe(_obs(_move(FIRST, 41), effect=SECOND))

    assert tracker.known_top_export() == ((41, FIRST),)


def test_known_top_participates_in_the_bellman_semantic_key():
    observation = _obs()
    blind = DecisionState.from_observation(observation, deck=(), deck_name="test")
    known = DecisionState.from_observation(
        {**observation, "known_top": ((41, FIRST),)}, deck=(), deck_name="test")

    assert blind.semantic_key != known.semantic_key


def test_known_top_producers_are_generated_from_source_metadata():
    effects = CardEffects.load()
    assert any(clause.get("dest") == "deck_top" for clause in effects.clauses(1188))
    assert any(clause.get("dest") == "deck_top" for clause in effects.clauses(1248))
    source = json.loads(DEFAULT_MEASURED.read_text(encoding="utf-8"))
    overrides = json.loads(DEFAULT_OVERRIDES.read_text(encoding="utf-8"))
    assert DEFAULT_OUT.read_bytes() == render(source, overrides)
