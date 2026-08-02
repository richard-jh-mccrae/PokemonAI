"""Shared access to the apply-seam coverage census (`tools/apply_seam_coverage.py`, Issue #269).

The census is a CLI script rather than a package module, so importing it takes an explicit by-path
load. That load lives HERE, once: two test modules assert against the census — its own rot-guard
(`test_apply_seam_coverage.py`) and Issue #305's triggered-Ability measurement
(`test_triggered_ability_shape.py`) — and a second by-path loader would be free to drift from the
first without either side noticing.

A module rather than a `tests/strategy/conftest.py`, deliberately: a conftest in that directory
would shadow the root `tests/conftest.py` for the `from conftest import ...` that several strategy
tests already do.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]

_MODULE = None


def census_module():
    """`tools/apply_seam_coverage.py`, imported by path and cached — `tools/` is on `sys.path`
    (root conftest), but the module is a CLI and belongs to no package."""
    global _MODULE
    if _MODULE is None:
        path = _ROOT / "tools" / "apply_seam_coverage.py"
        spec = importlib.util.spec_from_file_location("apply_seam_coverage", path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        _MODULE = mod
    return _MODULE


def load_census() -> tuple:
    """``(module, cards, effects, covers)`` — the census's own sources, loaded the census's own way.

    ``covers`` is Issue #300's per-card clause-coverage ruling, which now lives in
    `card_effects.json` beside the clauses (where the apply seam reads it too) rather than in the
    script's own table."""
    mod = census_module()
    return mod, mod.load_cards(), mod.load_effects(), mod.load_covers()


def census_pool(mod) -> set[int]:
    """Every card id the census measures: our decks plus the scouting artifact's builds."""
    decks = mod.load_our_decks()
    builds, _priors = mod.load_opponent_builds()
    return set().union(*[set(c) for c in decks.values()], *[set(c) for c in builds.values()])
