from __future__ import annotations

import ast
from pathlib import Path

from common import END_VALUE
from deprecated.bellman import BellmanTurnPlanner
from deprecated.bellman.providers import BellmanNativeProvider


REPO = Path(__file__).resolve().parents[3]
#: The Bellman kernel (quarantined) plus the live modules it still rides; the boundary is about
#: what the core may depend on, not where it sits.
MODULES = tuple((REPO / "src" / "common" / name) for name in (
    "__init__.py", "algebra.py", "api.py", "cards/functions/damage.py",
    "cards/functions/damage_context.py", "cards/functions/draw.py", "cards/functions/energy.py",
    "cards/functions/attack_lock.py", "cards/functions/fetch.py",
    "effects.py", "engine.py", "information.py", "options.py", "refresh.py",
)) + tuple((REPO / "deprecated" / "bellman" / name) for name in (
    "commutativity.py", "demand.py", "planner.py", "potential.py", "solver.py", "state.py",
    "value.py",
))


def test_end_value_is_the_neutral_continuation_contract():
    assert END_VALUE == 0.0


def test_package_has_no_legacy_strategic_dependency():
    forbidden = {
        "common.composer", "common.pilot", "common.strategy.planner",
        "common.deciders.attach", "common.deciders.order",
        "common.strategy.doctrines.doctrine_fetch",
    }
    found = set()
    for path in MODULES:
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
    for path in MODULES:
        source = path.read_text(encoding="utf-8").lower()
        assert not [name for name in forbidden if name in source], path


def test_runtime_boundary_is_deck_neutral():
    assert BellmanTurnPlanner.__module__ == "deprecated.bellman.planner"


def test_the_search_provider_extends_the_live_native_seam():
    assert BellmanNativeProvider.__module__ == "deprecated.bellman.providers"
    from common.native_engine import NativeCgTransitionProvider
    assert issubclass(BellmanNativeProvider, NativeCgTransitionProvider)
