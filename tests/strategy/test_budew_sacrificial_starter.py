"""Budew IS the sacrificial item-lock starter — the declared identity (user doctrine 2026-07-19).

Card facts (id 235, verified): 30 HP, free retreat, Itchy Pollen — NO cost, 10 damage, opponent
can't play Items next turn. This file keeps the identity claims: finite item-lock worth, never funded, and the
declaration itself. The opener BEHAVIOUR is `test_setup_active_placement.py`'s.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_BUDEW = 235


def _pilot(agent: str):
    spec = importlib.util.spec_from_file_location("tune_mod", REPO / "tools" / "train" / "tune.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._build_pilot(agent)[0]


@pytest.fixture(scope="module")
def pilot():
    return _pilot("dragapult_ex")


@pytest.mark.req("REQ-WORTH-0003")
def test_budew_is_the_decks_declared_rank_one_opener(pilot):
    """ADR-0079 retired the `starter` Role because it drove nothing; `Strategy.starter_priority` is
    the form that does. `_hand_startable` is moot here — any Basic clears the mulligan prompt."""
    assert pilot.strategy.starter_priority[:1] == [_BUDEW], (
        f"Budew must be the declared rank-1 opener; got {pilot.strategy.starter_priority[:1]}")
    assert "starter" not in pilot.strategy.roles.get(_BUDEW, []), (
        "the `starter` Role was retired by ADR-0079 — the declaration is starter_priority")


@pytest.mark.req("REQ-WORTH-0003")
def test_budew_carries_the_shared_item_lock_worth(pilot):
    """Sacrificial means its benefit can justify spending it, not that the finite card is free."""
    from common.card_worth import FUNCTION_TIER
    assert pilot._role_value(_BUDEW) == FUNCTION_TIER["item_lock"] == 10.0


@pytest.mark.req("REQ-WORTH-0003")
def test_budew_is_never_a_funding_target(pilot):
    """A free attack closes every funding gate, so the turn's Energy develops a real attacker."""
    assert not pilot._attach_target_needs({"id": _BUDEW, "energies": []}), (
        "a bare Budew reads as needing Energy — its free attack should close every funding gate")
