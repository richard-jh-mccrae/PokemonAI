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
def test_the_promote_decider_off_does_not_take_the_ko():
    """Baseline (the pre-fix defect): f26 promotes the wrong body and forfeits the Knock Out — pins
    that the fix, not the fixture, is what lands it.

    The LEVER changed with ADR-0100 (#141). `promote_ko_aware` was the kill-switch for
    `promote-the-ko-attacker`, and that rung is DELETED; the pick site's Knock-Out layer is now
    `_promote_ko_tactical`, which rides the `promote_retreat_value` switch alongside the residual
    it sums with. So the degraded mode this test pins is the decider OFF — which reproduces the
    shipped defect exactly, and is what makes OFF a coherent state rather than half an agent."""
    obs = _fixture("ml_lethal_recover_energy_retreat_ko_f26")["obs"]
    promoted, opp_ko = _drive_promote(
        _pilot("mega_lucario", promote_retreat_value=False), obs, [1])
    assert promoted != _MEGA_LUCARIO_EX and not opp_ko


# ─────────────────────────── Proposal B: boost lethal (f24) ───────────────────────────

# ⚠ f24's ``[correct]``-only cascade is a SAMPLE, not a fact (#178, measured 2026-07-27). Driving one
# step and letting decide() play out the rest makes the sim draw 8-11 cards off the deck `_seed_zones`
# seeded from a PREDICTED multiset and the engine shuffled — so its verdict is whatever that shuffle
# allowed. Measured over 30 fresh processes: flags-ON None ×30 (the engine reaches its own win and
# `_engine_confirms_win` declines to certify a shuffle-dependent True); flags-OFF False ×29, None ×1
# — the lucky shuffle where closed-form recognition composes the line WITHOUT the tier. That 1-in-30
# is what failed the full suite here. No assertion below may turn on that verdict.
#
# Everything else in this module is draw-free and asserted exactly, f24's own explicit line included.

@pytest.mark.req("REQ-BOOST-LETHAL-0001")
def test_boost_lethal_f24_composes_the_win_line_and_is_never_refuted():
    """The fix's gate, on the part of it that is a fact: with the boost tier + KO-aware promote ON,
    f24's ``[correct]``-only form is NEVER refuted — decide() composes attach->boost->boost->retreat->
    promote->swing far enough that the engine never passes the turn to the opponent unresolved, which
    is the refute this gate would otherwise show.

    It cannot assert ``is True``. The engine does reach its own win here, but only via a cascade that
    drew 8-11 cards off the shuffled predicted deck, so that True holds for one shuffle and
    `_engine_confirms_win` demotes it to None (see the note above). The REPRODUCIBLE proof that the
    target win is real is the explicit line below — which is measurably draw-free."""
    fx = _fixture("ml_lethal_retreat_boost_to_ko_f24")
    assert engine_confirms(fx, _pilot("mega_lucario", promote_ko_aware=True,
                                      boost_lethal=True)) is not False


@pytest.mark.req("REQ-BOOST-LETHAL-0001")
def test_boost_lethal_f24_target_is_real():
    """Proof-of-target: the full explicit win line IS a real engine win, and reproducibly so — driving
    every step leaves the cascade nothing to draw for (measured: zero DRAW, zero COIN, one prize take,
    which the verdict is invariant to). This is the multi-step gate `lethal_helpers.engine_confirms`
    documents for a lethal whose decide() follow-up hooks can't be trusted to compose it.

    The old OFF-side bookend is DELETED, not moved: it asserted that the flag-off cascade "still
    REFUTES ... closed-form recognition alone never composes it", and that is false as measured — it
    composes on roughly 1 shuffle in 30. The claim was never about the tier; it was about the deck
    order the process happened to draw."""
    fx = _fixture("ml_lethal_retreat_boost_to_ko_f24")
    win_line = [[5], [1], [1], [2], [0], [0], [2]]
    assert engine_confirms(fx, _pilot("mega_lucario"), line=win_line) is True


