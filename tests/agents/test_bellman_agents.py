from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest

from common.runtime import BellmanRuntime, build_runtime
from common.cards import CardFunctions
from common.effects import CardEffects
from common.scouting.provider import EngineCardStatProvider
from common.value import ValueRegistry


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
        strategy, deck, stats=None, functions=CardFunctions.load(), scout=None, briefs=[])
    assert isinstance(runtime, BellmanRuntime)
    assert runtime.strategy.name == name
    assert runtime.registry.identity
    assert len(runtime.deck) == 60


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
    assert not lucario.partners
    assert lucario.prize_plan is not None
    assert lucario.prize_plan.routes == ((676, 678, 674, 678),)
    assert lucario.roles[678] == ["primary_attacker", "accel_source"]
    assert lucario.roles[676] == ["secondary_attacker"]
    assert 1123 not in lucario.roles  # Shared Switch function supplies its behavior and Worth.
    assert 1174 not in lucario.roles  # Shared Air Balloon function supplies its behavior and Worth.
    functions = CardFunctions.load()
    assert "switch" in functions.tags(1123)
    assert "retreat_reduction" in functions.tags(1174)
    assert functions.partners(675) == (676,)
    assert functions.partners(676) == (675,)
    assert functions.roles(675) == ("engine",)
    assert functions.roles(1071) == ("engine",)
    assert functions.evolves_to(677) == (678,)
    assert functions.evolves_to(673) == (674,)
    deck = [int(value) for value in (REPO / "src" / "agents" / "mega_lucario" /
                                     "deck.csv").read_text().splitlines() if value.strip()]
    registry = ValueRegistry.from_strategy(
        strategy=lucario, stats=None, functions=functions, deck=deck)
    assert registry.partners == {675: (676,), 676: (675,)}
    assert registry.lines == ((673, 674), (677, 678))
    assert registry.roles[677] == ("win_condition_base",)
    assert registry.roles[673] == ("evolution_base",)
    assert 1142 not in lucario.roles  # Generic tutor role comes from card-function data.
    assert 1182 not in lucario.roles  # Generic gust role comes from card-function data.
    assert dragapult.lines[0].path == (119, 120, 121)


def test_mega_lucario_every_card_has_deck_or_shared_runtime_semantics():
    """No Lucario card may become an unmodelled, purpose-free deck slot."""
    strategy = _strategy("mega_lucario")
    deck = {int(value) for value in
            (REPO / "src" / "agents" / "mega_lucario" / "deck.csv").read_text().splitlines()
            if value.strip()}
    functions, effects = CardFunctions.load(), CardEffects.load()
    stats = EngineCardStatProvider()
    stats.warm()

    covered = {
        card_id for card_id in deck
        if (strategy.roles.get(card_id) or functions.tags(card_id) or effects.clauses(card_id)
            or bool(getattr(stats.get(card_id), "is_typed_basic_energy", False)))
    }
    assert covered == deck

    # Exact shared facts for cards whose value is not deck-specific.
    assert stats.get(1174).retreatReduction == 2       # Air Balloon
    assert stats.get(1141).damageBoost == 30           # Premium Power Pro
    assert stats.get(1211).damageBoost == 40           # Black Belt's Training
    assert effects.clauses(1252) == ({                 # Gravity Mountain
        "kind": "stadium_static", "effect": "hp_delta", "amount": -30,
        "applies_to": "stage2", "symmetric": True,
    },)
