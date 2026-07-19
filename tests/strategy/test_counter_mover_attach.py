"""Munkidori the counter-mover: the attach seam serves the Ability fuel and the stuck Active.

User doctrine (2026-07-19, follow-up to the attach-target-priority seam): every deck Pokémon has a
declared strategic purpose. Munkidori's is Adrena-Brain — relay damage counters onto the opponent's
board to assemble multi-KO Phantom Dive turns AND peel counters off our own bodies (keep an Active
Budew alive). It is declared `counter_mover` (worth: the engine band — a plan piece, not junk).

Two attach behaviours follow, replayed on boards derived from the real 86091728-19 record:
  * The {D} that switches Adrena-Brain on is FUEL, never "wasted": `dont-waste-off-type-energy`
    (attack-cost-only) must stand down, and `fuel-the-dormant-ability` (the attach-side sibling of
    `fetch-the-ability-fuel-color`) endorses it — but only once no benched Line member sits
    un-powered (the 86091728-19 pin: in setup the line eats first).
  * A STUCK Active Munkidori — no un-powered benched line, no better benched body to promote — takes
    the {P} it needs on top of the {D} so Mind Bend (60 + Confusion) is live: with the line fed,
    the `prefer-active-attach-in-setup` stand-down goes quiet and the +8 returns by design.
"""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

_ACTIVE_AREA, _BENCH_AREA = 4, 5
_P_ENERGY, _D_ENERGY, _MUNKIDORI, _DREEPY = 5, 7, 112, 119


def _record():
    corr = REPO / "data" / "corrections" / "dragapult_ex_20260715_32530b9" / "corrections.jsonl"
    for line in corr.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        if str(d.get("episode_id")) == "86091728" and d.get("decision", {}).get("frame") == 19:
            return d
    raise AssertionError("correction 86091728-19 not found in data/corrections/")


def _pilot(agent: str):
    spec = importlib.util.spec_from_file_location("tune_mod", REPO / "tools" / "train" / "tune.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._build_pilot(agent)[0]


def _me(obs):
    return obs["current"]["players"][obs["current"].get("yourIndex", 0)]


def _feed_the_line(obs):
    """Give each benched Dreepy the 1 {P} its cheapest attack costs — no benched Line member needs
    Energy any more, so the setup line-first priority (the 86091728-19 pin) is satisfied."""
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
    """The deck declares Munkidori's purpose — `counter_mover` — and the worth oracle prices it as a
    plan piece (> 0), not a freely-pitchable role-less body."""
    pilot = _pilot("dragapult_ex")
    assert "counter_mover" in pilot.strategy.roles.get(_MUNKIDORI, []), (
        "Munkidori carries no counter_mover Role in the dragapult overlay")
    assert pilot._role_value(_MUNKIDORI) > 0, "the counter-mover prices 0 — still pitchable junk"


@pytest.mark.req("REQ-CORPUS-0001")
def test_dark_fuel_is_not_wasted_once_the_line_is_fed():
    """Line fed, Munkidori bare and Active, hand holds {P}+{D}: the {D} attach switches Adrena-Brain
    on — `dont-waste-off-type-energy` stands down (the colour is Ability fuel, not a wasted
    off-type), `fuel-the-dormant-ability` endorses it, and the pick IS the {D}→Munkidori attach
    (the {P} stays for a body that attacks with it)."""
    rec = _record()
    obs = copy.deepcopy(rec["obs"])
    _feed_the_line(obs)
    d = _pilot(rec["agent"]).explain(obs)
    [dark_active] = _attach_options(rec, obs, card=_D_ENERGY, area=_ACTIVE_AREA)
    trace = next(t for t in d.options if t.index == dark_active)
    fired = {h.id for h, _ in trace.fired}
    assert "dont-waste-off-type-energy" not in fired, (
        "the Ability-fuel {D} still reads as a wasted off-type attach")
    assert "fuel-the-dormant-ability" in fired, "the dormant-Ability fuel attach is not endorsed"
    assert d.chosen == [dark_active], (
        f"expected the {{D}}→Munkidori fuel attach [{dark_active}], got {d.chosen}")


@pytest.mark.req("REQ-CORPUS-0001")
def test_the_line_still_eats_first_in_setup():
    """On the UNTOUCHED 86091728-19 board (two bare benched Dreepy) the fuel endorsement stays
    silent — `fuel-the-dormant-ability` is gated on no benched Line member needing Energy, so the
    human's pinned pick (the {P} to a bare benched Dreepy) is untouched."""
    rec = _record()
    d = _pilot(rec["agent"]).explain(rec["obs"])
    [dark_active] = _attach_options(rec, rec["obs"], card=_D_ENERGY, area=_ACTIVE_AREA)
    trace = next(t for t in d.options if t.index == dark_active)
    assert "fuel-the-dormant-ability" not in {h.id for h, _ in trace.fired}, (
        "the fuel endorsement fires while a benched Line member sits un-powered — it would fight "
        "the 86091728-19 pin's line-first priority")
    assert d.chosen[0] in _attach_options(rec, rec["obs"], card=_P_ENERGY, area=_BENCH_AREA), (
        f"the setup pick moved off the benched line: {d.chosen}")


@pytest.mark.req("REQ-CORPUS-0001")
def test_stuck_active_munkidori_takes_the_psychic_on_top_of_the_dark():
    """Line fed, Munkidori Active already fuelled with its {D}, no better benched body to promote
    (two 1-Energy Dreepy): the {P} goes to Munkidori so Mind Bend (60 + Confusion) is live — the
    stand-down is quiet (no un-powered benched line) and `prefer-active-attach-in-setup` (+8) backs
    the stuck Active again, exactly the user's 'not a bad idea' conditional."""
    rec = _record()
    obs = copy.deepcopy(rec["obs"])
    _feed_the_line(obs)
    active = _me(obs)["active"][0]
    active["energies"] = [_D_ENERGY]
    active["energyCards"] = [{"id": _D_ENERGY, "playerIndex": 0, "serial": 99}]
    d = _pilot(rec["agent"]).explain(obs)
    [psy_active] = _attach_options(rec, obs, card=_P_ENERGY, area=_ACTIVE_AREA)
    assert d.chosen == [psy_active], (
        f"expected the {{P}}→Active-Munkidori arm-up [{psy_active}], got {d.chosen}")
    trace = next(t for t in d.options if t.index == psy_active)
    assert "prefer-active-attach-in-setup" in {h.id for h, _ in trace.fired}, (
        "the Active preference did not return once the benched line was fed")
