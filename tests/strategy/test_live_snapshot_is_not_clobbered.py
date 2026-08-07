"""The per-decision `_state_model` must survive the composer running (POC-T4/5, Issue #386).

`_snapshot` builds AND STASHES the model onto `self._state_model`, and `_board_hypothetical` reaches
it deliberately — but a speculative build DURING a live decision leaves every later reader in that
`explain()` scoring a hypothetical end-of-turn board. The guard is written against that SYMPTOM
(identity of the stashed model across a decision), because the leak is general.
"""
import pytest

from common.pilot import Pilot
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy import Strategy
from common.strategy.general_strategy import GENERAL_STRATEGY
from pilot_helpers import ACTIVE, ATTACH, MAIN, attack_opt, make_select, opt, poke, state

MEGA, W_ENERGY, OPP = 1031, 3, 800
JETTING = 11


def _pilot():
    stats = DictCardStatProvider(
        {MEGA: CardStat(MEGA, synthetic=True, energyType=3, hp=330, megaEx=True,
                        maxDamage=210, maxDamageCost=3, minAttackCost=1, attacks=(JETTING,)),
         W_ENERGY: CardStat(W_ENERGY, synthetic=True, energyType=3, hp=0),
         OPP: CardStat(OPP, synthetic=True, energyType=2, hp=200)},
        attacks={JETTING: AttackStat(JETTING, damage=120, cost=1)})
    return Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)


def _obs():
    return make_select(
        [opt(ATTACH, area=2, index=0, inPlayArea=4, inPlayIndex=0), attack_opt(JETTING)],
        context=MAIN,
        current=state(active=poke(MEGA, energy=1, hp=330), opp_active=poke(OPP, hp=200),
                      hand=[W_ENERGY], turn=6))


@pytest.mark.req("REQ-PLANNER-0012")
def test_the_live_state_model_survives_a_decision_that_ran_the_composer():
    """Asserted by OBJECT IDENTITY: comparing `prizes_remaining` and body counts passes with the fix
    disabled, because a hypothetical end-of-turn board of the same game matches on both."""
    pilot = _pilot()
    obs = _obs()
    built = []
    orig = type(pilot)._snapshot
    type(pilot)._snapshot = lambda self, *a, **kw: built.append(orig(self, *a, **kw)) or built[-1]
    try:
        pilot.explain(obs)
    finally:
        type(pilot)._snapshot = orig

    assert len(built) > 1, (
        "only one snapshot was built, so this decision never ran a speculative build and the test "
        "is not exercising the leak it exists for")
    assert pilot._state_model is built[0], (
        "the stashed model is not the LIVE one built for this decision — a speculative build leaked "
        "into `self._state_model`, and every reader after `plan_turn` scored the wrong board")


@pytest.mark.req("REQ-PLANNER-0012")
def test_the_hypothetical_build_still_stashes_for_callers_that_want_it():
    """The restore lives in `_leaf_needs_resolution`, NOT in `_board_hypothetical`: callers that
    evaluate a rung against a hypothetical board depend on the stash (`test_hand_size_relief.py`)."""
    pilot = _pilot()
    obs = _obs()
    pilot._board(obs, obs.get("select"))
    live = pilot._state_model

    hypo_obs = {**obs, "current": {**obs["current"], "turn": 9}}
    pilot._board_hypothetical(hypo_obs)
    assert pilot._state_model is not live, (
        "`_board_hypothetical` no longer stashes — callers that evaluate against the hypothetical "
        "board read `self._state_model` and would silently score the wrong one")
