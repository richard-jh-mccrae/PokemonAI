"""Turn Planner — the Tier-1 Engine-Search rank (ADR-0031 phase 3), on the committed native engine.

Engine-backed (imports ``cg``), offline on Windows + Linux like ``test_lethal_engine.py``. Proves the
``_simulate_line`` / ``_engine_leaf_value`` primitives drive the simulator's own forward search from a
REAL observation to the end of my turn — stepping a candidate first move, then re-running the Pilot's
policy on each intermediate SearchState — and read a leaf value off the resulting board.
"""
import json
from pathlib import Path

import pytest

from cg.api import all_attack
from cg.game import battle_finish, battle_select, battle_start
from common.cards import CardFunctions
from common.pilot import Pilot
from common.scouting.provider import EngineCardStatProvider
from common.strategy import Strategy
from common.strategy.general_strategy import GENERAL_STRATEGY

REPO = Path(__file__).resolve().parents[2]
MEGA = REPO / "tests" / "fixtures" / "agents" / "mega_starmie"


def _deck():
    return [int(x) for x in (MEGA / "deck.csv").read_text(encoding="utf-8").split("\n")[:60]]


def _engine_pilot(deck):
    atk = all_attack()
    try:
        fns = CardFunctions.load()
    except Exception:
        fns = CardFunctions({})
    return Pilot(Strategy(), deck, general_strategy=GENERAL_STRATEGY, stats=EngineCardStatProvider(),
                 functions=fns, attacks={a.attackId: a.damage for a in atk},
                 attack_costs={a.attackId: len(a.energies) for a in atk})


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


@pytest.mark.req("REQ-PLANNER-0011")
def test_engine_leaf_value_round_trips_the_search_on_a_real_observation():
    """Drive a real mirror game to its first open turn menu, then evaluate the live first move through
    the engine sim: the primitive must return a concrete, non-negative leaf value (not None), proving
    ``search_begin`` → step the move → re-run the policy to end-of-turn round-trips from a live
    observation and the resulting board is read (prizes taken + survival). The engine, not our
    closed-form math, produced the board it scored."""
    deck = _deck()
    pilot = _engine_pilot(deck)
    obs, start = battle_start(deck, list(deck))
    assert start.errorPlayer < 0                           # a legal deck loaded
    try:
        menu = _first_open_menu(pilot, obs)
        assert menu is not None                            # reached an open turn menu with a search input
        value = pilot._engine_leaf_value(menu, pilot.decide(menu))
        assert value is not None                           # the search round-tripped to an end-of-turn board
        assert value >= 0                                  # prizes/survival are non-negative
    finally:
        battle_finish()


@pytest.mark.req("REQ-PLANNER-0012")
def test_simulate_line_reaches_a_board_and_ends_my_turn():
    """``_simulate_line`` returns a real end-of-turn board (not None) and stops on MY side: the returned
    tuple carries my player index and the prize count I started the turn with, and the resulting State
    is either the opponent's turn, a later board, or a finished game — never left mid-decision on my
    turn. Proves the policy-driven stepping terminates cleanly."""
    deck = _deck()
    pilot = _engine_pilot(deck)
    obs, start = battle_start(deck, list(deck))
    assert start.errorPlayer < 0
    try:
        menu = _first_open_menu(pilot, obs)
        assert menu is not None
        sim = pilot._simulate_line(menu, pilot.decide(menu))
        assert sim is not None
        end, my_index, start_prizes, result = sim
        assert my_index in (0, 1) and start_prizes >= 1
        cur = end.get("current") or {}
        # my turn is over: the game finished, or the menu is no longer mine to act on
        assert result != -1 or cur.get("yourIndex") != my_index or cur.get("select") is None \
            or (end.get("select") is None)
    finally:
        battle_finish()


# ---------------------------------------- the CRITICAL that literally asked for a turn planner (7f48)
def _shipped_pilot():
    """The real mega_starmie Pilot, built exactly like ``main.py`` (the canonical retest builder), so a
    replayed correction decides the way the shipped agent would."""
    import sys
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    pilot, _seeds = _build_pilot("mega_starmie")
    return pilot


