from __future__ import annotations

import ast
from pathlib import Path

from common.bellman import (
    END_VALUE, BellmanTurnPlanner, CgpyTransitionProvider,
)


REPO = Path(__file__).resolve().parents[2]
PACKAGE = REPO / "src" / "common" / "bellman"


def test_end_value_is_the_neutral_continuation_contract():
    assert END_VALUE == 0.0


def test_package_has_no_legacy_strategic_dependency():
    forbidden = {
        "common.composer", "common.pilot", "common.strategy.planner",
        "common.deciders.attach", "common.deciders.order",
        "common.strategy.doctrines.doctrine_fetch",
    }
    found = set()
    for path in PACKAGE.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.update(name.name for name in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                found.add(node.module)
    assert not (found & forbidden), sorted(found & forbidden)


def test_common_bellman_has_no_deck_or_named_card_policy():
    forbidden = (
        "mega_starmie", "starmie", "cinderace", "pokegear", "harlequin", "lillie",
        "alakazam", "abra", "kadabra",
    )
    for path in PACKAGE.glob("*.py"):
        source = path.read_text(encoding="utf-8").lower()
        assert not [name for name in forbidden if name in source], path


def test_runtime_boundary_is_deck_neutral():
    assert BellmanTurnPlanner.__module__ == "common.bellman.runtime"


def test_runtime_uses_the_forkable_transition_provider():
    assert CgpyTransitionProvider.__module__ == "common.bellman.engine"
