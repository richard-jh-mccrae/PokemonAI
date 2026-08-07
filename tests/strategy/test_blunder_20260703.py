"""Blunder round 2026-07-03 (mega_starmie) — real-replay regression gates (/blunder-buster).

Each test replays a captured CRITICAL correction state through the SHIPPED Pilot (the exact
`tune._build_pilot` construction) and pins the fix. The planner-layer sisters of this round
(a212 evolution-tutor line, 6858 heal-before-attach) gate in `test_planner_engine.py`; here live
the Pilot-sequencing ones.
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
    """CRITICAL eb98 ('we had opportunity to KO their main attacker for 3 prize points but we instead
    gusted up their 1 prize point pre-evolution'): on the ACTUAL captured state, Nebula Beam (210 ≥ 190,
    3 prizes) was on the menu, but Boss's Orders sequenced ahead of it as an 'informative Supporter'
    and the gust swapped the defender — forfeiting the KO. The gust now drops behind a menu KO
    (`_finish_turn_last`); the agent may still take an endorsed NON-defender-changing dev first
    (attack-last, ep83037962), so the gate pins 'never the gust', not one exact dev order."""
    fx = _fixture("pilot_eb98")
    pilot = _shipped_pilot()
    decision = pilot.explain(fx["obs"])
    assert decision.chosen != fx["chosen"]                      # the gust pick is gone
    gust_opt = fx["chosen"][0]
    assert gust_opt not in decision.chosen
    nebula = fx["correct"][0]
    assert decision.options[nebula].tactical >= 1000            # the 3-prize KO is seen on the menu


@pytest.mark.req("REQ-GUST-0012")
@pytest.mark.xfail(strict=True, reason=marks("pilot_6f14")[0].kwargs["reason"])
def test_critical_6f14_harlequin_beats_the_unpayable_gust_on_its_real_replay_state():
    """CRITICAL 6f14 ('we need energy here and we need to disrupt opponent … then play Harlequin'):
    on the ACTUAL captured state my Mega Starmie had 0 Energy and the hand held none — no attack was
    payable this turn, yet `gust-for-the-ko` endorsed Boss's Orders (+50) over the hand-refresh the
    dead hand needed. The whether-to-play signal now gates on payable Energy, so the phantom gust is
    silent and Harlequin — the human's ``correct`` disruption/refresh — wins the Supporter slot."""
    fx = _fixture("pilot_6f14")
    pilot = _shipped_pilot()
    decision = pilot.explain(fx["obs"])
    assert decision.chosen == fx["correct"]                     # Harlequin, as the human marked
    boss = fx["chosen"][0]
    # The rung-id assertion that stood here is DELETED with its rung (POC-T4/5, Issue #386).
    # Not merely stale — it gave this test's strict xfail a SECOND cause. The recorded reason
    # is a seam-coverage gap; whoever closes that gap would have found the test still red on a
    # dead rung name and concluded the fix did not work. One xfail, one cause.


@pytest.mark.req("REQ-GEN-0066")
def test_critical_b323_dead_recycle_is_held_on_its_real_replay_state():
    """CRITICAL b323 ('Cinderace shall never be recycled with Night Stretcher — it can never be
    played outside of match setup'): on the ACTUAL captured state, the discard's only recycle pool
    was the setup-only Explosiveness Cinderace (no Basic Energy), yet Night Stretcher won a 0-0 tie
    over End turn. `dont-recycle-the-dead` (Verifier-passed) now drops the dead recycle below End."""
    fx = _fixture("pilot_b323")
    pilot = _shipped_pilot()
    decision = pilot.explain(fx["obs"])
    assert decision.chosen == fx["correct"]                     # End turn, as the human marked
    ns = fx["chosen"][0]
    assert any(h.id == "dont-recycle-the-dead" for h, _ in decision.options[ns].fired)


@pytest.mark.req("REQ-GUST-0013")
@pytest.mark.xfail(strict=True, reason=marks("pilot_cd91")[0].kwargs["reason"])
def test_cd91_starved_stall_gust_wins_the_slot_on_its_real_replay_state():
    """cd91 ('we need to stall … real risk they evolve into Mega Lucario and KO our Cinderace; Boss's
    Orders up Makuhita'): on the ACTUAL captured state, Cinderace faced the Riolu → Mega Lucario line
    with zero Energy anywhere (no attack payable), yet Salvatore's dig stack (98) beat Boss's (0).
    The general forward-evolution doom + the energy-famine stall rule now lift the gust over the
    tutor — the human's ``correct`` pick."""
    fx = _fixture("pilot_cd91")
    pilot = _shipped_pilot()
    decision = pilot.explain(fx["obs"])
    assert decision.chosen == fx["correct"]                     # Boss's Orders, as the human marked
    boss = fx["correct"][0]
    # The rung-id assertion that stood here is DELETED with its rung (POC-T4/5, Issue #386).
    # Not merely stale — it gave this test's strict xfail a SECOND cause. The recorded reason
    # is a seam-coverage gap; whoever closes that gap would have found the test still red on a
    # dead rung name and concluded the fix did not work. One xfail, one cause.


