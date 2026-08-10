"""Munkidori the counter-mover: the attach seam serves the Ability fuel and the stuck Active.

Munkidori is declared `counter_mover` — no attacker Role — so the board-evaluated role gate (ADR-0069
§4) zeroes its attack axis while an attacker alternative is IN PLAY, while the additive Ability Fuel
channel survives. Two of the three behaviours below are EMERGENT from that, with no rung and no
needs-conditioned gate; the third (the stuck-Active {P} arm-up) is an owed ruling carried as a STRICT
xfail. The doctrine is the user ruling of 2026-07-19, stated in full at that test.
"""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

_ACTIVE_AREA, _BENCH_AREA = 4, 5
_P_ENERGY, _D_ENERGY, _MUNKIDORI, _DREEPY = 5, 7, 112, 119


def _record():
    """THE Corpus Reader, via the shared test helper — ADR-0089 decision 5: nothing outside the store
    reaches the corpus."""
    from corpus_helpers import corpus_record
    return corpus_record("86091728", 19)


def _pilot(agent: str):
    spec = importlib.util.spec_from_file_location("tune_mod", REPO / "tools" / "train" / "tune.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._build_pilot(agent)[0]


def _me(obs):
    return obs["current"]["players"][obs["current"].get("yourIndex", 0)]


def _feed_the_line(obs):
    """Give each benched Dreepy the 1 {P} its cheapest attack costs, so no Line member needs Energy."""
    for serial, body in enumerate(_me(obs)["bench"], start=100):
        if body["id"] == _DREEPY:
            body["energies"] = [_P_ENERGY]
            body["energyCards"] = [{"id": _P_ENERGY, "playerIndex": 0, "serial": serial}]


def _attach_options(rec, obs, *, card, area):
    return [i for i, o in enumerate(obs["select"]["option"])
            if o.get("type") == 8 and o.get("inPlayArea") == area
            and _me(obs)["hand"][o["index"]]["id"] == card]


@pytest.mark.req("REQ-CORPUS-0001")
def test_munkidori_declares_the_counter_mover_role():
    """The worth oracle must price it as a plan piece (> 0), not a freely-pitchable role-less body."""
    pilot = _pilot("dragapult_ex")
    assert "counter_mover" in pilot.strategy.roles.get(_MUNKIDORI, []), (
        "Munkidori carries no counter_mover Role in the dragapult overlay")
    assert pilot._role_value(_MUNKIDORI) > 0, "the counter-mover prices 0 — still pitchable junk"


@pytest.mark.req("REQ-CORPUS-0001")
def test_the_dark_is_priced_as_ability_fuel_never_as_waste():
    """Both colours advance a legal typed path, but shared future realization may distinguish
    their build. The role gate zeros either attack-axis benefit; {D}'s independent Adrena-Brain
    fuel therefore still out-prices {P} on this off-Line body."""
    rec = _record()
    obs = copy.deepcopy(rec.obs)
    _feed_the_line(obs)
    d = _pilot(rec.agent).explain(obs)
    [dark_active] = _attach_options(rec, obs, card=_D_ENERGY, area=_ACTIVE_AREA)
    [psy_active] = _attach_options(rec, obs, card=_P_ENERGY, area=_ACTIVE_AREA)
    rows = {r["i"]: r for r in d.attach_working["eq"]}
    assert rows[dark_active]["build"] > 0 and rows[psy_active]["build"] > 0
    assert rows[dark_active]["ability_fuel"] > 0 and rows[psy_active]["ability_fuel"] == 0
    assert rows[dark_active]["tactical"] > rows[psy_active]["tactical"]


@pytest.mark.req("REQ-CORPUS-0001")
def test_dark_fuel_wins_the_root_axis_once_the_line_is_fed():
    """EMERGENT: a SECOND {P} fills no remaining slot of Phantom Dive's {R}{P}, and Retreat Equity +
    Ability Fuel are additive, so they survive the attack-axis gate."""
    rec = _record()
    obs = copy.deepcopy(rec.obs)
    _feed_the_line(obs)
    d = _pilot(rec.agent).explain(obs)
    [dark_active] = _attach_options(rec, obs, card=_D_ENERGY, area=_ACTIVE_AREA)
    rows = {row["i"]: row for row in d.attach_working["eq"]}
    assert rows[dark_active]["ability_fuel"] > 0
    assert rows[dark_active]["tactical"] == max(row["tactical"] for row in rows.values())


@pytest.mark.req("REQ-CORPUS-0001")
def test_the_line_still_eats_first_in_setup():
    """EMERGENT from the board-evaluated role gate: while a Line member is in play Munkidori's ATTACK
    AXIS is zero and only its mobility/fuel channels speak, which the line's build step outbids."""
    rec = _record()
    d = _pilot(rec.agent).explain(rec.obs)
    [dark_active] = _attach_options(rec, rec.obs, card=_D_ENERGY, area=_ACTIVE_AREA)
    row = next(r for r in d.attach_working["eq"] if r["i"] == dark_active)
    assert row["role_gated"] is True and row["attack_axis"] == 0.0
    assert row["ability_fuel"] > 0, "the fuel channel survives the attack-axis gate (per-axis gating)"
    assert d.chosen[0] in _attach_options(rec, rec.obs, card=_P_ENERGY, area=_BENCH_AREA), (
        f"the setup pick moved off the benched line: {d.chosen}")


@pytest.mark.req("REQ-CORPUS-0001")
@pytest.mark.xfail(strict=True, reason="RULING OWED — the role gate discards the very "
                   "discrimination the doctrine turns on; see this test's docstring "
                   "and ADR-0069.")
def test_stuck_active_munkidori_takes_the_psychic_on_top_of_the_dark():
    """The doctrine says the {P} goes to Munkidori so Mind Bend is live. It asserts the SUBSTANCE —
    whether the ranking distinguishes at all — because an OUTCOME assertion here went silently XPASS."""
    rec = _record()
    obs = copy.deepcopy(rec.obs)
    _feed_the_line(obs)
    active = _me(obs)["active"][0]
    active["energies"] = [_D_ENERGY]
    active["energyCards"] = [{"id": _D_ENERGY, "playerIndex": 0, "serial": 99}]
    d = _pilot(rec.agent).explain(obs)
    [psy_active] = _attach_options(rec, obs, card=_P_ENERGY, area=_ACTIVE_AREA)
    [dark_active] = _attach_options(rec, obs, card=_D_ENERGY, area=_ACTIVE_AREA)
    score = {t.index: t.score for t in d.options}
    assert score[psy_active] > score[dark_active], (
        f"the arm-up {{P}} [{psy_active}] does not out-score the dead second {{D}} [{dark_active}]: "
        f"{score[psy_active]} vs {score[dark_active]} — the ranking has no opinion, so whichever "
        f"wins does so on the tie-break")
    assert d.chosen == [psy_active], (
        f"expected the {{P}}→Active-Munkidori arm-up [{psy_active}], got {d.chosen}")
