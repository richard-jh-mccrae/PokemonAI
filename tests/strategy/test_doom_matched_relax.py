"""The `active_doomed` matched-Read-gated swap (`doom_matched_relax`).

Worst-case stays the default. Behind a γ-matched Brief with no discard-recur fuel, the CHARGED
Threat-Clock curve (`Pilot._DOOM_CHARGED`) confirms-or-clears a worst-case doom cry — RELAX-ONLY, so
it never manufactures doom the incumbent did not cry. Unmatched stays byte-identical worst-case: the
ADR-0064 §4 asymmetry is never relax on a guess.

Every pin replays a RULED frame through the agent's real shipped Pilot, fresh per frame. Card facts
for the rulings are verified at `data/EN_Card_Data.csv` and `docs/rules.md` §3/§5.
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
    """Replay through a FRESH shipped Pilot and read the doom DECISION off the LIVE decider —
    `doom_final` IS `Board.active_doomed`, and `decided` is the predicate `_active_doomed` branches on."""
    pilot = _pilot(deck)
    if relax is not None:
        pilot.doom_matched_relax = relax
    if recur is not None:
        pilot.recur_fuel_relax = recur
    obs = fx["obs"]
    board = pilot._board(obs, obs.get("select"))
    state = obs.get("current") or {}
    players = state.get("players") or []
    yi = state.get("yourIndex", 0)
    ma = next((p for p in ((players[yi] or {}).get("active") or []) if p), None)
    opp = players[1 - yi]
    oa = next((p for p in ((opp or {}).get("active") or []) if p), None)
    model, ctx = pilot._state_model, pilot._opp_attack_context
    old = model.theirs.doomed(ma, bodies=[oa], context=ctx)
    matched, fueled, read_oa = pilot._doom_relax_inputs(oa, opp)
    charged = (int(model.theirs.incoming(ma, 1, bodies=[read_oa],
                                         charged=pilot._DOOM_CHARGED, context=ctx))
               if matched else None)
    return {"doom_old": old, "my_hp": int(ma.get("hp", 0) or 0), "doom_charged": charged,
            "matched": matched,
            "decided": pilot._doom_relax_consulted(old, matched, fueled),
            "doom_final": bool(getattr(board, "active_doomed", False))}


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
    """No Brief covers this deck, so the γ-gate never opens and the worst-case oracle decides
    unchanged — even though the charged arithmetic would say safe (ADR-0064 §4)."""
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
    """`recur_fuel_relax` OFF — ADR-0076's pre-quantification guard, still a real code path though the
    flag now ships ON: visible {M} in their discard is fuel the charged budget cannot see."""
    fx = copy.deepcopy(_fixture("dp_doom_relax_archaludon_0e_f30"))
    state = fx["obs"]["current"]
    opp = state["players"][1 - state["yourIndex"]]
    opp["discard"] = list(opp.get("discard") or []) + [
        {"id": METAL, "playerIndex": 1 - state["yourIndex"], "serial": 900 + i} for i in range(2)]
    s = _doom(fx, "dragapult_ex", recur=False)
    assert s["matched"] and not s["decided"]
    assert s["doom_final"] is True


@pytest.mark.req("REQ-GEN-0078")
def test_recur_fuel_still_stays_doomed_under_the_armed_default():
    """The SAME frame under the SHIPPED default (ADR-0076 Amendment D): armed, the relax IS consulted
    and the quantified curve still refuses. Arming narrowed WHEN it runs, never what it concludes."""
    fx = copy.deepcopy(_fixture("dp_doom_relax_archaludon_0e_f30"))
    state = fx["obs"]["current"]
    opp = state["players"][1 - state["yourIndex"]]
    opp["discard"] = list(opp.get("discard") or []) + [
        {"id": METAL, "playerIndex": 1 - state["yourIndex"], "serial": 900 + i} for i in range(2)]
    s = _doom(fx, "dragapult_ex")                    # no override — the shipped PROFILE default
    assert s["matched"] and s["decided"]             # armed: the quantified relax IS consulted
    assert s["doom_final"] is True                   # ...and still refuses to relax this threat