@pytest.mark.req("REQ-GEN-0067")
def test_c4f5_powered_active_pitches_ignition_keeps_lillies_on_its_real_replay_state():
    """c4f5 ('active mega starmie is already fully energized … discard Cinderace and Ignition, then
    play lillie's determination to refill hand'): on the ACTUAL captured Discard-2, the Active Mega
    carried Nebula Beam's full cost, so Ignition's keep-premise is void — the agent now pitches
    [Cinderace, Ignition] and keeps the 8-card refresh."""
    fx = _fixture("pilot_c4f5")
    pilot = _shipped_pilot()
    decision = pilot.explain(fx["obs"])
    assert sorted(decision.chosen) == sorted(fx["correct"])     # [Cinderace, Ignition], as marked


@pytest.mark.req("REQ-PLANNER-0036")
@pytest.mark.xfail(strict=True, reason=(
    "POC-T4/5 flip (Issue #386): this frame is HAND-EDITED from the e1db replay (the Ignition "
    "is put back in hand and `energyAttached` rewound), so it has no fixture file and no row in "
    "`poc_t4_flips.FLIPS` — the ruling is the docstring. The composer plays [5], the Ignition "
    "attach, rather than [1], Wally's Compassion first. Same family as `pilot_e1db`, whose "
    "flip-table row records the cause: the seam has NO board synthesis registered for the "
    "'heal' choice key, so the Wally's line cannot be written at all"))
def test_e1db_intended_sequence_commits_from_the_turn8_pre_attach_state():
    """CRITICAL e1db, resolved per human ack 2026-07-03: the intended line — Wally's Compassion,
    THEN attach Ignition, THEN Nebula Beam for the 3-prize KO — belongs to turn 8's REAL decision
    point, BEFORE the agent spent the attach (by the tagged f47 frame it is unexecutable). Rewinding
    the captured f47 board to that pre-attach state (Ignition back to hand, attach unspent), the
    f35 stabilize-then-KO fix commits Wally's FIRST with the Ignition attach's KO (tac ≥ 1000)
    queued behind it — the human's exact sequence, one fix covering both turns of the episode."""
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
    # The GOAL LABEL is not asserted any more. `planned.goal` was `"stabilize_then_ko"`, one of the
    # named closed-form goals the rung ladder produced; POC-T4/5 (Issue #386) makes it `"compose"`
    # on every frame the sequence search answers, so the label stopped distinguishing anything. What
    # the test is for — the ruled ACTION, and the reason it is ruled — is asserted directly.
    assert decision.planned is not None
    assert decision.chosen == [1]                               # Wally's FIRST
    assert decision.options[5].tactical >= 1000                 # the Ignition attach-KO queued behind it


@pytest.mark.req("REQ-PILOT-0027")
def test_e1db_refutation_proof_the_heal_would_forfeit_a_certain_three_prize_ko():
    """REFUTATION EVIDENCE for e1db (f47, CRITICAL — recorded only on human ack): the correction
    asks for Wally's Compassion, but at f47 the manual attach is ALREADY SPENT
    (`energyAttached=true`) and Nebula Beam's 3-prize KO (210 ≥ 140) is on the menu. Wally's bounce
    would strip all 4 Energy with no re-attach available — healing forfeits a certain 3-prize KO
    (hard-rung invariant / forgo-KO precedent). This test pins the two facts the refutation rests
    on: the KO is real (KO_SCORE-class on the menu) and the agent's turn ends having banked it
    (dev-first is fine; the attack persists — the defender can't change)."""
    fx = _fixture("pilot_e1db")
    assert fx["obs"]["current"]["energyAttached"] is True       # the attach is spent at f47
    pilot = _shipped_pilot()
    decision = pilot.explain(fx["obs"])
    nebula = 5                                                  # Attack 1488 = Nebula Beam, 210 ≥ 140
    assert decision.options[nebula].tactical >= 1000            # a certain 3-prize KO is on the menu
    chosen = decision.chosen[0]
    assert decision.options[chosen].card_id != 1229             # and the pick is never the heal