@pytest.mark.req("REQ-PLANNER-0016")
def test_critical_7f48_is_fixed_on_its_real_replay_state():
    """CRITICAL 7f48 ('another multi decision example showing that we need a turn planner system'): on the
    ACTUAL captured blunder state, the agent played a card ([1]) instead of retreating the spent Cinderace
    into the powered Mega Starmie — the first step of retreat → attach → KO Fezandipiti for 2 prizes. No
    single option scores that KO, so the greedy scorer missed it. Replayed through the shipped Pilot, the
    Turn Planner now commits the ``ko_for_prizes`` line and the agent takes the human's ``correct`` move
    (the retreat). A hard regression gate on the real state, like the Lethal Solver's CRITICALs."""
    fx = json.loads((REPO / "tests" / "fixtures" / "corrections" / "planner_7f48.json").read_text(encoding="utf-8"))
    pilot = _shipped_pilot()
    decision = pilot.explain(fx["obs"])
    assert decision.planned is not None and decision.planned.goal == "ko_for_prizes"   # the Planner acted
    assert "2-prize KO" in decision.planned.rationale                                   # via the multi-step line
    assert decision.chosen == fx["correct"]        # the agent now takes the human's correct move (the retreat)


@pytest.mark.req("REQ-PLANNER-0020")
def test_critical_0cbc_stabilize_then_ko_is_fixed_on_its_real_replay_state():
    """CRITICAL 0cbc: on the ACTUAL captured state, the agent's Mega ex was at 160/330 and could KO the
    opponent's Active (Jetting Blow), but the `active_can_ko` suppressor dropped the heal — so it played
    a filler card ([3]) instead of Wally's Compassion ([5]). Wally heals to full and bounces the Energy;
    one re-attach still affords the KO, so the agent both survives and takes the prize. Replayed through
    the shipped Pilot, the stabilize-then-KO goal commits Wally's — the human's ``correct`` move."""
    fx = json.loads((REPO / "tests" / "fixtures" / "corrections" / "planner_0cbc.json").read_text(encoding="utf-8"))
    pilot = _shipped_pilot()
    decision = pilot.explain(fx["obs"])
    assert decision.planned is not None and decision.planned.goal == "stabilize_then_ko"
    assert decision.chosen == fx["correct"]        # the agent now heals-and-KOs (plays Wally's) as the human marked


@pytest.mark.req("REQ-PLANNER-0023")
def test_critical_4298_supporter_enabled_ko_is_fixed_on_its_real_replay_state():
    """CRITICAL 4298 ('our agent needs to start planning its turn ahead of time … it can KO opponent's
    Active via Hilda for energy grab, attach to Mega Starmie, retreat to Mega Starmie, and Jetting Blow'):
    on the ACTUAL captured state, the agent played Crushing Hammer ([1]) instead of Hilda ([2]). Cinderace
    is Active with no Energy and two benched Mega Starmie ex sit at 0 Energy — no single option scores a
    KO, and the enabling first step is a *Supporter* (Hilda tutors an Energy into hand), which the
    retreat/evolve generator never produced. Replayed through the shipped Pilot, the Turn Planner's
    tutor-energy line commits Hilda — the human's ``correct`` move — so the fetched Energy can then power
    the retreat→Jetting-Blow KO. A hard regression gate on the real state, like 7f48 and 0cbc."""
    fx = json.loads((REPO / "tests" / "fixtures" / "corrections" / "planner_4298.json").read_text(encoding="utf-8"))
    pilot = _shipped_pilot()
    decision = pilot.explain(fx["obs"])
    assert decision.planned is not None and decision.planned.goal == "ko_for_prizes"   # the Planner acted
    assert "energy tutor" in decision.planned.rationale                                # via the Supporter line
    assert decision.chosen == fx["correct"]        # the agent now plays Hilda (the energy grab) as the human marked