@pytest.mark.req("REQ-BOOST-LETHAL-0001")
def test_boost_lethal_inert_on_mega_starmie_f110():
    """Inert where inapplicable: a shipped mega_starmie recover-energy win still confirms with the new
    tiers ON — no boosted {F} body there, so the boost tier never mis-generates a win."""
    fx = _fixture("ms_lethal_recover_energy_to_win_f110")
    pilot = _pilot("mega_starmie", promote_ko_aware=True, boost_lethal=True)
    assert pilot._engine_confirms_win(fx["obs"], [fx["correct"]], max_cascade=40) is True


# ─────────────────── retreat-enabler lethal (ml f15, retreat_enabler_lethal) ───────────────────

@pytest.mark.req("REQ-RETREAT-ENABLER-LETHAL-0001")
def test_retreat_enabler_lethal_f15_locks_and_wins_end_to_end_when_flag_on():
    """ml f15 (a thrown turn-3 WIN): Team Rocket's Petrel -> tutor Air Balloon -> attach it to the Active
    Makuhita (retreat 2-2=0) -> free retreat -> promote Mega Lucario ex -> Aura Jab {F} 130 >= Riolu 80,
    opp bench empty -> WIN. With ``retreat_enabler_lethal`` ON the tier LOCKS the win (planned.goal=='win',
    next_step==[0]) and the grab/attach steering drives the full cascade to a real engine WIN."""
    fx = _fixture("ml_petrel_balloon_retreat_lethal_f15")
    pilot = _pilot("mega_lucario", promote_ko_aware=True, retreat_enabler_lethal=True)
    d = pilot.explain(fx["obs"])
    assert d.chosen == [0]
    assert d.planned is not None and d.planned.goal == "win" and d.planned.verified is True
    assert engine_confirms(fx, pilot) is True


@pytest.mark.req("REQ-RETREAT-ENABLER-LETHAL-0001")
def test_retreat_enabler_lethal_off_does_not_lock_f15():
    """Soundness bookend: with the flag OFF (default) the tier is inert — no win LOCK, and the
    ``[correct]``-only cascade REFUTES (closed-form recognition alone never composes the Petrel ->
    Air Balloon -> retreat -> promote steering)."""
    fx = _fixture("ml_petrel_balloon_retreat_lethal_f15")
    pilot = _pilot("mega_lucario", promote_ko_aware=True)   # retreat_enabler_lethal defaults False
    d = pilot.explain(fx["obs"])
    assert d.planned is None or d.planned.goal != "win"
    assert engine_confirms(fx, pilot, line=[0]) is False


@pytest.mark.req("REQ-RETREAT-ENABLER-LETHAL-0001")
def test_retreat_enabler_lethal_counter_fixtures_do_not_regress():
    """The three shipped lethal counter-fixtures still behave with the tier ON: f110 confirms a WIN and
    f24 is never refuted (its `[correct]`-only verdict is a shuffle sample — see the note above the
    boost-lethal gates), f26/f48 stay KO-not-win (engine_confirms is a WIN gate, so it correctly
    refutes them by category — they ship via promote_ko_aware, not this gate)."""
    on = dict(promote_ko_aware=True, boost_lethal=True, retreat_enabler_lethal=True)
    assert engine_confirms(_fixture("ml_lethal_retreat_boost_to_ko_f24"),
                           _pilot("mega_lucario", **on)) is not False
    assert engine_confirms(_fixture("ms_lethal_recover_energy_to_win_f110"), _pilot("mega_starmie", **on)) is True
    assert engine_confirms(_fixture("ml_lethal_recover_energy_retreat_ko_f26"), _pilot("mega_lucario", **on)) is False
    assert engine_confirms(_fixture("ml_lethal_recover_energy_via_gong_f48"), _pilot("mega_lucario", **on)) is False
