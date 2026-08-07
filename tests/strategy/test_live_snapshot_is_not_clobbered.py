"""The per-decision `_state_model` must survive the composer running (POC-T4/5, Issue #386).

`_snapshot` *builds AND STASHES* the per-decision StateModel onto `self._state_model` — one
construction site, unconditional. `_board_hypothetical` reaches it, and that is deliberate: a caller
that builds a speculative board in order to evaluate something against it wants exactly that stash.

It stops being deliberate the moment a speculative board is built DURING a live decision. Arming the
composer did that: `state_value`'s `hand` family calls `needs` -> `_leaf_needs_resolution` ->
`_board_hypothetical`, three times on an ordinary board, inside `plan_turn` — which `explain()` runs
BEFORE it builds the Decision. Every later reader of `self._state_model` in that same `explain()`
then saw a hypothetical end-of-turn board instead of the real one.

**What it cost, measured rather than imagined.** `_attach_value` reads `self._state_model.mine`.
Against the leaked leaf model, `_attach_body_view` returned None, `can_attack_tonight` went False,
and a one-shot Energy that unlocks a 210-damage attack this turn read as EVAPORATING for nothing:

    this_turn   90.0 -> 0.0        marginal   +90.0 -> -30.0        evaporates  False -> True

on a board where nothing about the attach had changed. Seven `test_attach_decider` tests caught it;
all forty-four pass on `main`, and the same seven fail at the bare swap commit, so it was the swap
and not the deletions around it. Nothing in the composer's own output looked wrong — this is a
telemetry-and-scoring corruption downstream of a decision that was itself fine.

The guard is written against the SYMPTOM (identity of the stashed model across a decision) rather
than against the attach decider, because the attach decider was one victim and the leak was general:
anything reading `self._state_model` after `plan_turn` was affected.
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
    """The stashed model at the END of a decision is the one built for the LIVE board, not the last
    hypothetical the composer priced on its way there.

    Asserted by OBJECT IDENTITY against the first model `_snapshot` built in this decision, and that
    choice is the whole test. The first version of this guard compared `prizes_remaining` and the
    body count between the stashed model and a freshly-built one — and it PASSED with the fix
    disabled, because a hypothetical END-OF-TURN board of the same game has the same prize count and
    usually the same bodies. It asserted nothing while looking like a regression net. Identity cannot
    be satisfied by a coincidence."""
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
    """The other half, and the reason the fix is NOT a blanket restore inside `_board_hypothetical`.

    A caller that builds a hypothetical board in order to evaluate a rung against it depends on the
    stash — `tests/strategy/test_hand_size_relief.py` does exactly this. A first attempt at the fix
    restored the model inside `_board_hypothetical` itself; it repaired the attach decider and broke
    five relief tests, and it made a sixth test pass for the WRONG reason, by feeding the live model
    to reads inside `_leaf_needs_resolution` that are supposed to see the hypothetical one.

    So the restore lives in `_leaf_needs_resolution` — the one caller that is speculative *during a
    live decision* — and this asserts the general behaviour it deliberately did not change."""
    pilot = _pilot()
    obs = _obs()
    pilot._board(obs, obs.get("select"))
    live = pilot._state_model

    hypo_obs = {**obs, "current": {**obs["current"], "turn": 9}}
    pilot._board_hypothetical(hypo_obs)
    assert pilot._state_model is not live, (
        "`_board_hypothetical` no longer stashes — callers that evaluate against the hypothetical "
        "board read `self._state_model` and would silently score the wrong one")
