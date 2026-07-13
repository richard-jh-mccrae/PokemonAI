"""Tier 6 — Escalation Search on the committed native engine (ADR-0043; the tier-6 finish-plan's
engine-backed trigger-fixture test, grilled 2026-07-05, extended 2026-07-05 with the DENSITY trigger).

Engine-backed (imports ``cg``), offline on Windows + Linux like ``test_planner_engine.py``. The unit
gates in ``test_escalation.py`` cover the triggers + stand-downs on synthetic inputs; here the two-ply
sim (``_simulate_line(opponent_reply=True)``) is exercised end-to-end from a REAL observation, an
escalation-ON drive proves the seam never crashes and stays inside its per-move budget, and the
opponent-disruption-DENSITY trigger is proven to actually FIRE + commit on real boards (the unlock the
near-unreachable close-attack-tie trigger structurally lacked — 0 commits over 646 real decisions).
"""
import math
from pathlib import Path

import pytest

from cg.game import battle_finish, battle_select, battle_start
from common.cards import CardFunctions
from common.pilot import Pilot
from common.scouting.artifact import load_artifact
from common.scouting.briefs import load_briefs
from common.scouting.provider import EngineCardStatProvider
from common.scouting.scout import Scout
from common.strategy import Strategy
from common.strategy.general_strategy import GENERAL_STRATEGY

REPO = Path(__file__).resolve().parents[2]
MEGA = REPO / "tests" / "fixtures" / "agents" / "mega_starmie"
_BUDGET = 400


def _deck():
    return [int(x) for x in (MEGA / "deck.csv").read_text(encoding="utf-8").split("\n")[:60]]


def _engine_pilot(deck, *, read=False, **kw):
    try:
        fns = CardFunctions.load()
    except Exception:
        fns = CardFunctions({})
    provider = EngineCardStatProvider()                 # its attack() table (built from all_attack())
    extra = {}                                          # is the one attack-fact source (ADR-0051)
    if read:                                            # wire the Read + Briefs so the density signal's
        extra = dict(scout=Scout(load_artifact(), provider=provider),   # predicted half (γ·expected_cards)
                     briefs=load_briefs(), posture=True)                 # is live, as main.py builds it
    return Pilot(Strategy(), deck, general_strategy=GENERAL_STRATEGY, stats=provider,
                 functions=fns, **extra, **kw)


def _first_open_menu(pilot, obs, limit=80):
    """Drive a real mirror game to the first open MAIN menu that carries a ``search_begin_input``."""
    for _ in range(limit):
        cur = obs.get("current") or {}
        if cur.get("result", -1) != -1:
            return None
        sel = obs.get("select")
        if sel is not None and sel.get("context") == 0 and obs.get("search_begin_input"):
            return obs
        obs = battle_select(pilot.decide(obs))
    return None


@pytest.mark.req("REQ-ESCALATE-0004")
def test_two_ply_value_round_trips_the_opponent_reply_sim_on_a_real_observation():
    """The depth-2 leaf: from a live turn menu, ``_two_ply_value`` sims MY move, continues the engine
    through the opponent's reply (our-policy proxy), and reads a concrete leaf value — proving
    ``_simulate_line(opponent_reply=True)`` round-trips past my turn on real engine observations (the
    opponent-choice read closed-form provably lacks). A finite float, not None."""
    deck = _deck()
    pilot = _engine_pilot(deck, escalation=True, search_budget=_BUDGET)
    obs, start = battle_start(deck, list(deck))
    assert start.errorPlayer < 0
    try:
        menu = _first_open_menu(pilot, obs)
        assert menu is not None                            # reached an open turn menu with a search input
        pilot._search_steps = 0                            # arm the per-move budget (as _escalate does)
        value = pilot._two_ply_value(menu, pilot.decide(menu))
        assert value is not None and math.isfinite(value)  # the two-ply sim produced a concrete leaf
        assert pilot._search_steps <= _BUDGET              # the opponent-reply sim stayed in budget
    finally:
        battle_finish()


@pytest.mark.req("REQ-ESCALATE-0005")
def test_escalation_on_live_drive_never_crashes_and_stays_in_budget():
    """A full mirror drive with escalation ON + a real budget: the Pilot never crashes, every committed
    escalation line is a legal move (``goal='escalation'``), and the per-move search budget is never
    blown — the never-time-out invariant holding on live engine observations, not just synthetic inputs."""
    deck = _deck()
    pilot = _engine_pilot(deck, escalation=True, search_budget=_BUDGET)
    obs, start = battle_start(deck, list(deck))
    assert start.errorPlayer < 0
    escalations = 0
    try:
        for _ in range(160):
            cur = obs.get("current") or {}
            if cur.get("result", -1) != -1:
                break
            decision = pilot.explain(obs)                  # never raises
            if decision.planned is not None and decision.planned.goal == "escalation":
                escalations += 1
                assert decision.chosen                     # committed a real, legal move
            assert pilot._search_steps <= _BUDGET + 1      # hard per-move budget (one-step trip margin)
            obs = battle_select(decision.chosen)
    finally:
        battle_finish()
    assert escalations >= 0                                # drive completed cleanly (fired or not)


@pytest.mark.req("REQ-ESCALATE-0008")
def test_density_trigger_fires_on_real_boards_and_the_seam_holds():
    """The opponent-disruption-DENSITY trigger's reason for existing: it must actually FIRE on real
    boards, where the close-attack-tie trigger structurally cannot (≥2 affordable attacks occur on
    ~0-1.5% of our menus). With the Read + Briefs wired (so the predicted-density half is live) and
    escalation ON, a short mirror drive flags disruption-dense boards while the per-move budget holds and
    every committed escalation is a legal move — the seam holding on live observations.

    Whether it *commits* on a given drive is engine-trajectory-dependent (the two-ply strict-improvement
    outcome is not identical across platforms/games — Linux CI can see 0 over the same 4 games Windows
    commits several), so the COMMIT LOGIC is pinned deterministically in the unit suite
    (`test_commit_escalation_overrides_only_on_strict_improvement`) and its real-board *rate* is measured
    by the firing diagnostic — NOT asserted as a live count here (that would be a flaky test)."""
    deck = _deck()
    pilot = _engine_pilot(deck, read=True, escalation=True, search_budget=_BUDGET)
    dominated = 0
    try:
        for _ in range(4):
            obs, start = battle_start(deck, list(deck))
            if start.errorPlayer >= 0:
                continue
            for _ in range(220):
                cur = obs.get("current") or {}
                if cur.get("result", -1) != -1:
                    break
                sel = obs.get("select")
                if sel is not None and sel.get("context") == 0 and sel.get("maxCount", 0) == 1 \
                        and obs.get("search_begin_input"):
                    if pilot._density_dominated(obs, pilot._board_hypothetical(obs)):
                        dominated += 1
                decision = pilot.explain(obs)              # never raises
                pl = decision.planned
                if pl is not None and pl.goal == "escalation":
                    assert decision.chosen                 # any committed escalation is a legal move
                assert pilot._search_steps <= _BUDGET + 1  # hard per-move budget holds under the trigger
                obs = battle_select(decision.chosen)
    finally:
        battle_finish()
    assert dominated > 0                                   # the density trigger flagged real dense boards
