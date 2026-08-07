"""Shared by-path load of the apply-seam coverage census (`tools/apply_seam_coverage.py`, Issue #269).

One loader, so the two test modules asserting against the census cannot drift. Deliberately NOT a
`tests/strategy/conftest.py` — that would shadow the root `tests/conftest.py`.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import NamedTuple

_ROOT = Path(__file__).resolve().parents[1]

_MODULE = None


class Census(NamedTuple):
    module: object
    #: ``{card id: engine card dict}`` — `tools/meta_tracker/cards.json`
    cards: dict
    #: ``{card id: [Effect Clause, …]}`` — `src/common/card_effects.json` (ADR-0032)
    effects: dict
    #: ``{card id: coverage ruling}`` — `card_effects.json`, beside the clauses (Issue #300)
    covers: dict


def census_module():
    global _MODULE
    if _MODULE is None:
        path = _ROOT / "tools" / "apply_seam_coverage.py"
        spec = importlib.util.spec_from_file_location("apply_seam_coverage", path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        _MODULE = mod
    return _MODULE


def load_census() -> Census:
    mod = census_module()
    return Census(mod, mod.load_cards(), mod.load_effects(), mod.load_covers())


def census_pool(mod) -> set[int]:
    """Our decks plus the scouting artifact's builds."""
    decks = mod.load_our_decks()
    builds, _priors = mod.load_opponent_builds()
    return set().union(*[set(c) for c in decks.values()], *[set(c) for c in builds.values()])
