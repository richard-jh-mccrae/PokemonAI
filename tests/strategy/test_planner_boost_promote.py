"""Engine-backed gates for the coupled promote/boost change (blunder-buster, two thrown WINs):

- ``promote_ko_aware`` (Proposal C) — after an energy grab the retreat/promote must bring up the
  benched body whose affordable attack KOs the opponent's Active. ml f26/f48: promote Mega Lucario ex
  (Aura Jab 130 >= Tangela 80), not Solrock (Cosmic Beam 70). These are KOs, NOT this-turn wins, so
  they are gated by the promote pick landing the KO — NOT routed through ``engine_confirms`` (a WIN
  gate that correctly refutes them by category).
- ``boost_lethal`` (Proposal B) — the ``_family_win_candidates`` tier that composes promote-a-benched-
  {F}-attacker -> play N damage-boost Items -> swing lethal. ml f24: attach {F}->Solrock, play 2x
  Premium Power Pro (+30 each), retreat Lunatone, promote Solrock, Cosmic Beam 70+60=130 OHKOs
  Duraludon 130 (opp bench empty -> a bench-empty win). Gated end-to-end by ``engine_confirms``.

Imports the committed native ``cg`` lib (offline on Windows + Linux); skips cleanly when absent.
"""
import json
from dataclasses import asdict
from pathlib import Path

import pytest

pytest.importorskip("cg")

import sys                                                          # noqa: E402

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "tests") not in sys.path:
    sys.path.insert(0, str(REPO / "tests"))

from cg import api as cgapi                                         # noqa: E402
from cg.api import all_attack                                       # noqa: E402
from common.cards import CardFunctions                             # noqa: E402
from common.effects import CardEffects                             # noqa: E402
from common.pilot import Pilot                                     # noqa: E402
from common.scouting.provider import (                             # noqa: E402
    EngineCardStatProvider, build_attack_stats, load_attack_overrides,
    parse_attack_bench_snipe, parse_attack_recoil)
from common.strategy import Strategy                               # noqa: E402
from common.strategy.general_strategy import GENERAL_STRATEGY      # noqa: E402
from common.strategy.planner import _prune_none                    # noqa: E402
from lethal_helpers import engine_confirms                         # noqa: E402

_MEGA_LUCARIO_EX = 678
_SWITCH, _TO_ACTIVE = 3, 4


def _deck(agent):
    return [int(x) for x in (REPO / "src" / "agents" / agent / "deck.csv")
            .read_text(encoding="utf-8").split("\n")[:60]]


def _pilot(agent, **kw):
    atk = all_attack()
    try:
        fns = CardFunctions.load()
    except Exception:
        fns = CardFunctions({})
    return Pilot(Strategy(), _deck(agent), general_strategy=GENERAL_STRATEGY,
                 stats=EngineCardStatProvider(), functions=fns, effects=CardEffects.load(),
                 attacks={a.attackId: a.damage for a in atk},
                 attack_costs={a.attackId: len(a.energies) for a in atk},
                 recoil={a.attackId: parse_attack_recoil(a.text) for a in atk},
                 bench_snipe={a.attackId: parse_attack_bench_snipe(a.text) for a in atk},
                 attack_stats=build_attack_stats(atk, load_attack_overrides()),
                 lethal_verify=True, lethal_family=True, lethal_veto=True, **kw)


def _fixture(name):
    return json.loads((REPO / "tests" / "fixtures" / "corrections" / f"{name}.json")
                      .read_text(encoding="utf-8"))


def _drive_promote(pilot, obs, first_step, *, max_selects=28):
    """Drive ``first_step`` through the pilot's seeded search, letting ``decide()`` complete the cascade
    (as the live agent does). Returns ``(promoted_id, opp_active_ko)`` — the card id decide() brought up
    at the first retreat SWITCH / forced promote, and whether the opponent's Active reached 0 HP during
    the drive. Mirrors ``_engine_confirms_win``'s cascade drive, incl. its boost-tracker feed."""
    cur = obs["current"]
    yi = cur["yourIndex"]
    me, opp = cur["players"][yi], cur["players"][1 - yi]
    yd, yp, od_, op_, oh = pilot._seed_zones(obs, me, opp)
    promoted_id, opp_ko = None, False
    pilot._planning = True
    boost_snap = {k: list(v) for k, v in pilot._turn_boosts._by_side.items()}
    try:
        st = cgapi.search_begin(cgapi.to_observation_class(obs), yd, yp, od_, op_, oh, [],
                                manual_coin=True)
        st = cgapi.search_step(st.searchId, list(first_step))
        for _ in range(max_selects):
            o = st.observation
            c = o.current
            if c is None or c.result != -1 or o.select is None or c.yourIndex != yi:
                break
            od = _prune_none(asdict(o))
            pilot._turn_boosts.observe(od)
            sel = od.get("select") or {}
            opp_now = next((p for p in ((c.players[1 - yi].active) or []) if p), None)
            if opp_now is not None and (opp_now.hp or 0) <= 0:
                opp_ko = True
            chosen = list(pilot.decide(od))
            if promoted_id is None and sel.get("context") in (_SWITCH, _TO_ACTIVE) and chosen:
                promoted_id = pilot._option_card_id(od, sel, (sel.get("option") or [])[chosen[0]])
            st = cgapi.search_step(st.searchId, chosen)
        # final board (the KO may land on the last step before the verdict)
        oc = st.observation.current
        if oc is not None:
            opp_now = next((p for p in ((oc.players[1 - yi].active) or []) if p), None)
            if opp_now is not None and (opp_now.hp or 0) <= 0:
                opp_ko = True
        cgapi.search_end()
    finally:
        pilot._planning = False
        pilot._turn_boosts._by_side = boost_snap
    return promoted_id, opp_ko


