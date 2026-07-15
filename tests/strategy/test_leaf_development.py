"""Turn Planner leaf — the ``_board_development`` enrichment (develop-rung Phase 0, the locked
bottleneck: ``docs/plans/turn-planner-develop-rung.md``).

The engine-rank leaf splits prize-EQUAL end-of-turn boards toward the stronger one. The original
term was body-count + attached-Energy only (role-blind), so a line that builds the win-condition and
a line that builds junk scored identically. These tracers pin the enrichment: at equal material the
board that advances the WIN-CONDITION line — and that puts Energy on the RIGHT body — must rank
higher, so a rollout on this leaf prefers the human's setup over greedy's.

Seam: ``Pilot._board_development(me)`` — pure over the simmed end-of-turn ``me`` dict + the fixed
``Strategy`` (via ``_wincon_set``). No engine.
"""
import pytest

from common.cards import CardFunctions
from common.pilot import Pilot
from common.scouting.provider import CardStat, DictCardStatProvider
from common.strategy import Strategy
from common.strategy.general_strategy import GENERAL_STRATEGY

WINCON = 900   # carries the primary_attacker Role -> in _wincon_set()
JUNK = 800     # a roleless filler basic


def _pilot():
    stats = DictCardStatProvider({
        WINCON: CardStat(WINCON, name="wincon", hp=200, energyType=3),
        JUNK: CardStat(JUNK, name="junk", hp=60, energyType=3),
    })
    return Pilot(Strategy(roles={WINCON: ["primary_attacker"]}), deck=[1] * 60,
                 general_strategy=GENERAL_STRATEGY, stats=stats, functions=CardFunctions({}))


def _body(cid, energy=0):
    return {"id": cid, "energies": [3] * energy}


@pytest.mark.req("REQ-PLANNER-0011")
def test_wincon_body_outdevelops_an_equal_junk_board():
    """Equal material (2 bodies, 2 total Energy on both boards); one board's Active IS the
    win-condition, the other is all junk. The win-condition board must develop strictly higher, so a
    prize-equal rollout prefers the line that builds toward the win."""
    p = _pilot()
    wincon_me = {"active": [_body(WINCON, 1)], "bench": [_body(JUNK, 1)]}
    junk_me = {"active": [_body(JUNK, 1)], "bench": [_body(JUNK, 1)]}
    assert p._board_development(wincon_me) > p._board_development(junk_me)


@pytest.mark.req("REQ-PLANNER-0011")
def test_energy_on_the_wincon_body_outdevelops_energy_on_junk():
    """Identical bodies (one win-condition + one junk) and identical TOTAL Energy (2), but one board
    stacks it on the WIN-CONDITION body and the other wastes it on junk. Energy on the right body
    must develop strictly higher — a rollout prefers concentrating Energy on the wincon line."""
    p = _pilot()
    on_wincon = {"active": [_body(WINCON, 2)], "bench": [_body(JUNK, 0)]}
    on_junk = {"active": [_body(WINCON, 0)], "bench": [_body(JUNK, 2)]}
    assert p._board_development(on_wincon) > p._board_development(on_junk)
