from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest

from common.cards import CardFunctions
from common.runtime import BellmanRuntime, build_runtime
from common.scouting.provider import EngineCardStatProvider


REPO = Path(__file__).resolve().parents[2]
AGENTS = ("dragapult_ex", "mega_lucario", "mega_starmie")


def _strategy(name: str):
    path = REPO / "src" / "agents" / name / "strategy.py"
    spec = importlib.util.spec_from_file_location(f"_test_{name}_strategy", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.STRATEGY


@pytest.mark.parametrize("name", AGENTS)
def test_every_deck_builds_the_shared_bellman_runtime(name):
    strategy = _strategy(name)
    deck = [int(value) for value in
            (REPO / "src" / "agents" / name / "deck.csv").read_text().splitlines()
            if value.strip()]
    runtime = build_runtime(
        strategy, deck, stats=None, functions=None, scout=None, briefs=[])
    assert isinstance(runtime, BellmanRuntime)
    assert runtime.strategy.name == name
    assert runtime.registry.identity
    assert len(runtime.deck) == 60


@pytest.mark.parametrize("name", AGENTS)
def test_every_deck_pokemon_resolves_to_a_role(name):
    strategy = _strategy(name)
    deck = [int(value) for value in
            (REPO / "src" / "agents" / name / "deck.csv").read_text().splitlines()
            if value.strip()]
    stats = EngineCardStatProvider()
    roles = strategy.roles.resolve(deck, stats, CardFunctions.load())
    pokemon = {card_id for card_id in deck if stats.get(card_id).is_pokemon}
    assert pokemon <= roles.keys(), f"{name}: missing Roles for {sorted(pokemon - roles.keys())}"


@pytest.mark.parametrize("name", AGENTS)
def test_agent_entrypoint_contains_only_shared_runtime_wiring(name):
    path = REPO / "src" / "agents" / name / "main.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = {(node.module, alias.name) for node in ast.walk(tree)
               if isinstance(node, ast.ImportFrom) for alias in node.names}
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    assert ("common.runtime", "make_agent") in imports
    assert sum(isinstance(call.func, ast.Name) and call.func.id == "make_agent"
               for call in calls) == 1
    assert "pilot" not in path.read_text(encoding="utf-8").lower()


def test_deck_declarations_are_the_only_per_deck_policy_surface():
    starmie, lucario, dragapult = (_strategy(name) for name in AGENTS[::-1])
    assert starmie.prize_plan is not None
    assert lucario.partners
    assert dragapult.roles[121] == ["primary_attacker"]
    assert dragapult.roles.evolves == {}


def test_experiment_decision_seconds_exactly_overrides_deck_clock(monkeypatch):
    strategy = _strategy("mega_starmie")
    strategy.pilot_overrides["clock.remaining_200_seconds"] = 99
    monkeypatch.setenv("AGENT_DECISION_SECONDS", "7")
    deck = [int(value) for value in
            (REPO / "src" / "agents" / "mega_starmie" / "deck.csv").read_text().splitlines()
            if value.strip()]
    runtime = build_runtime(
        strategy, deck, stats=None, functions=None, scout=None, briefs=[])
    assert runtime.pilot_profile.get("clock.remaining_200_seconds") == 7
    assert runtime.pilot_profile.get("clock.adaptive_enabled") == 0
    # The pinned clock also unbinds the prover from the wall clock (node/decision caps only),
    # so replayed node counts cannot vary with machine load.
    assert runtime.pilot_profile.get("terminal.max_seconds") == 60
