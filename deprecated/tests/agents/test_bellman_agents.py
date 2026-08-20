from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest

from common.cards import CardFunctions
from deprecated.bellman.runtime import (
    BellmanTeacherRuntime, build_teacher_runtime, legacy_roles_resolve,
)
from common.scouting.provider import EngineCardStatProvider


REPO = Path(__file__).resolve().parents[3]
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
    runtime = build_teacher_runtime(
        strategy, deck, stats=None, functions=None, scout=None, briefs=[])
    assert isinstance(runtime, BellmanTeacherRuntime)
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
    roles = legacy_roles_resolve(strategy.roles, deck, stats, CardFunctions.load())
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


def test_one_outcome_claims_one_protected_bundle():
    """Two Mega Lucario declarations ask for the same Lunatone. The allocator protects at most
    two bundles, so an outcome that spends both slots on itself starves every other demand."""
    from deprecated.bellman.demand import StrategyBeamBuilder
    from deprecated.bellman.pilot_profile import PilotProfile
    from deprecated.bellman.solver import ProductionSolver
    from deprecated.bellman.activation import activate_strategies, resolve_strategies
    from types import SimpleNamespace

    strategy = _strategy("mega_lucario")
    solrock, riolu = 676, 677
    observation = {
        "current": {
            "turn": 3, "yourIndex": 0,
            "players": [
                {"hand": [], "active": [{"id": solrock, "serial": 1, "hp": 90, "maxHp": 90}],
                 "bench": [{"id": solrock, "serial": 2, "hp": 90, "maxHp": 90},
                           {"id": riolu, "serial": 3, "hp": 70, "maxHp": 70}],
                 "benchMax": 5, "discard": [], "prize": []},
                {"hand": None, "active": [], "bench": [], "discard": [], "prize": []},
            ],
        },
        "select": {"context": 0, "option": []},
    }
    snapshot = activate_strategies(
        observation, resolve_strategies((), strategy.strategies), roles=strategy.roles)
    pairing = [row for row in snapshot.hints if "solrock_with_lunatone" in row.strategy_id]
    assert len(pairing) == 2, "the Active and the Benched Solrock both want the partner"

    solver = ProductionSolver.__new__(ProductionSolver)
    solver.profile = PilotProfile.resolve(
        global_values={}, authored_deck_overrides={}, provenance="test")
    solver._protected_bundle_diagnostics = {}
    solver._strategy_builder = StrategyBeamBuilder(snapshot)
    state = SimpleNamespace(obs=observation, root_seat=0, deck_counts=())

    assert solver._protected_bundles(state) == ("mega_lucario.complete_the_solrock_pair",)


def test_external_decision_seconds_reserve_the_fallback_tail(monkeypatch):
    strategy = _strategy("mega_starmie")
    strategy.pilot_overrides["clock.remaining_200_seconds"] = 99
    monkeypatch.setenv("AGENT_DECISION_SECONDS", "7")
    deck = [int(value) for value in
            (REPO / "src" / "agents" / "mega_starmie" / "deck.csv").read_text().splitlines()
            if value.strip()]
    runtime = build_teacher_runtime(
        strategy, deck, stats=None, functions=None, scout=None, briefs=[])
    assert runtime.pilot_profile.get("clock.remaining_200_seconds") == 6
    assert runtime.decision_clock.fallback_tail_seconds == 1
    assert runtime.pilot_profile.get("clock.adaptive_enabled") == 0
    # The pinned clock no longer lifts the prover's own clock. That lift is what let one
    # abstention eat 9s of a 10s decision and forfeit a match; the 64-node cap supplies the
    # replay determinism it was there for.
    assert runtime.pilot_profile.get("terminal.max_seconds") == 1.2


def test_the_prover_clock_is_a_ceiling_no_layer_can_raise():
    """1.2s must hold against every source, not merely be the default: `PilotProfile.resolve`
    rejects an out-of-bounds value, so `maximum` is what makes the ceiling real."""
    from deprecated.bellman.pilot_profile import PilotProfile

    assert PilotProfile.resolve(
        global_values={"terminal.max_seconds": 1.2},
        authored_deck_overrides={}, provenance="test").get("terminal.max_seconds") == 1.2
    for layer in ("global_values", "authored_deck_overrides"):
        with pytest.raises(ValueError):
            PilotProfile.resolve(**{layer: {"terminal.max_seconds": 1.21}},
                                 provenance="test")
    # A learned delta cannot climb past it either — that layer clamps rather than raises.
    assert PilotProfile.resolve(
        deck_learned={"terminal.max_seconds": 100.0},
        provenance="test").get("terminal.max_seconds") == 1.2
