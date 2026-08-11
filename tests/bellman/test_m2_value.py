from __future__ import annotations

from copy import deepcopy

import pytest

from common.bellman import ActionIdentity, DecisionState
from common.bellman.value import CardFacts, FAMILY_OWNERS, Potential, ValueOracle, ValueRegistry


HAMMER, LILLIE, WATER = 1120, 1227, 3
DECK = (HAMMER, LILLIE, WATER)


def _obs(hand, *, supporter=False, attached=False, energy=0):
    return {
        "current": {
            "yourIndex": 0, "supporterPlayed": supporter, "energyAttached": attached,
            "retreated": False, "stadiumPlayed": False,
            "players": [
                {"hand": [{"id": cid, "serial": 10 + i, "playerIndex": 0}
                          for i, cid in enumerate(hand)],
                 "discard": [], "active": [], "bench": [], "prize": [], "deckCount": 0},
                {"hand": None, "handCount": 0, "discard": [], "active": [], "bench": [],
                 "prize": [], "deckCount": 0, "energy": energy},
            ],
        },
        "select": {"context": 0, "option": [{"type": 14}]},
    }


def _registry(overrides=None):
    return ValueRegistry(
        functions={HAMMER: ("energy_denial",), LILLIE: ("draw", "shuffle_hand")},
        facts={HAMMER: CardFacts(), LILLIE: CardFacts(), WATER: CardFacts(typed_basic_energy=True)},
        overrides=overrides,
    )


def _families(obs):
    return Potential(total=float(obs["current"].get("board", 0.0)),
                     families=(("board", float(obs["current"].get("board", 0.0))),))


def _state(obs, registry):
    return DecisionState.from_observation(obs, deck=DECK, deck_name="mega_starmie",
                                          value_registry_identity=registry.identity)


def test_portable_worth_is_shared_and_overrides_only_raise():
    registry = _registry()
    assert registry.worth(HAMMER) == 6.0
    assert registry.worth(LILLIE) == 8.0
    assert registry.worth(WATER) == 8.0
    assert _registry({HAMMER: 4.0}).worth(HAMMER) == 6.0
    assert _registry({HAMMER: 11.0}).worth(HAMMER) == 11.0


def test_pure_cost_card_loses_to_end_exactly_zero():
    registry, oracle = _registry(), ValueOracle(_registry(), _families)
    before = _state(_obs([HAMMER]), registry)
    after = _state(_obs([]), registry)
    play = oracle.transition_ledger(before, after, ActionIdentity("play", (HAMMER,)))
    assert play.total < 0.0
    assert dict(play.costs)["hand"] == pytest.approx(6.0 / 120.0)
    assert oracle.transition_ledger(before, before, ActionIdentity("end")).total == 0.0


def test_realized_benefit_minus_same_consumed_cost_is_counted_once():
    registry, oracle = _registry(), ValueOracle(_registry(), _families)
    before_obs, after_obs = _obs([HAMMER]), _obs([])
    after_obs["current"]["board"] = 0.10
    ledger = oracle.transition_ledger(_state(before_obs, registry), _state(after_obs, registry),
                                      ActionIdentity("play", (HAMMER,)))
    assert dict(ledger.benefits)["board"] == pytest.approx(0.10)
    assert dict(ledger.costs)["hand"] == pytest.approx(0.05)
    assert 0.049 < ledger.total < 0.05


def test_every_known_non_end_decision_is_strictly_costly_without_benefit():
    registry, oracle = _registry(), ValueOracle(_registry(), _families)
    state = _state(_obs([]), registry)
    for kind in ("attack", "ability", "card", "retreat"):
        assert oracle.transition_ledger(state, state, ActionIdentity(kind)).total < 0.0


def test_duplicate_hand_options_diminish_but_never_become_free():
    registry = _registry()
    first = registry.hand_worth([LILLIE], _obs([LILLIE]))
    second = registry.hand_worth([LILLIE, LILLIE], _obs([LILLIE, LILLIE]))
    third = registry.hand_worth([LILLIE, LILLIE, LILLIE], _obs([LILLIE] * 3))
    assert first < second < third
    assert second - first == pytest.approx(registry.worth(LILLIE) * 0.55)
    assert third - second == pytest.approx(registry.worth(LILLIE) * 0.25)


def test_every_required_consequence_has_one_named_family_owner():
    flattened = [fact for facts in FAMILY_OWNERS.values() for fact in facts]
    for required in ("game", "prizes", "post-attack safety", "opponent threat removal",
                     "denial counterfactual", "typed attack readiness", "mobility",
                     "evolution dependencies", "persistent Energy", "Bench capacity",
                     "portable card Worth", "future access"):
        assert flattened.count(required) == 1
