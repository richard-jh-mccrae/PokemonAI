from __future__ import annotations

from collections import Counter
from pathlib import Path

from common import (
    Chance,
    Choice,
    DecisionState,
    Deterministic,
    Refresh,
    RevealChoice,
    Terminal,
    Unknown,
)
from deprecated.bellman import ValueRegistry
from deprecated.bellman.providers import BellmanCgpyProvider as CgpyTransitionProvider
from train.blunder.store import load_corrections
from bellman_helpers import runtime


REPO = Path(__file__).resolve().parents[3]
DECK = tuple(int(line) for line in (REPO / "src" / "agents" / "mega_starmie" /
                                    "deck.csv").read_text().split())
EXPECTED_CORRECTION_ROWS = 346
EXPECTED_SEMANTIC_ACTIONS = 2_069
EXPECTED_SELECTION_INDICES = 2_526
MINIMUM_EXERCISED_CHANCE_NODES = 2


def _rows():
    return [correction for correction in load_corrections(REPO / "data" / "corrections")
            if (correction.agent == "mega_starmie" and correction.obs
                and int((correction.obs.get("current") or {}).get("turn", 0)) > 0)]


def _registry():
    return runtime().registry


def _source_key(obs, option):
    kind = int(option["type"])
    if kind in (7, 8, 9):
        seat = int(obs["current"]["yourIndex"])
        hand = obs["current"]["players"][seat].get("hand") or ()
        return kind, int(hand[int(option["index"])]["id"])
    if kind == 13:
        return kind, int(option["attackId"])
    return kind, None


def test_every_unfiltered_correction_action_has_a_declared_transition():
    registry = _registry()
    actions = covered = unavailable = 0
    unknowns = []
    for correction in _rows():
        state = DecisionState.from_observation(
            correction.obs, deck=DECK, deck_name="mega_starmie")
        provider = CgpyTransitionProvider(state, registry=registry)
        unavailable += not provider.available
        for action in provider.actions(state):
            actions += 1
            covered += len(action.equivalent_selections)
            transition = provider.transition(state, action)
            if isinstance(transition, Unknown):
                unknowns.append((correction.id, transition.reason))
    assert len(_rows()) == EXPECTED_CORRECTION_ROWS
    assert actions == EXPECTED_SEMANTIC_ACTIONS
    assert covered == EXPECTED_SELECTION_INDICES
    assert unavailable == 0
    assert unknowns == [
        (correction_id, "unsupported ability produced no observable effect")
        for correction_id in (
            "eb4fb1f19691", "7d4ff7cff859", "496a7657096f", "baede6accfac",
            "cb70b1405932",
        )
    ]


def test_every_deck_source_resolves_all_nested_mechanics_without_unknown():
    registry = _registry()
    representatives = {}
    for correction in _rows():
        obs = correction.obs
        if int((obs.get("select") or {}).get("context", -1)) != 0:
            continue
        for index, option in enumerate(obs["select"].get("option") or ()):
            representatives.setdefault(_source_key(obs, option), (correction, index))

    deck_sources = {(7, card_id) for card_id in set(DECK)
                    if card_id not in (3, 17, 666, 1031, 1159)}
    deck_sources |= {(8, 3), (8, 17), (8, 1159), (9, 1031)}
    deck_sources |= {(13, attack_id) for attack_id in (965, 1486, 1487, 1488)}
    deck_sources |= {(12, None), (14, None)}
    assert deck_sources <= set(representatives)

    contexts, chance_nodes, unknowns = Counter(), 0, []
    for key in sorted(deck_sources):
        correction, root_index = representatives[key]
        state = DecisionState.from_observation(
            correction.obs, deck=DECK, deck_name="mega_starmie")
        provider = CgpyTransitionProvider(state, registry=registry)
        action = next(action for action in provider.actions(state)
                      if root_index in action.selection)
        seen = set()

        def walk(node):
            nonlocal chance_nodes
            if isinstance(node, Unknown):
                unknowns.append((key, node.reason, node.missing_fact))
                return
            if isinstance(node, Terminal):
                return
            if isinstance(node, (Chance, Choice)):
                chance_nodes += isinstance(node, Chance)
                for edge in node.children:
                    walk(edge.node)
                return
            # The store now supplies clauses even without an effects table, so reveal windows
            # and shuffle-refreshes appear here exactly as they do in production search.
            if isinstance(node, RevealChoice):
                chance_nodes += 1
                for edge in node.choices:
                    walk(edge.node)
                return
            if isinstance(node, Refresh):
                chance_nodes += 1
                return
            assert isinstance(node, Deterministic)
            child = node.state
            context = int((child.obs.get("select") or {}).get("context", -1))
            contexts[context] += 1
            if context in (-1, 0) or child.semantic_key in seen:
                return
            seen.add(child.semantic_key)
            for nested in provider.actions(child):
                walk(provider.transition(child, nested))

        walk(provider.transition(state, action))

    assert not unknowns
    assert chance_nodes >= MINIMUM_EXERCISED_CHANCE_NODES
    assert {3, 5, 7, 8, 15, 17, 18, 19, 21, 22, 30} <= set(contexts)
