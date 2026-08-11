from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from common.bellman import END_VALUE, ActionIdentity, BellmanUnavailable
from common.bellman.api import require_consumed_cost


REPO = Path(__file__).resolve().parents[2]
PACKAGE = REPO / "src" / "common" / "bellman"


def test_end_is_the_only_cost_free_contract():
    assert END_VALUE == 0.0
    assert require_consumed_cost(ActionIdentity("end"), ()) == ()
    with pytest.raises(ValueError, match="must name"):
        require_consumed_cost(ActionIdentity("play", (1227,)), ())
    with pytest.raises(ValueError, match="End"):
        require_consumed_cost(ActionIdentity("end"), ("card",))


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


def test_inventory_is_fresh_and_closed():
    import subprocess
    import sys

    subprocess.run([sys.executable, str(REPO / "tools" / "bellman_inventory.py"), "--check"],
                   cwd=REPO, check=True)


def test_live_baseline_is_unfiltered_and_keeps_rationales():
    baseline = json.loads((REPO / "docs" / "plans" /
                           "mega-starmie-live-corpus-baseline.json").read_text(encoding="utf-8"))
    assert baseline["records"] == len(baseline["rows"]) == 259
    assert baseline["excluded"] == 0
    assert baseline["agrees"] + baseline["misses"] == baseline["records"]
    assert all("rationale" in row for row in baseline["rows"])


@pytest.mark.xfail(strict=True, raises=BellmanUnavailable,
                   reason="M0 executable fixture: planner implementation starts at M1")
def test_cinderace_lillie_boundary_is_not_silently_delegated():
    raise BellmanUnavailable("60-HP and 50-HP full-turn fixtures are not implemented in M0")
