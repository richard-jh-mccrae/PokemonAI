"""BASELINE cluster: RETREAT — the setup-retreat reluctance, now EMERGENT (ADR-0100 §11).

`hold-position-in-setup` (-25) is DELETED. ADR-0100 flags this as the WEAKEST claim in that ruling —
the one deletion made on emergence with no worked frame behind it — so this file IS that frame and
fails loudly if the emergence stops holding.
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


def _pilot(strategy=None):
    stats = DictCardStatProvider({ACTIVE_ID: CardStat(ACTIVE_ID, synthetic=True, hp=90, minAttackCost=1),
                                  BENCH_ID: CardStat(BENCH_ID, synthetic=True, hp=70, minAttackCost=1)})
    return Pilot(strategy or Strategy(), deck=[], general_strategy=GENERAL_STRATEGY, stats=stats)


def _setup_obs():
    return make_select([opt(RETREAT), opt(END)], context=MAIN,
                       current=state(active=poke(ACTIVE_ID, energy=1), bench=[poke(BENCH_ID)]))


@pytest.mark.req("REQ-GEN-0026")
def test_the_setup_retreat_is_declined_without_a_rung_saying_so():
    """A bare bench body earns no `my_yield` while promoting it still costs prize Exposure."""
    p = _pilot()   # no Lines -> choose_plan returns SETUP
    trace = p.explain(_setup_obs())
    retreat = trace.options[0].promote_retreat_working
    assert retreat is not None and retreat["site"] == "whether"
    assert retreat["my_yield"] == 0.0
    assert trace.options[0].score < 0
    assert p.decide(_setup_obs()) == [1]               # End, not Retreat


@pytest.mark.req("REQ-GEN-0026")
def test_the_reluctance_is_a_price_not_a_veto():
    """Nothing structurally suppresses a setup retreat — the equation charges its actual cost."""
    strat = Strategy(lines=[Line(path=[ACTIVE_ID], payoff=ACTIVE_ID, ready=Ready(energy=1))])
    p = _pilot(strat)
    fired = {h.id for h, _ in p.explain(_setup_obs()).options[0].fired}
    assert "hold-position-in-setup" not in fired       # the rung is gone, in both Plans
