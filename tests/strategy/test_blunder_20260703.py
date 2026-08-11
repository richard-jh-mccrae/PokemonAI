"""Blunder round 2026-07-03 (mega_starmie) — real-replay regression gates.

Each test replays a captured CRITICAL correction state through the SHIPPED Pilot
(`tune._build_pilot`). The planner-layer sisters of this round gate in `test_planner_engine.py`.
"""
import json
import sys
from pathlib import Path

import pytest

from poc_t4_flips import marks

REPO = Path(__file__).resolve().parents[2]


def _shipped_pilot():
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    pilot, _seeds = _build_pilot("mega_starmie")
    return pilot


def _fixture(name):
    p = REPO / "tests" / "fixtures" / "corrections" / f"{name}.json"
    return json.loads(p.read_text(encoding="utf-8"))


@pytest.mark.req("REQ-PILOT-0026")
def test_critical_eb98_gust_no_longer_forfeits_the_menu_ko_on_its_real_replay_state():
    """A gust that swaps the defender forfeits a menu KO, so it drops behind one in `_finish_turn_last`.
    The gate pins "never the gust", not one exact dev order — a non-defender-changing dev may still lead."""
    fx = _fixture("pilot_eb98")
    pilot = _shipped_pilot()
    decision = pilot.explain(fx["obs"])
    assert decision.chosen != fx["chosen"]                      # the gust pick is gone
    gust_opt = fx["chosen"][0]
    assert gust_opt not in decision.chosen
    nebula = fx["correct"][0]
    assert decision.options[nebula].tactical >= 1000            # the 3-prize KO is seen on the menu


@pytest.mark.req("REQ-GUST-0012")
def test_critical_6f14_harlequin_beats_the_unpayable_gust_on_its_real_replay_state():
    """No attack is payable on this board, so the whether-to-play signal must silence the gust."""
    fx = _fixture("pilot_6f14")
    pilot = _shipped_pilot()
    decision = pilot.explain(fx["obs"])
    assert decision.chosen == fx["correct"]                     # Harlequin, as the human marked
    boss = fx["chosen"][0]
    # The rung-id assertion here is DELETED with its rung (Issue #386): it gave this strict xfail a
    # SECOND cause, and the recorded reason is a seam-coverage gap. One xfail, one cause.


@pytest.mark.req("REQ-GEN-0066")
def test_critical_b323_dead_recycle_is_held_on_its_real_replay_state():
    """The discard's only recycle pool is a setup-only body, so `dont-recycle-the-dead` drops it below End."""
    fx = _fixture("pilot_b323")
    pilot = _shipped_pilot()
    decision = pilot.explain(fx["obs"])
    assert decision.chosen == fx["correct"]                     # End turn, as the human marked
    ns = fx["chosen"][0]
    assert decision.composer["dead_recycle_refused"] == ns       # no playable recycle target exists


@pytest.mark.req("REQ-GUST-0013")
def test_cd91_starved_stall_gust_wins_the_slot_on_its_real_replay_state():
    """Forward-evolution doom plus the energy-famine stall rule must lift the gust over the tutor."""
    fx = _fixture("pilot_cd91")
    pilot = _shipped_pilot()
    decision = pilot.explain(fx["obs"])
    assert decision.chosen == fx["correct"]                     # Boss's Orders, as the human marked
    boss = fx["correct"][0]
    # The rung-id assertion here is DELETED with its rung (Issue #386): it gave this strict xfail a
    # SECOND cause, and the recorded reason is a seam-coverage gap. One xfail, one cause.


@pytest.mark.req("REQ-GEN-0067")
def test_c4f5_powered_active_pitches_ignition_keeps_lillies_on_its_real_replay_state():
    """The Active already carries Nebula Beam's full cost, so Ignition's keep-premise is void."""
    fx = _fixture("pilot_c4f5")
    pilot = _shipped_pilot()
    decision = pilot.explain(fx["obs"])
    assert sorted(decision.chosen) == sorted(fx["correct"])     # [Cinderace, Ignition], as marked


@pytest.mark.req("REQ-PLANNER-0036")
def test_e1db_intended_sequence_commits_from_the_turn8_pre_attach_state():
    """The ruled line (Wally's, then attach, then the KO) belongs to turn 8's REAL decision point,
    BEFORE the attach was spent — so the captured f47 board is REWOUND to that state below."""
    fx = _fixture("pilot_e1db")
    obs = json.loads(json.dumps(fx["obs"]))                     # deep copy
    cur = obs["current"]
    me = cur["players"][cur["yourIndex"]]
    act = me["active"][0]
    act["energies"] = [3]                                       # rewind: only the earlier {W} attached
    act["energyCards"] = [ec for ec in (act.get("energyCards") or []) if ec.get("id") == 3]
    me["hand"] = me["hand"] + [{"id": 17, "playerIndex": 0, "serial": 999}]   # Ignition back in hand
    me["handCount"] = len(me["hand"])
    cur["energyAttached"] = False
    PLAY, ATTACH, RETREAT, ATTACK, END = 7, 8, 12, 13, 14
    opts = [
        {"index": 0, "type": PLAY},                                                 # Poffin
        {"index": 1, "type": PLAY},                                                 # Wally's
        {"index": 4, "type": PLAY},                                                 # Salvatore
        {"index": 6, "type": PLAY},                                                 # Lillie's
        {"area": 2, "inPlayArea": 4, "inPlayIndex": 0, "index": 2, "type": ATTACH},  # {W} -> Active
        {"area": 2, "inPlayArea": 4, "inPlayIndex": 0, "index": 8, "type": ATTACH},  # Ignition -> Active
        {"attackId": 1487, "type": ATTACK},                                          # Jetting, no KO
        {"type": RETREAT},
        {"type": END},
    ]
    obs["select"] = {"context": 0, "type": 0, "minCount": 1, "maxCount": 1, "option": opts,
                     "deck": None, "contextCard": None, "effect": None,
                     "remainDamageCounter": 0, "remainEnergyCost": 0}
    pilot = _shipped_pilot()
    decision = pilot.explain(obs)
    # `planned.goal` is `"compose"` on every composed frame (Issue #386), so the label distinguishes
    # nothing and the ruled ACTION is asserted directly instead.
    assert decision.planned is not None
    assert decision.chosen == [1]                               # Wally's FIRST
    assert decision.options[5].tactical >= 1000                 # the Ignition attach-KO queued behind it


@pytest.mark.req("REQ-PILOT-0027")
def test_e1db_refutation_proof_the_heal_would_forfeit_a_certain_three_prize_ko():
    """REFUTATION EVIDENCE: at f47 the manual attach is ALREADY SPENT, so Wally's bounce would strip
    all 4 Energy with no re-attach and forfeit a certain 3-prize KO."""
    fx = _fixture("pilot_e1db")
    assert fx["obs"]["current"]["energyAttached"] is True       # the attach is spent at f47
    pilot = _shipped_pilot()
    decision = pilot.explain(fx["obs"])
    nebula = 5                                                  # Attack 1488 = Nebula Beam, 210 ≥ 140
    assert decision.options[nebula].tactical >= 1000            # a certain 3-prize KO is on the menu
    chosen = decision.chosen[0]
    assert decision.options[chosen].card_id != 1229             # and the pick is never the heal
