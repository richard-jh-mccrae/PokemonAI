"""BASELINE cluster: RETREAT — `hold-position-in-setup` (don't retreat away during SETUP).

Verified through the Pilot's PUBLIC interface (`explain`): the reluctance fires on a Retreat option at
the open turn menu while the Plan is SETUP, and stands down once a win-condition is online (RACE).
Lib-free: observation dicts built by hand via `pilot_helpers` (no native engine). Closes the behavioral
coverage gap flagged by the 2026-06-29 refactor audit (only structural roster coverage existed before).
"""
import pytest

from common.strategy.general_strategy import GENERAL_STRATEGY
from common.pilot import Pilot
from common.scouting.provider import CardStat, DictCardStatProvider
from common.strategy import Line, Ready, Strategy
from pilot_helpers import MAIN, make_select, opt, poke, state

RETREAT = 12   # OptionType.RETREAT — swap the Active out (cg/api.py)
END = 14       # OptionType.END
ACTIVE_ID, BENCH_ID = 900, 901


def _fired(o):
    return {h.id for h, _ in o.fired}


def _pilot(strategy=None):
    stats = DictCardStatProvider({ACTIVE_ID: CardStat(ACTIVE_ID, hp=90, minAttackCost=1),
                                  BENCH_ID: CardStat(BENCH_ID, hp=70, minAttackCost=1)})
    return Pilot(strategy or Strategy(), deck=[], general_strategy=GENERAL_STRATEGY, stats=stats)


@pytest.mark.req("REQ-GEN-0026")
def test_hold_position_in_setup_fires_on_a_retreat_at_the_setup_turn_menu():
    """During SETUP, retreating spends the turn's tempo for no payoff — the reluctance fires (negative)
    on the Retreat option so the agent develops the board instead, and stays silent on End (not a retreat)."""
    p = _pilot()   # no Lines -> choose_plan returns SETUP
    obs = make_select([opt(RETREAT), opt(END)], context=MAIN,
                      current=state(active=poke(ACTIVE_ID, energy=1), bench=[poke(BENCH_ID)]))
    trace = p.explain(obs)
    assert "hold-position-in-setup" in _fired(trace.options[0])       # the Retreat option
    assert trace.options[0].score < 0                                 # a reluctance (negative weight)
    assert "hold-position-in-setup" not in _fired(trace.options[1])   # the End option — not a retreat


@pytest.mark.req("REQ-GEN-0026")
def test_hold_position_in_setup_silent_once_a_wincon_is_online():
    """Once a Line's payoff is online (Plan RACE), the SETUP reluctance stands down — retreating to a
    ready attacker is a legitimate RACE move, not something this rule should discourage."""
    strat = Strategy(lines=[Line(path=[ACTIVE_ID], payoff=ACTIVE_ID, ready=Ready(energy=1))])
    p = _pilot(strat)   # payoff Active online at 1 energy -> choose_plan returns RACE
    obs = make_select([opt(RETREAT), opt(END)], context=MAIN,
                      current=state(active=poke(ACTIVE_ID, energy=1), bench=[poke(BENCH_ID)]))
    assert "hold-position-in-setup" not in _fired(p.explain(obs).options[0])