# ─────────────────────────── Proposal C: KO-aware promote (f26/f48) ───────────────────────────

@pytest.mark.req("REQ-PROMOTE-KO-0001")
@pytest.mark.parametrize("fixture,grab_step", [
    ("ml_lethal_recover_energy_retreat_ko_f26", [1]),   # grab the Basic {F} Energy
    ("ml_lethal_recover_energy_via_gong_f48", [9]),     # grab via Fighting Gong
])
def test_promote_ko_aware_brings_up_the_ko_body(fixture, grab_step):
    """With ``promote_ko_aware`` ON, after the energy grab the cascade promotes Mega Lucario ex (Aura
    Jab 130 KOs Tangela 80) and takes the KO — where the energy-ranked baseline brings up Solrock
    (Cosmic Beam 70, no KO)."""
    obs = _fixture(fixture)["obs"]
    assert obs.get("search_begin_input")
    promoted, opp_ko = _drive_promote(_pilot("mega_lucario", promote_ko_aware=True), obs, grab_step)
    assert promoted == _MEGA_LUCARIO_EX      # KO-aware pick, not the energy-ranked Solrock
    assert opp_ko                            # the Aura Jab KO actually lands


@pytest.mark.req("REQ-PROMOTE-KO-0001")
def test_promote_ko_aware_off_does_not_take_the_ko():
    """Baseline (flag OFF, the shipped defect): f26 promotes the wrong body and forfeits the KO — pins
    that the fix, not the fixture, is what lands it."""
    obs = _fixture("ml_lethal_recover_energy_retreat_ko_f26")["obs"]
    promoted, opp_ko = _drive_promote(_pilot("mega_lucario"), obs, [1])
    assert promoted != _MEGA_LUCARIO_EX and not opp_ko


# ─────────────────────────── Proposal B: boost lethal (f24) ───────────────────────────

@pytest.mark.req("REQ-BOOST-LETHAL-0001")
def test_boost_lethal_f24_wins_end_to_end_when_flags_on():
    """The fix's gate: once the boost tier + KO-aware promote steer the cascade, f24's ``[correct]``-only
    form drives to a real engine WIN — decide() now composes attach->boost->boost->retreat->promote->
    swing on its own."""
    fx = _fixture("ml_lethal_retreat_boost_to_ko_f24")
    assert engine_confirms(fx, _pilot("mega_lucario", promote_ko_aware=True, boost_lethal=True)) is True


@pytest.mark.req("REQ-BOOST-LETHAL-0001")
def test_boost_lethal_f24_target_is_real_and_off_flag_still_refutes():
    """Soundness bookends: the full explicit line is a REAL win (proof-of-target), and with the flags
    OFF the ``[correct]``-only form still REFUTES (closed-form recognition alone never composes it —
    the byte-identical baseline the shipped `test_engine_confirms_multi_step_line` pins)."""
    fx = _fixture("ml_lethal_retreat_boost_to_ko_f24")
    win_line = [[5], [1], [1], [2], [0], [0], [2]]
    assert engine_confirms(fx, _pilot("mega_lucario"), line=win_line) is True
    assert engine_confirms(fx, _pilot("mega_lucario")) is False


@pytest.mark.req("REQ-BOOST-LETHAL-0001")
def test_boost_lethal_inert_on_mega_starmie_f110():
    """Inert where inapplicable: a shipped mega_starmie recover-energy win still confirms with the new
    tiers ON — no boosted {F} body there, so the boost tier never mis-generates a win."""
    fx = _fixture("ms_lethal_recover_energy_to_win_f110")
    pilot = _pilot("mega_starmie", promote_ko_aware=True, boost_lethal=True)
    assert pilot._engine_confirms_win(fx["obs"], [fx["correct"]], max_cascade=40) is True
