from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from common.bellman import (
    Actor, Chance, Choice, DecisionState, Deterministic, Ledger, OpponentBelief, Terminal,
    TurnBudgets, Unknown, enumerate_legal_actions,
)
from common.bellman.algebra import Edge, WeightedEdge
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
    assert Terminal(state, "end", Ledger()).ledger.total == 0.0


def test_every_corpus_menu_index_is_covered_once_with_stable_identity():
    seen = 0
    for correction in load_corrections(REPO / "data" / "corrections"):
        if correction.agent != "mega_starmie" or correction.obs is None:
            continue
        obs = correction.obs
        actions = enumerate_legal_actions(obs)
        offered = len(((obs.get("select") or {}).get("option") or ()))
        flattened = [index for action in actions for index in action.menu_indices]
        assert sorted(flattened) == list(range(offered))
        again = enumerate_legal_actions(deepcopy(obs))
        assert [(action.identity, action.menu_indices) for action in actions] == [
            (action.identity, action.menu_indices) for action in again]
        seen += offered
    assert seen > 500
