"""Munkidori the counter-mover: the attach seam serves the Ability fuel and the stuck Active.

User doctrine (2026-07-19, follow-up to the attach-target-priority seam): every deck Pokémon has a
declared strategic purpose. Munkidori's is Adrena-Brain — relay damage counters onto the opponent's
board to assemble multi-KO Phantom Dive turns AND peel counters off our own bodies (keep an Active
Budew alive). It is declared `counter_mover` (worth: the engine band — a plan piece, not junk).

Two attach behaviours follow, replayed on boards derived from the real 86091728-19 record:
  * The {D} that switches Adrena-Brain on is FUEL, never "wasted" — now the decider's **Ability Fuel**
    channel (#139, ADR-0069), additive rather than a tie-break, so a colour doing double duty wins
    outright. In setup the line still eats first, and that priority is now EMERGENT: the deck declares
    Munkidori `counter_mover` — no attacker Role — so the board-evaluated role gate zeroes its attack
    axis while a real attacker alternative is in play.
  * A STUCK Active Munkidori — no un-powered benched line, no better benched body to promote — takes
    the {P} it needs on top of the {D} so Mind Bend (60 + Confusion) is live.

Both the line-first priority and the {D}-fuel-once-fed half are EMERGENT and pinned below, with no
rung and no needs-conditioned gate. What does NOT reproduce is the third pin, the stuck-Active {P}
arm-up: ADR-0069 §4 states the role gate on "an attacker alternative is IN PLAY", so a fed-but-
still-building Dreepy keeps gating Munkidori's own attack. Making the gate per-colour instead was
measured and INVERTS the committed 86091728-19 correction (the human ruled the line eats the {P}
first even though the {D} beside it is dead to the line), so the correction wins and that pin is
marked. The choices are written up in `docs/plans/attach-decider-swap-review.md` §Ruling 3.
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
    """THE Corpus Reader, via the shared test helper (ADR-0087 / ADR-TEMP-243).

    What this replaced named a BUILD DIRECTORY outright — `dragapult_ex_20260715_32530b9` — which no
    glob pattern can see and which breaks silently the day that directory is renamed. That is why
    ADR-TEMP-243 decision 5 widened the rule from "no raw glob" to "nothing outside the store reaches
    the corpus": a check that forbids a spelling teaches people to find another one."""
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
def test_the_dark_is_priced_as_ability_fuel_never_as_waste():
    """The {D} onto a bare Munkidori is FUEL. Two facts carry it, and both hold unconditionally: it
    fills Mind Bend's colourless slot (typed build — a colourless slot absorbs any type, so the old
    colourless-blind waste boolean's verdict is structurally unreachable), and it wakes Adrena-Brain
    (the Ability Fuel channel). So the {D} out-prices the same-build {P} on the SAME body outright."""
    rec = _record()
    obs = copy.deepcopy(rec.obs)
    _feed_the_line(obs)
    d = _pilot(rec.agent).explain(obs)
    [dark_active] = _attach_options(rec, obs, card=_D_ENERGY, area=_ACTIVE_AREA)
    [psy_active] = _attach_options(rec, obs, card=_P_ENERGY, area=_ACTIVE_AREA)
    rows = {r["i"]: r for r in d.attach_working["eq"]}
    assert rows[dark_active]["build"] == rows[psy_active]["build"] > 0   # both fill the ● slot
    assert rows[dark_active]["ability_fuel"] > 0 and rows[psy_active]["ability_fuel"] == 0
    assert rows[dark_active]["tactical"] > rows[psy_active]["tactical"]


@pytest.mark.req("REQ-CORPUS-0001")
def test_dark_fuel_wins_the_turn_once_the_line_is_fed():
    """Line fed, Munkidori bare and Active, hand holds {P}+{D}: the turn's Energy IS the {D}→Munkidori
    fuel attach (the {P} stays for a body that attacks with it).

    EMERGENT, with no rung and no needs-conditioned gate: each Dreepy already holds its {P}, and a
    SECOND {P} fills no remaining slot of Phantom Dive's {R}{P}, so the typed build credits the line
    nothing. Munkidori's attack axis is still gated, but Retreat Equity + Ability Fuel are additive
    and survive the attack-axis gate — which is exactly enough when every alternative is zero."""
    rec = _record()
    obs = copy.deepcopy(rec.obs)
    _feed_the_line(obs)
    d = _pilot(rec.agent).explain(obs)
    [dark_active] = _attach_options(rec, obs, card=_D_ENERGY, area=_ACTIVE_AREA)
    assert d.chosen == [dark_active], (
        f"expected the {{D}}→Munkidori fuel attach [{dark_active}], got {d.chosen}")


@pytest.mark.req("REQ-CORPUS-0001")
def test_the_line_still_eats_first_in_setup():
    """On the UNTOUCHED 86091728-19 board (two bare benched Dreepy) the human's pinned pick — the {P}
    to a bare benched Dreepy — stands. EMERGENT now, from the board-evaluated role gate: the deck gave
    Munkidori only `counter_mover`, so while a Line member is in play its ATTACK AXIS is zero and only
    its mobility/fuel channels speak — which the line's real build step comfortably outbids."""
    rec = _record()
    d = _pilot(rec.agent).explain(rec.obs)
    [dark_active] = _attach_options(rec, rec.obs, card=_D_ENERGY, area=_ACTIVE_AREA)
    row = next(r for r in d.attach_working["eq"] if r["i"] == dark_active)
    assert row["role_gated"] is True and row["attack_axis"] == 0.0
    assert row["ability_fuel"] > 0, "the fuel channel survives the attack-axis gate (per-axis gating)"
    assert d.chosen[0] in _attach_options(rec, rec.obs, card=_P_ENERGY, area=_BENCH_AREA), (
        f"the setup pick moved off the benched line: {d.chosen}")


@pytest.mark.req("REQ-CORPUS-0001")
@pytest.mark.xfail(strict=False, reason="RULING OWED — same ruling as "
                   "test_dark_fuel_wins_the_turn_once_the_line_is_fed "
                   "(docs/plans/attach-decider-swap-review.md).")
def test_stuck_active_munkidori_takes_the_psychic_on_top_of_the_dark():
    """Line fed, Munkidori Active already fuelled with its {D}, no better benched body to promote
    (two 1-Energy Dreepy): the user doctrine says the {P} goes to Munkidori so Mind Bend (60 +
    Confusion) is live."""
    rec = _record()
    obs = copy.deepcopy(rec.obs)
    _feed_the_line(obs)
    active = _me(obs)["active"][0]
    active["energies"] = [_D_ENERGY]
    active["energyCards"] = [{"id": _D_ENERGY, "playerIndex": 0, "serial": 99}]
    d = _pilot(rec.agent).explain(obs)
    [psy_active] = _attach_options(rec, obs, card=_P_ENERGY, area=_ACTIVE_AREA)
    assert d.chosen == [psy_active], (
        f"expected the {{P}}→Active-Munkidori arm-up [{psy_active}], got {d.chosen}")
    trace = next(t for t in d.options if t.index == psy_active)
    assert "prefer-active-attach-in-setup" in {h.id for h, _ in trace.fired}, (
        "the Active preference did not return once the benched line was fed")
    assert trace is not None
