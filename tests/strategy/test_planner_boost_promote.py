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
from common.cards import CardFunctions                             # noqa: E402
from common.effects import CardEffects                             # noqa: E402
from common.pilot import Pilot                                     # noqa: E402
from common.scouting.provider import EngineCardStatProvider        # noqa: E402
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
    try:
        fns = CardFunctions.load()
    except Exception:
        fns = CardFunctions({})
    # attack facts flow through the provider's audit-overridden table (ADR-0051)
    return Pilot(Strategy(), _deck(agent), general_strategy=GENERAL_STRATEGY,
                 stats=EngineCardStatProvider(), functions=fns, effects=CardEffects.load(),
                 lethal_verify=True, lethal_family=True, lethal_veto=True, **kw)


def _fixture(name):
    return json.loads((REPO / "tests" / "fixtures" / "corrections" / f"{name}.json")
                      .read_text(encoding="utf-8"))


def _drive_promote(pilot, obs, first_step, *, max_selects=28):
    """``(promoted_id, opp_active_ko)`` — the id decide() brought up at the first SWITCH / forced
    promote, and whether their Active reached 0 HP. Mirrors `_engine_confirms_win`'s cascade drive."""
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
    """The energy-ranked baseline brings up the wrong body and forfeits the Knock Out."""
    obs = _fixture(fixture)["obs"]
    assert obs.get("search_begin_input")
    promoted, opp_ko = _drive_promote(_pilot("mega_lucario", promote_ko_aware=True), obs, grab_step)
    assert promoted == _MEGA_LUCARIO_EX      # KO-aware pick, not the energy-ranked Solrock
    assert opp_ko                            # the Aura Jab KO actually lands


@pytest.mark.req("REQ-PROMOTE-KO-0001")
def test_the_promote_decider_off_does_not_take_the_ko():
    """The Knock-Out layer rides `promote_retreat_value` alongside the residual it sums with
    (ADR-0100), so the degraded mode is the whole DECIDER off rather than half an agent."""
    obs = _fixture("ml_lethal_recover_energy_retreat_ko_f26")["obs"]
    promoted, opp_ko = _drive_promote(
        _pilot("mega_lucario", promote_retreat_value=False), obs, [1])
    assert promoted != _MEGA_LUCARIO_EX and not opp_ko


# ─────────────────────────── Proposal B: boost lethal (f24) ───────────────────────────

# ⚠ f24's ``[correct]``-only cascade is a SAMPLE, not a fact (Issue #178): decide() draws off a deck
# seeded from a PREDICTED multiset and shuffled, so no assertion below may turn on that verdict.

@pytest.mark.req("REQ-BOOST-LETHAL-0001")
def test_boost_lethal_f24_composes_the_win_line_and_is_never_refuted():
    """It cannot assert ``is True``: that verdict is shuffle-dependent and gets demoted to None. The
    reproducible proof that the target win is real is the explicit line below."""
    fx = _fixture("ml_lethal_retreat_boost_to_ko_f24")
    assert engine_confirms(fx, _pilot("mega_lucario", promote_ko_aware=True,
                                      boost_lethal=True)) is not False


@pytest.mark.req("REQ-BOOST-LETHAL-0001")
def test_boost_lethal_f24_target_is_real():
    """Driving EVERY step leaves the cascade nothing to draw for, so this verdict is reproducible
    where the `[correct]`-only one is not."""
    fx = _fixture("ml_lethal_retreat_boost_to_ko_f24")
    win_line = [[5], [1], [1], [2], [0], [0], [2]]
    assert engine_confirms(fx, _pilot("mega_lucario"), line=win_line) is True


@pytest.mark.req("REQ-BOOST-LETHAL-0001")
def test_boost_lethal_inert_on_mega_starmie_f110():
    """No boosted body on this board, so the boost tier must never mis-generate a win."""
    fx = _fixture("ms_lethal_recover_energy_to_win_f110")
    pilot = _pilot("mega_starmie", promote_ko_aware=True, boost_lethal=True)
    assert pilot._engine_confirms_win(fx["obs"], [fx["correct"]], max_cascade=40) is True


# ─────────────────── retreat-enabler lethal (ml f15, retreat_enabler_lethal) ───────────────────

@pytest.mark.req("REQ-RETREAT-ENABLER-LETHAL-0001")
def test_retreat_enabler_lethal_f15_locks_and_wins_end_to_end_when_flag_on():
    """Petrel -> tutor Air Balloon -> attach to the Active (retreat 2-2=0) -> free retreat -> promote
    -> Aura Jab into an empty opposing bench; the grab/attach steering drives the whole cascade."""
    fx = _fixture("ml_petrel_balloon_retreat_lethal_f15")
    pilot = _pilot("mega_lucario", promote_ko_aware=True, retreat_enabler_lethal=True)
    d = pilot.explain(fx["obs"])
    assert d.chosen == [0]
    assert d.planned is not None and d.planned.goal == "win" and d.planned.verified is True
    assert engine_confirms(fx, pilot) is True


@pytest.mark.req("REQ-RETREAT-ENABLER-LETHAL-0001")
def test_retreat_enabler_lethal_off_does_not_lock_f15():
    """OFF is the DEFAULT and the tier is inert: closed-form recognition alone never composes the
    tutor -> attach -> retreat -> promote steering."""
    fx = _fixture("ml_petrel_balloon_retreat_lethal_f15")
    pilot = _pilot("mega_lucario", promote_ko_aware=True)   # retreat_enabler_lethal defaults False
    d = pilot.explain(fx["obs"])
    assert d.planned is None or d.planned.goal != "win"
    assert engine_confirms(fx, pilot, line=[0]) is False


@pytest.mark.req("REQ-RETREAT-ENABLER-LETHAL-0001")
def test_retreat_enabler_lethal_counter_fixtures_do_not_regress():
    """`engine_confirms` is a WIN gate, so the two KO-not-win fixtures are correctly refuted BY
    CATEGORY — they ship via `promote_ko_aware`, not this one."""
    on = dict(promote_ko_aware=True, boost_lethal=True, retreat_enabler_lethal=True)
    assert engine_confirms(_fixture("ml_lethal_retreat_boost_to_ko_f24"),
                           _pilot("mega_lucario", **on)) is not False
    assert engine_confirms(_fixture("ms_lethal_recover_energy_to_win_f110"), _pilot("mega_starmie", **on)) is True
    assert engine_confirms(_fixture("ml_lethal_recover_energy_retreat_ko_f26"), _pilot("mega_lucario", **on)) is False
    assert engine_confirms(_fixture("ml_lethal_recover_energy_via_gong_f48"), _pilot("mega_lucario", **on)) is False
