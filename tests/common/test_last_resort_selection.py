from __future__ import annotations

from common.decision import safe_legal_selection
from common.strategy.context import _DAMAGE_COUNTER_ANY


def test_fail_safe_avoids_placing_damage_on_a_body_already_at_zero_hp():
    """Phantom Dive's free-placement counters must not pile onto a corpse: a body already
    at or below 0 hp is being knocked out and discarded once the attack resolves, so any
    further counter placed on it is pure waste versus chipping a body still in play."""
    observation = {
        "select": {
            "context": _DAMAGE_COUNTER_ANY,
            "remainDamageCounter": 1,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"playerIndex": 1, "area": 5, "index": 0},
                {"playerIndex": 1, "area": 5, "index": 1},
            ],
        },
        "current": {
            "players": [
                {},
                {"bench": [{"hp": -30}, {"hp": 170}]},
            ],
        },
    }

    assert safe_legal_selection(observation) == [1]


def test_fail_safe_returns_a_choice_with_only_knocked_out_bodies():
    observation = {
        "select": {
            "context": _DAMAGE_COUNTER_ANY,
            "remainDamageCounter": 1,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"playerIndex": 1, "area": 5, "index": 0},
                {"playerIndex": 1, "area": 5, "index": 1},
            ],
        },
        "current": {
            "players": [
                {},
                {"bench": [{"hp": -10}, {"hp": -20}]},
            ],
        },
    }

    assert safe_legal_selection(observation) in ([0], [1])
