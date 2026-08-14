from __future__ import annotations

from copy import deepcopy

import pytest

from common import ActionIdentity, DecisionState
from common.value import CardFacts, FAMILY_OWNERS, Potential, ValueOracle, ValueRegistry


HAMMER, LILLIE, WATER = 1120, 1227, 3
DECK = (HAMMER, LILLIE, WATER)
LINE_BASE, LINE_TOP, RUSH_EVOLUTION = 20, 21, 22


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


def test_unused_hand_card_has_no_terminal_turn_wealth():
    registry, oracle = _registry(), ValueOracle(_registry(), _families)
    before = _state(_obs([HAMMER]), registry)
    after = _state(_obs([]), registry)
    play = oracle.transition_ledger(before, after, ActionIdentity("play", (HAMMER,)))
    assert play.total == 0.0
    assert oracle.transition_ledger(before, before, ActionIdentity("end")).total == 0.0


def test_realized_board_benefit_is_counted_once():
    registry, oracle = _registry(), ValueOracle(_registry(), _families)
    before_obs, after_obs = _obs([HAMMER]), _obs([])
    after_obs["current"]["board"] = 0.10
    ledger = oracle.transition_ledger(_state(before_obs, registry), _state(after_obs, registry),
                                      ActionIdentity("play", (HAMMER,)))
    assert dict(ledger.benefits)["board"] == pytest.approx(0.10)
    assert "hand" not in dict(ledger.costs)
    assert ledger.total == pytest.approx(0.10)


def test_acquisition_enables_continuation_without_becoming_terminal_hand_wealth():
    registry, oracle = _registry(), ValueOracle(_registry(), _families)
    root = _state(_obs([LILLIE]), registry)
    consumed_state = root.with_observation(_obs([]))
    restored_state = consumed_state.with_observation(_obs([LILLIE]))
    consumed = oracle.transition_ledger(root, consumed_state, ActionIdentity("play"))
    restored = oracle.transition_ledger(consumed_state, restored_state, ActionIdentity("card"))
    assert "hand" not in dict(restored.benefits)
    assert consumed.total + restored.total == pytest.approx(0.0)

    empty_root = _state(_obs([]), registry)
    acquired_state = empty_root.with_observation(_obs([LILLIE]))
    acquired = oracle.transition_ledger(empty_root, acquired_state, ActionIdentity("card"))
    assert "hand" not in dict(acquired.benefits)


def test_action_labels_do_not_change_the_same_state_transition_value():
    registry, oracle = _registry(), ValueOracle(_registry(), _families)
    state = _state(_obs([]), registry)
    for kind in ("attack", "ability", "card", "retreat", "play"):
        assert oracle.transition_ledger(state, state, ActionIdentity(kind)).total == 0.0


def test_isolated_selection_realizes_the_larger_unmet_need_value(monkeypatch):
    registry = _registry()
    before_obs, after_obs = _obs([]), _obs([])
    before_obs["select"]["context"] = 7
    before_obs["current"]["looking"] = [{"id": LILLIE}]
    before_obs["current"]["board"] = 0.0
    after_obs["current"]["board"] = 0.1
    oracle = ValueOracle(registry, _families)
    monkeypatch.setattr(oracle, "reveal_choice_priority", lambda _before, _after: 0.8)

    ledger = oracle.transition_ledger(
        _state(before_obs, registry), _state(after_obs, registry), ActionIdentity("card"))

    assert dict(ledger.benefits)["hand_demand"] == pytest.approx(0.8)
    assert ledger.total == pytest.approx(0.9)


def test_duplicate_hand_resources_are_linear_and_policy_free():
    registry = _registry()
    first = registry.hand_worth([LILLIE], _obs([LILLIE]))
    second = registry.hand_worth([LILLIE, LILLIE], _obs([LILLIE, LILLIE]))
    third = registry.hand_worth([LILLIE, LILLIE, LILLIE], _obs([LILLIE] * 3))
    assert first < second < third
    assert second - first == pytest.approx(registry.worth(LILLIE))
    assert third - second == pytest.approx(registry.worth(LILLIE))


def test_held_worth_does_not_embed_board_state_policy():
    registry = ValueRegistry(
        functions={RUSH_EVOLUTION: ("search", "rush_evolve")},
        facts={LINE_BASE: CardFacts(pokemon=True, stage="basic"),
               LINE_TOP: CardFacts(pokemon=True, stage="stage1"),
               RUSH_EVOLUTION: CardFacts()},
        line_pairs=((LINE_BASE, LINE_TOP),), lines=((LINE_BASE, LINE_TOP),),
    )
    before_obs = _obs([RUSH_EVOLUTION, RUSH_EVOLUTION])
    before_obs["current"]["players"][0]["bench"] = [{"id": LINE_BASE, "serial": 30}]
    after_obs = _obs([RUSH_EVOLUTION])
    after_obs["current"]["players"][0]["bench"] = [{"id": LINE_TOP, "serial": 30}]
    before = DecisionState.from_observation(
        before_obs, deck=(LINE_BASE, LINE_TOP, RUSH_EVOLUTION), deck_name="test",
        value_registry_identity=registry.identity)
    after = DecisionState.from_observation(
        after_obs, deck=(LINE_BASE, LINE_TOP, RUSH_EVOLUTION), deck_name="test",
        value_registry_identity=registry.identity)

    assert registry.held_worth(RUSH_EVOLUTION, before_obs) == registry.worth(RUSH_EVOLUTION)
    assert registry.held_worth(RUSH_EVOLUTION, after_obs) == registry.worth(RUSH_EVOLUTION)
    ledger = ValueOracle(registry, _families).transition_ledger(
        before, after, ActionIdentity("play", (RUSH_EVOLUTION,)))
    assert "hand" not in dict(ledger.costs)


def test_every_required_consequence_has_one_named_family_owner():
    flattened = [fact for facts in FAMILY_OWNERS.values() for fact in facts]
    for required in ("game", "prizes", "damage progress", "reachable attack value",
                     "in-play resource value"):
        assert flattened.count(required) == 1
