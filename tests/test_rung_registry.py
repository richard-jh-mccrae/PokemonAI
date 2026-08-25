from __future__ import annotations

import importlib
from pathlib import Path

from tools.rung_registry import FOLDED


REPO = Path(__file__).resolve().parents[1]


def _resolves(target: str) -> bool:
    module_name, _, attributes = target.partition(":")
    value = importlib.import_module(module_name)
    for attribute in attributes.split("."):
        value = getattr(value, attribute)
    return value is not None


def test_deleted_sim_runners_have_checked_retirement_destinations():
    expected = {"tools/sim/selfplay.py", "tools/sim/corpus.py"}

    assert set(FOLDED) == expected
    assert all(not (REPO / name).exists() for name in expected)
    assert all(fold.adr == "0057" for fold in FOLDED.values())
    assert all(_resolves(fold.symbol) for fold in FOLDED.values())
    assert all(fold.note and len(fold.note) <= 120 for fold in FOLDED.values())
