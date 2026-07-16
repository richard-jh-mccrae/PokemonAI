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
PLAN = 850     # carries an engine Role -> a game-plan piece below the payoff (_development_plan_set)
JUNK = 800     # a roleless filler basic -> off-plan (base credit only)


def _pilot(roles=None):
    stats = DictCardStatProvider({
        WINCON: CardStat(WINCON, name="wincon", hp=200, energyType=3),
        PLAN: CardStat(PLAN, name="plan", hp=90, energyType=3),
        JUNK: CardStat(JUNK, name="junk", hp=60, energyType=3),
    })
    roles = roles if roles is not None else {WINCON: ["primary_attacker"], PLAN: ["engine"]}
    return Pilot(Strategy(roles=roles), deck=[1] * 60,
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


@pytest.mark.req("REQ-PLANNER-0011")
def test_plan_piece_body_outdevelops_an_offplan_body():
    """A game-plan piece below the payoff (an ``engine`` Role) must develop strictly higher than a
    role-less off-plan body — the wincon tier alone is INERT during setup (the payoff isn't in play
    yet), so the plan tier is what tells a wincon-line setup board from one that feeds an opener
    (develop-rung Phase 0, ep86090147 "Poké Pad" / ep83661652 f33 "dont feed Meowth ex")."""
    p = _pilot()
    plan_me = {"active": [_body(PLAN, 0)], "bench": [_body(JUNK, 0)]}
    junk_me = {"active": [_body(JUNK, 0)], "bench": [_body(JUNK, 0)]}
    assert p._board_development(plan_me) > p._board_development(junk_me)


@pytest.mark.req("REQ-PLANNER-0011")
def test_payoff_still_outdevelops_a_plan_piece():
    """Soundness ordering: the payoff (win-condition) must develop strictly ABOVE a plan piece at equal
    material, so the leaf never prefers HOLDING a pre-evo over EVOLVING to the payoff (payoff tier 10 >
    plan tier 5). Without this the plan credit would invert the win — ep85785606 f19/f21."""
    p = _pilot()
    payoff_me = {"active": [_body(WINCON, 1)], "bench": [_body(JUNK, 0)]}
    plan_me = {"active": [_body(PLAN, 1)], "bench": [_body(JUNK, 0)]}
    assert p._board_development(payoff_me) > p._board_development(plan_me)


@pytest.mark.req("REQ-PLANNER-0011")
def test_energy_on_plan_piece_outdevelops_energy_on_offplan():
    """Identical bodies (one plan piece + one junk) and identical TOTAL Energy (2), but one board stacks
    it on the game-plan body and the other strands it on an off-plan opener. Energy on the plan piece
    must develop strictly higher — ep83661652 f33 "dont feed Meowth ex"."""
    p = _pilot()
    on_plan = {"active": [_body(PLAN, 2)], "bench": [_body(JUNK, 0)]}
    on_junk = {"active": [_body(PLAN, 0)], "bench": [_body(JUNK, 2)]}
    assert p._board_development(on_plan) > p._board_development(on_junk)


@pytest.mark.req("REQ-PLANNER-0011")
def test_no_declared_roles_collapses_to_payoff_only():
    """A deck that declares NO roles/lines yields an empty plan set, so the credit degrades exactly to
    the old payoff-only (+base) behaviour — no regression for un-annotated decks. Two equal all-junk
    boards develop identically; a bare pilot never raises on the plan-set lookup."""
    p = _pilot(roles={})
    assert p._development_plan_set() == set()
    a = {"active": [_body(JUNK, 1)], "bench": [_body(JUNK, 0)]}
    b = {"active": [_body(JUNK, 0)], "bench": [_body(JUNK, 1)]}
    assert p._board_development(a) == p._board_development(b) == (10.0 + 5.0) + 10.0
