from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from common import (
    Actor,
    Chance,
    Choice,
    Deterministic,
    BellmanLedger,
    Refresh,
    Terminal,
    Unknown,
    enumerate_legal_actions,
)
from deprecated.bellman.state import DecisionState, OpponentBelief, TurnBudgets
from common.algebra import Edge, WeightedEdge
from train.blunder.store import load_corrections


REPO = Path(__file__).resolve().parents[2]
DECK = tuple(int(line) for line in (REPO / "src" / "agents" / "mega_starmie" /
                                    "deck.csv").read_text().split())


def _main_obs():
    corrections = load_corrections(REPO / "data" / "corrections")
    return next(c.obs for c in corrections if c.agent == "mega_starmie"
                and ((c.obs or {}).get("select") or {}).get("context") == 0)


def test_state_is_immutable_semantic_and_carries_allowances():
    obs = deepcopy(_main_obs())
    state = DecisionState.from_observation(obs, deck=DECK, deck_name="mega_starmie")
    same = DecisionState.from_observation(deepcopy(obs), deck=DECK, deck_name="mega_starmie")
    assert state.semantic_key == same.semantic_key
    obs["current"]["supporterPlayed"] = not obs["current"]["supporterPlayed"]
    changed = DecisionState.from_observation(obs, deck=DECK, deck_name="mega_starmie")
    assert changed.semantic_key != state.semantic_key
    assert changed.budgets.supporter != state.budgets.supporter


def test_belief_mass_and_node_algebra_are_explicit():
    with pytest.raises(ValueError, match="sum"):
        OpponentBelief(visible=(), archetypes=(("x", 0.8),), unknown_mass=0.3)
    state = DecisionState.from_observation(_main_obs(), deck=DECK, deck_name="mega_starmie")
    deterministic = Deterministic(state)
    assert Choice(Actor.OURS, (Edge("a", deterministic),)).actor is Actor.OURS
    assert Choice(Actor.OPPONENT, (Edge("promote", deterministic),)).actor is Actor.OPPONENT
    chance = Chance((WeightedEdge(0.5, "heads", deterministic),
                     WeightedEdge(0.5, "tails", deterministic)))
    assert sum(edge.probability for edge in chance.children) == 1.0
    with pytest.raises(ValueError, match="sum"):
        Chance((WeightedEdge(0.4, "heads", deterministic),))
    assert Unknown("unsupported", "card clause").missing_fact == "card clause"
    assert Terminal(state, "end", BellmanLedger()).ledger.total == 0.0
    refresh = Refresh(900, ((5, 3), (3, 5)), True)
    assert refresh.draws == ((5, 3), (3, 5))
    assert not hasattr(refresh, "state")


def test_every_corpus_menu_index_is_covered_once_with_stable_identity():
    seen = 0
    for correction in load_corrections(REPO / "data" / "corrections"):
        if correction.agent != "mega_starmie" or correction.obs is None:
            continue
        obs = correction.obs
        actions = enumerate_legal_actions(obs)
        offered = len(((obs.get("select") or {}).get("option") or ()))
        select = obs.get("select") or {}
        if select.get("minCount", 1) == select.get("maxCount", 1) == 1:
            flattened = [selection[0] for action in actions
                         for selection in action.equivalent_selections]
            assert sorted(flattened) == list(range(offered))
        else:
            from math import comb
            want = sum(comb(offered, count) for count in range(
                max(0, int(select.get("minCount", 1))),
                min(offered, int(select.get("maxCount", 1))) + 1))
            assert sum(len(action.equivalent_selections) for action in actions) == want
        again = enumerate_legal_actions(deepcopy(obs))
        assert [(action.identity, action.selection) for action in actions] == [
            (action.identity, action.selection) for action in again]
        seen += offered
    assert seen > 500


def test_an_impossible_minimum_clamps_to_the_closest_legal_submission():
    # A menu demanding more picks than it offers must still yield a submittable action —
    # an empty action list upstream is a raise, which is a forfeit in deployment.
    obs = {
        "current": {"yourIndex": 0, "players": [
            {"hand": [{"id": 1120, "serial": 10}, {"id": 1227, "serial": 11}]}, {},
        ]},
        "select": {"minCount": 3, "maxCount": 3, "option": [
            {"type": 3, "area": 2, "index": 0, "playerIndex": 0},
            {"type": 3, "area": 2, "index": 1, "playerIndex": 0},
        ]},
    }
    actions = enumerate_legal_actions(obs)
    assert actions and actions[0].selection == (0, 1)


def test_combination_enumeration_is_capped_cheapest_counts_first():
    hand = [{"id": 1000 + index, "serial": index} for index in range(24)]
    obs = {
        "current": {"yourIndex": 0, "players": [{"hand": hand}, {}]},
        "select": {"minCount": 0, "maxCount": 6, "option": [
            {"type": 3, "area": 2, "index": index, "playerIndex": 0}
            for index in range(24)
        ]},
    }
    actions = enumerate_legal_actions(obs)
    total = sum(len(action.equivalent_selections) for action in actions)
    assert total <= 4096                              # bounded, not the ~190k uncapped
    assert any(action.selection == () for action in actions)   # the decline survives the cap


def test_identical_playable_hand_copies_are_one_action_and_cover_both_indices():
    obs = {
        "current": {"yourIndex": 0, "players": [
            {"hand": [{"id": 1120, "serial": 10}, {"id": 1120, "serial": 11}]},
            {},
        ]},
        "select": {"minCount": 1, "maxCount": 1, "option": [
            {"type": 7, "index": 0}, {"type": 7, "index": 1},
        ]},
    }
    actions = enumerate_legal_actions(obs)
    assert len(actions) == 1
    assert actions[0].selection == (0,)
    assert actions[0].equivalent_selections == ((0,), (1,))
