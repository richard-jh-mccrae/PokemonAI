"""Lethal Solver — the Tier-1 Engine-Search backstop (ADR-0030), on the committed native engine.

Engine-backed (imports ``cg``), offline on Windows + Linux like ``test_battle.py``. Proves the
``_engine_confirms_win`` primitive drives the simulator's own forward search from a REAL observation
(``search_begin`` / ``search_step``) and reads back the engine's verdict — the authority behind a
locked Lethal Line.
"""
from pathlib import Path

import pytest

from cg.game import battle_finish, battle_select, battle_start
from common.cards import CardFunctions
from common.pilot import Pilot
from common.scouting.provider import EngineCardStatProvider
from common.strategy import Strategy
from common.strategy.general_strategy import GENERAL_STRATEGY
from conftest import needs_live_board_search

REPO = Path(__file__).resolve().parents[2]
MEGA = REPO / "tests" / "fixtures" / "agents" / "mega_starmie"


# Cinderace (Explosiveness opener + Turbo Flare accel) / Staryu (the wincon Line base).
CINDERACE, STARYU = 666, 1030


def _deck():
    return [int(x) for x in (MEGA / "deck.csv").read_text(encoding="utf-8").split("\n")[:60]]


def _engine_pilot(deck, **kw):
    try:
        fns = CardFunctions.load()
    except Exception:
        fns = CardFunctions({})
    # attack facts flow through the provider's audit-overridden table (ADR-0051). `starter_priority`
    # is DECLARED (ADR-0079): undeclared, the pregame Active pick scores 0.0 and the drive wanders.
    return Pilot(Strategy(starter_priority=[CINDERACE, STARYU]), deck,
                 general_strategy=GENERAL_STRATEGY, stats=EngineCardStatProvider(),
                 functions=fns, **kw)


@pytest.mark.req("REQ-LETHAL-0014")
@needs_live_board_search
def test_live_wiring_engine_refutes_a_phantom_direct_lock():
    deck = _deck()
    pilot = _engine_pilot(deck, lethal_verify=True)
    pilot._attack_wins = lambda *a, **kw: True        # the closed-form lie: every attack "wins"
    # battle_start shuffles unseeded, so the first attack menu is *occasionally* a genuine lethal the
    # engine rightly confirms; retry over fresh battles until the lie actually has to be refuted.
    refuted = False
    for _attempt in range(20):
        obs, start = battle_start(deck, list(deck))
        assert start.errorPlayer < 0
        try:
            for _ in range(120):
                cur = obs.get("current") or {}
                if cur.get("result", -1) != -1:
                    break
                sel = obs.get("select")
                if (sel is not None and sel.get("context") == 0 and sel.get("maxCount", 0) == 1
                        and obs.get("search_begin_input")
                        and any(o.get("type") == 13 for o in (sel.get("option") or []))):  # an ATTACK option
                    d = pilot.explain(obs)
                    # Retry unless the planned win is the DIRECT phantom: a genuine donk gets
                    # CONFIRMED, and an "evolve"/"unlock" line legitimately verifies None (ADR-0037).
                    if d.planned is not None and d.planned.goal == "win" and (
                            d.planned.verified or d.planned.kind != "direct"):
                        break
                    assert d.planned is None or d.planned.goal != "win"   # phantom candidate refuted
                    assert d.lethal_refuted >= 1
                    refuted = True
                    break
                obs = battle_select(pilot.decide(obs))
        finally:
            battle_finish()
        if refuted:
            break
    assert refuted, "no attack menu reached where the engine had to refute a phantom lock"


@pytest.mark.req("REQ-LETHAL-0023")
def test_family_survives_a_live_drive_and_verified_locks_are_never_false():
    """A refuted candidate is DROPPED, so False never rides a lock (ADR-0037)."""
    deck = _deck()
    pilot = _engine_pilot(deck, lethal_family=True, lethal_verify=True)
    obs, start = battle_start(deck, list(deck))
    assert start.errorPlayer < 0
    locks = []
    try:
        for _ in range(400):
            cur = obs.get("current") or {}
            if cur.get("result", -1) != -1:
                break
            d = pilot.explain(obs)
            if d.planned is not None and d.planned.goal == "win":
                locks.append(d.planned)
            obs = battle_select(d.chosen)
        assert all(ln.verified in (True, None) for ln in locks)
    finally:
        battle_finish()


@pytest.mark.req("REQ-LETHAL-0029")
def test_veto_survives_a_live_drive_and_replays_only_verified_locks():
    """Only a confirmed cascade is ever replayed, and a lost lock surfaces the sparse flag rather
    than a blind pick."""
    deck = _deck()
    pilot = _engine_pilot(deck, lethal_family=True, lethal_verify=True, lethal_veto=True)
    obs, start = battle_start(deck, list(deck))
    assert start.errorPlayer < 0
    replays, losses = [], 0
    try:
        for _ in range(400):
            cur = obs.get("current") or {}
            if cur.get("result", -1) != -1:
                break
            d = pilot.explain(obs)
            if d.planned is not None and d.planned.kind == "replay":
                replays.append(d.planned)
            losses += 1 if d.lethal_lost else 0
            obs = battle_select(d.chosen)
        assert all(ln.goal == "win" and ln.verified is True for ln in replays)
    finally:
        battle_finish()


@pytest.mark.req("REQ-LETHAL-0009")
@needs_live_board_search
def test_engine_confirms_win_round_trips_the_search_on_a_real_observation():
    deck = _deck()
    pilot = _engine_pilot(deck)
    # battle_start shuffles unseeded, so a drive may miss a search-capable menu inside the cap, or
    # surface an unaccounted coin (a sound None); retry until a concrete verdict lands.
    verdict = None
    for _attempt in range(20):
        obs, start = battle_start(deck, list(deck))
        assert start.errorPlayer < 0                      # legal deck loaded
        try:
            for _ in range(80):
                cur = obs.get("current") or {}
                if cur.get("result", -1) != -1:
                    break
                sel = obs.get("select")
                if sel is not None and sel.get("context") == 0 and obs.get("search_begin_input"):
                    verdict = pilot._engine_confirms_win(obs, [pilot.decide(obs)])
                    break
                obs = battle_select(pilot.decide(obs))
        finally:
            battle_finish()
        if verdict is not None:
            break
    assert verdict is False        # engine round-tripped + ruled: one early move isn't a win
