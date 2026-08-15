from __future__ import annotations

import ast
from pathlib import Path

from common import (
    END_VALUE, BellmanTurnPlanner, NativeCgTransitionProvider,
)


REPO = Path(__file__).resolve().parents[2]
PACKAGE = REPO / "src" / "common"
MODULES = (
    "__init__.py", "algebra.py", "api.py", "commutativity.py", "damage.py", "damage_context.py", "draws.py",
    "effects.py", "engine.py", "fetch.py", "information.py", "demand.py", "options.py", "planner.py",
    "potential.py", "refresh.py", "solver.py", "state.py", "value.py",
)


def test_end_value_is_the_neutral_continuation_contract():
    assert END_VALUE == 0.0


def test_package_has_no_legacy_strategic_dependency():
    forbidden = {
        "common.composer", "common.pilot", "common.strategy.planner",
        "common.deciders.attach", "common.deciders.order",
        "common.strategy.doctrines.doctrine_fetch",
    }
    found = set()
    for name in MODULES:
        path = PACKAGE / name
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.update(name.name for name in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                found.add(node.module)
    assert not (found & forbidden), sorted(found & forbidden)


def test_common_core_has_no_deck_or_named_card_policy():
    forbidden = (
        "mega_starmie", "starmie", "cinderace", "pokegear", "harlequin", "lillie",
        "alakazam", "abra", "kadabra",
    )
    for name in MODULES:
        path = PACKAGE / name
        source = path.read_text(encoding="utf-8").lower()
        assert not [name for name in forbidden if name in source], path


def test_runtime_boundary_is_deck_neutral():
    assert BellmanTurnPlanner.__module__ == "common.planner"


def test_runtime_uses_the_native_transition_provider():
    assert NativeCgTransitionProvider.__module__ == "common.native_engine"
