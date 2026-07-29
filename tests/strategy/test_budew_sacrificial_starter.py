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
  * startable   — the deck's declared rank-1 OPENER. Was the `starter` Role (declared in STRATEGY.md
                  §7, wired 2026-07-19); ADR-0075 retired that Role and moved the declaration to
                  `Strategy.starter_priority`, where it actually drives the Set-Up Active pick.

The opener BEHAVIOUR (Budew takes the Active Spot over the rest of the field) is asserted in
`test_setup_active_placement.py`, which owns that seam. This file keeps the identity claims that are
not about the seam: worth 0, never funded, and the declaration itself.
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
    """STRATEGY.md §7 declares Budew the item-lock starter; the executable overlay must agree. Since
    ADR-0075 that declaration is `Strategy.starter_priority` rank 1 rather than a `starter` Role —
    the Role was retired because it drove nothing, and this is the form that does.

    `_hand_startable` is deliberately NOT asserted here any more: it now reads only the `opener` Tag
    (Explosiveness), and Budew is a plain Basic. That is moot rather than a regression — a hand
    holding any Basic never reaches the mulligan prompt at all (`docs/rulebook.txt` L224: "if either
    player has no Basic Pokemon in their opening hand, that player must take a mulligan"), which is
    exactly why the Role could never change an outcome."""
    assert pilot.strategy.starter_priority[:1] == [_BUDEW], (
        f"Budew must be the declared rank-1 opener; got {pilot.strategy.starter_priority[:1]}")
    assert "starter" not in pilot.strategy.roles.get(_BUDEW, []), (
        "the `starter` Role was retired by ADR-0075 — the declaration is starter_priority")


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
