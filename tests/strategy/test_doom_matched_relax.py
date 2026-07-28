"""Doom-shadow grill pins (2026-07-23) — the `active_doomed` matched-Read-gated swap.

The S1b doom shadow's 15-frame disagreement corpus was ruled frame-by-frame (docs/plans/
doom-shadow-grill-handoff.md, RULED appendix); the swap decision was (b): worst-case stays the
default, and behind a γ-matched Brief with no discard-recur fuel the CHARGED Threat-Clock curve
(`Pilot._DOOM_CHARGED` — manual + one generic supporter-accel attach, Ignition burst on
Evolutions) confirms-or-clears a worst-case doom cry, RELAX-ONLY (it never manufactures doom the
incumbent didn't cry — the 82525101-14 lesson), kill-switched via `doom_matched_relax`.

These pins replay the RULED frames through each agent's real shipped Pilot (fresh per frame):

  - B-frames (relaxation aligns with the human) must RELAX: a bare 0-Energy Terapagos ex
    (Unified Beatdown needs ●●, visible bench caps 30×3=90 < 160) and a 0-Energy Archaludon ex
    (Metal Defender {M}{M}{M} unreachable at 0+2, empty opponent discard) no longer cry doom.
  - C-frames (hidden reach the visible read can't clear) must STAY doomed even matched: Mega
    Abomasnow ex's Hammer-lanche deck-density nuke (600 ceiling ≥ 330 once {W}{W} is budget-
    affordable), Munkidori's Mind Bend into a ×2 Psychic-weak Riolu (60×2=120 ≥ 70 — that
    opponent's discard visibly held a Crispin), and a 1-Energy Archaludon ex (1+2 reaches
    {M}{M}{M} Metal Defender 220).
  - Unmatched (no Brief for the Ho-Oh chaos deck) must stay BYTE-IDENTICAL worst-case doomed —
    the ADR-0064 §4 asymmetry: never relax on a guess.
  - Kill-switch OFF must reproduce the incumbent worst-case on a would-relax frame.
  - The recur-fuel guard: injecting Basic {M} Energy into the Archaludon opponent's discard
    (Assemble Alloy's `discard_energy_recur` reservoir) stands the relax down to worst-case.

Card facts verified at source for the rulings: `data/EN_Card_Data.csv` (Terapagos ex 176,
Mega Abomasnow ex 723, Munkidori 112, Archaludon ex 190, Riolu 677 weak {P}, Crispin 1198,
Waitress 1235, Ignition Energy 17), `docs/rules.md` §3 (1 manual attach + 1 Supporter/turn) and
§5 (weakness ×2).
"""
import copy
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
METAL = 8   # EnergyType.METAL (src/cg/api.py) — Assemble Alloy's Basic {M} fuel


def _pilot(deck):
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    return _build_pilot(deck)[0]


def _fixture(name):
    return json.loads((REPO / "tests" / "fixtures" / "corrections" / f"{name}.json").read_text(encoding="utf-8"))


def _doom(fx, deck, *, relax=None, recur=None):
    """Replay the fixture through a FRESH shipped Pilot (optionally forcing either kill-switch) and
    return its threat shadow — `doom_final` is the live `Board.active_doomed` consumers saw."""
    pilot = _pilot(deck)
    if relax is not None:
        pilot.doom_matched_relax = relax
    if recur is not None:
        pilot.recur_fuel_relax = recur
    shadow = pilot.explain(fx["obs"]).threat_shadow
    assert shadow is not None
    return shadow


@pytest.mark.req("REQ-GEN-0078")
@pytest.mark.parametrize("name, deck", [
    ("ms_doom_relax_bare_terapagos_f21", "mega_starmie"),
    ("ms_doom_relax_bare_terapagos_f29", "mega_starmie"),
    ("dp_doom_relax_archaludon_0e_f30", "dragapult_ex"),
])
def test_ruled_b_frames_relax_behind_the_matched_read(name, deck):
    """The ruled-B pins: matched Read, no recur fuel — the charged curve decides and the doom
    boolean RELAXES (the incumbent worst-case still cries doom, exposed as `doom_old`)."""
    s = _doom(_fixture(name), deck)
    assert s["matched"] and s["decided"]
    assert s["doom_old"] is True                 # the worst-case incumbent still says doomed
    assert s["doom_charged"] < s["my_hp"]        # the charged curve is below my HP…
    assert s["doom_final"] is False              # …and it decided: no doom


@pytest.mark.req("REQ-GEN-0078")
@pytest.mark.parametrize("name, deck", [
    ("ms_doom_guard_abomasnow_density_f44", "mega_starmie"),
    ("ml_doom_guard_munkidori_weakness_f69", "mega_lucario"),
    ("dp_doom_guard_archaludon_1e_f35", "dragapult_ex"),
])
def test_ruled_c_frames_stay_doomed_even_matched(name, deck):
    """The ruled-C guards: even behind the matched Read the charged budget still reaches my HP
    (Hammer-lanche density / ×2 weakness / 1-Energy Metal Defender) — doom must NOT relax."""
    s = _doom(_fixture(name), deck)
    assert s["matched"] and s["decided"]
    assert s["doom_charged"] >= s["my_hp"]
    assert s["doom_final"] is True


@pytest.mark.req("REQ-GEN-0078")
def test_unmatched_read_stays_byte_identical_worst_case():
    """No Brief covers the Ho-Oh chaos deck → the γ-gate never opens: the worst-case oracle
    decides unchanged (ADR-0064 §4 — never relax on a guess), even though the charged arithmetic
    would say safe (Flap 50 < 60; Shining Blaze needs 3 attached)."""
    s = _doom(_fixture("ms_doom_unmatched_hooh_f17"), "mega_starmie")
    assert not s["matched"] and not s["decided"]
    assert s["doom_charged"] is None
    assert s["doom_old"] is True and s["doom_final"] is True


@pytest.mark.req("REQ-GEN-0078")
def test_kill_switch_off_reproduces_the_incumbent():
    """`doom_matched_relax` OFF → byte-identical incumbent behavior on a would-relax frame."""
    s = _doom(_fixture("ms_doom_relax_bare_terapagos_f21"), "mega_starmie", relax=False)
    assert not s["decided"]
    assert s["doom_final"] is True and s["doom_final"] == s["doom_old"]


@pytest.mark.req("REQ-GEN-0078")
def test_recur_fuel_stands_the_relax_down():
    """The Assemble-Alloy hole, `recur_fuel_relax` OFF (ADR-0074's pre-quantification guard,
    `_doom_recur_fueled`, still a real code path even though the flag now ships ON by default):
    the 0-Energy Archaludon ex frame relaxes on an EMPTY opponent discard, but with Basic {M}
    Energy visibly in that discard the `discard_energy_recur` guard refuses the relax entirely
    (evolving re-attaches fuel the charged budget can't see) and the worst-case oracle decides
    again. The ARMED behavior (the SAME fuel, quantified rather than blocked outright) is pinned
    separately in `test_recur_fuel_relax.py`."""
    fx = copy.deepcopy(_fixture("dp_doom_relax_archaludon_0e_f30"))
    state = fx["obs"]["current"]
    opp = state["players"][1 - state["yourIndex"]]
    opp["discard"] = list(opp.get("discard") or []) + [
        {"id": METAL, "playerIndex": 1 - state["yourIndex"], "serial": 900 + i} for i in range(2)]
    s = _doom(fx, "dragapult_ex", recur=False)
    assert s["matched"] and not s["decided"]
    assert s["doom_final"] is True
