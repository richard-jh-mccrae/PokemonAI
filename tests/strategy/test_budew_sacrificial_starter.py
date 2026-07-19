"""Budew IS the sacrificial item-lock starter — the declared identity, pinned (user doctrine
2026-07-19, the counter-mover follow-up).

Card facts (data/EN_Card_Data.csv id 235, verified): 30 HP, free retreat, Itchy Pollen — NO cost,
10 damage, opponent can't play Items next turn. The identity decomposes across surfaces that are
ALREADY built and one declaration that had drifted:

  * opener      — `open-the-item-lock-starter` (+35) keys the `item_lock` tag at the pregame pick;
  * sacrificial — worth 0 (the `starter` role is behavioural, never a worth tier): the lock body is
                  MEANT to be spent — soak a hit for one prize (`interpose`, `promote-the-staller`);
  * no funding  — Itchy Pollen is free, so `attach_target_needs` is False and no energy rung ever
                  prices an attach onto Budew (the line eats the Energy — the 86091728-19 priority);
  * startable   — the `starter` Role, declared in STRATEGY.md §7 but never wired into strategy.py
                  (the drift this file closes): `_hand_startable` reads it at the mulligan keep.
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
def test_budew_declares_the_starter_role(pilot):
    """STRATEGY.md §7 declares `BUDEW: ["starter"]`; the executable overlay must agree (the drift
    fix), and a hand holding Budew reads startable at the mulligan keep."""
    assert "starter" in pilot.strategy.roles.get(_BUDEW, []), (
        "Budew's starter Role is declared in STRATEGY.md §7 but not wired in strategy.py")
    assert pilot._hand_startable([{"id": _BUDEW}]), "a Budew hand does not read startable"


@pytest.mark.req("REQ-WORTH-0003")
def test_budew_stays_sacrificial_worth_zero(pilot):
    """The lock body is spent, not kept: its worth MUST stay 0 (behavioural role, no worth tier) so
    the keep/discard/refresh machinery never hoards it like a plan piece. A future tier for
    `starter`/`item_lock` trips this pin deliberately — re-grill the sacrificial doctrine first."""
    assert pilot._role_value(_BUDEW) == 0, (
        f"Budew prices {pilot._role_value(_BUDEW)} — the sacrificial starter must stay worth 0")


@pytest.mark.req("REQ-WORTH-0003")
def test_budew_is_never_a_funding_target(pilot):
    """Itchy Pollen costs nothing: Budew never 'needs' Energy, so `power-up-attacker` /
    `prefer-active-attach-in-setup` have no gate open on it and the turn's Energy always develops a
    real attacker instead — the no-energy-on-the-sacrifice half of the identity."""
    assert not pilot._attach_target_needs({"id": _BUDEW, "energies": []}), (
        "a bare Budew reads as needing Energy — its free attack should close every funding gate")
