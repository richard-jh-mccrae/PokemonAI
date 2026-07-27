"""BASELINE cluster: RETREAT — the setup-retreat reluctance, now EMERGENT (ADR-0073 §11, #141).

`hold-position-in-setup` (−25) is DELETED. ADR-0073 rules it emergent: a setup retreat pays real
`retreat_cost` to promote a body that is not yet worth promoting, so the equation should decline it
without a rung saying so.

**This is flagged in ADR-0073 as the WEAKEST claim in the ruling** — the one deletion made on an
emergence argument with *no worked frame behind it*, and the one most likely to come back as a ruled
flip. That is exactly why it is pinned here rather than simply deleted with its rung: this test is
the worked frame the ADR lacked, and it fails loudly if the emergence stops holding. (The corpus
sweep agrees: zero regressions, and six of its twelve FIX frames are "stop retreating for nothing".)

Verified through the Pilot's PUBLIC interface (`explain`/`decide`), asserting the DECISION rather
than a rung firing — ADR-0072's rewrite of f29 from a score claim to a decision claim is the prior
art. Lib-free: observation dicts built by hand via `pilot_helpers` (no native engine).
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
    stats = DictCardStatProvider({ACTIVE_ID: CardStat(ACTIVE_ID, hp=90, minAttackCost=1),
                                  BENCH_ID: CardStat(BENCH_ID, hp=70, minAttackCost=1)})
    return Pilot(strategy or Strategy(), deck=[], general_strategy=GENERAL_STRATEGY, stats=stats)


def _setup_obs():
    return make_select([opt(RETREAT), opt(END)], context=MAIN,
                       current=state(active=poke(ACTIVE_ID, energy=1), bench=[poke(BENCH_ID)]))


@pytest.mark.req("REQ-GEN-0026")
def test_the_setup_retreat_is_declined_without_a_rung_saying_so():
    """During setup, retreating spends the turn's tempo for no payoff. The destination earns no
    `my_yield` (a bare bench body reaches no damage) while promoting it still costs prize Exposure,
    so the retreat option prices NEGATIVE and End wins — the emergence claim, made falsifiable."""
    p = _pilot()   # no Lines -> choose_plan returns SETUP
    trace = p.explain(_setup_obs())
    retreat = trace.options[0].promote_retreat_working
    assert retreat is not None and retreat["site"] == "whether"
    assert retreat["my_yield"] == 0.0                  # nothing on the Bench is worth bringing up
    assert trace.options[0].score < 0                  # …so the pivot is priced as a loss
    assert p.decide(_setup_obs()) == [1]               # End, not Retreat


@pytest.mark.req("REQ-GEN-0026")
def test_the_reluctance_is_a_price_not_a_veto():
    """The deleted rung was a flat −25 brake gated on the Plan being SETUP. The equation charges the
    actual cost instead, so nothing structurally suppresses a retreat during setup — which is what
    lets `retreat-to-wall-the-line` (the surviving #165 Maneuver) still fire on the same board
    without needing the stand-down clause the rung had to carry."""
    strat = Strategy(lines=[Line(path=[ACTIVE_ID], payoff=ACTIVE_ID, ready=Ready(energy=1))])
    p = _pilot(strat)
    fired = {h.id for h, _ in p.explain(_setup_obs()).options[0].fired}
    assert "hold-position-in-setup" not in fired       # the rung is gone, in both Plans
