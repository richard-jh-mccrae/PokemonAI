"""The post-setup empty-Bench SOUND RUNG (ADR-0086 decision 7, Issue #197).

`keep-a-bench` (+60) is the one rule in the bench table that guards a WIN CONDITION rather than a
preference: `docs/rules.md` §7 case 2 — "Opponent has no Pokémon in play to replace a KO'd Active".
An empty Bench under a Knocked-Out Active is not a bad position, it is the game.

So it is PROMOTED out of the weight layer rather than folded into the Deploy Marginal. The structural
argument is `_LINE_CAP`'s band invariant: max positional (readiness 300 + survival 50 + threat 100 +
value 40 + line 100) = 590 < 1000 = KO_SCORE, deliberately, so no positional term can outrank a real
prize. A loss-avoidance value cannot be simultaneously bounded under that band AND un-outbiddable —
arithmetic, not taste. It is therefore a FILTER on the option order, never a score.
"""
from __future__ import annotations

import pytest

from common.pilot import Pilot
from common.cards import CardFunctions
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy import Strategy
from common.strategy.context import _MAIN, _PLAY, _SETUP_BENCH
from common.strategy.general_strategy import GENERAL_STRATEGY

ATTACKER, OPPA, ATK = 900, 678, 20   # the planner-branch board: a chip attacker vs a KO-able Active

RIOLU, MEOWTH, BALL = 677, 1071, 1121


def _pilot():
    stats = {RIOLU: CardStat(RIOLU, name="Riolu", hp=80),
             MEOWTH: CardStat(MEOWTH, name="Meowth ex", hp=170, ex=True),
             BALL: CardStat(BALL, name="Ultra Ball", hp=0)}
    # `deploy_value=True` because the ctor defaults every feature OFF (the shipped state lives in
    # `runtime.PROFILE`). The Set-Up scoping test below asserts the guard does NOT force a placement
    # the Deploy Marginal declines — with no decider there is nothing to decline WITH, so the pilot
    # would bench Meowth ex and the test would pass or fail on the ctor default rather than the rule.
    return Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats,
                 functions=CardFunctions({MEOWTH: ["supporter_tutor"]}), deploy_value=True)


def _main_obs(hand_ids, *, bench, turn=4):
    """A MAIN menu offering a PLAY of each hand card, plus End."""
    opts = [{"type": _PLAY, "index": i} for i in range(len(hand_ids))] + [{"type": 14}]
    return {"current": {"players": [{"active": [{"id": RIOLU, "hp": 80}],
                                     "bench": [{"id": RIOLU, "hp": 80}] * bench,
                                     "hand": [{"id": c} for c in hand_ids],
                                     "prize": [None] * 6, "deckCount": 40},
                                    {"active": [{"id": RIOLU, "hp": 80}], "bench": [],
                                     "prize": [None] * 6}],
                        "yourIndex": 0, "turn": turn},
            "select": {"context": _MAIN, "minCount": 1, "maxCount": 1, "option": opts}}


@pytest.mark.req("REQ-DEPLOY-0010")
def test_an_empty_bench_forces_a_deploy_over_ending_the_turn():
    """The whole point: with nothing to promote, one Knock-Out ends the match on the spot, so a legal
    Pokémon play is taken rather than ranked. `End` is on the menu and must not win."""
    pilot = _pilot()
    obs = _main_obs([RIOLU, BALL], bench=0)
    assert pilot.decide(obs) == [0]


@pytest.mark.req("REQ-DEPLOY-0010")
def test_the_guard_ranks_WHICH_body_but_never_WHETHER():
    """It is a filter, not a score: the Deploy Marginal still chooses among the bodies, so a menu with
    two legal deploys picks one of THEM and never the Item or End."""
    pilot = _pilot()
    obs = _main_obs([BALL, RIOLU, MEOWTH], bench=0)
    assert pilot.decide(obs)[0] in (1, 2)


@pytest.mark.req("REQ-DEPLOY-0010")
def test_the_guard_stands_down_once_a_body_is_benched():
    """One body is enough to survive a Knock-Out, so the guard is silent from the first bench slot —
    it protects against losing, not against a thin board.

    Asserted on the guard itself rather than through `decide`, because "what wins once the guard
    stands down" is the ordinary scoring layer's business: an Ultra Ball play beating `End` is a
    legitimate outcome and says nothing about this rung."""
    pilot = _pilot()
    obs = _main_obs([RIOLU, BALL], bench=1)
    select, options = obs["select"], obs["select"]["option"]
    board = pilot._board(obs, select)
    order = [2, 1, 0]                            # End first, deploy last — the guard must NOT reorder
    assert pilot._empty_bench_forced(obs, select, board, options, order) == order


@pytest.mark.req("REQ-DEPLOY-0010")
def test_the_guard_does_NOT_fire_during_set_up():
    """Decision 7's scoping: the guard is a statement about a loss that is REACHABLE NOW.

    Verified at source (`docs/rules.md` §2): the player going first cannot attack on turn 1, and the
    player going second acts only after that turn — so in either seat MY first turn precedes the
    first legal attack of the game. At Set Up no Knock Out is legal yet, so there is nothing for a
    loss-avoidance filter to be forced by.

    Asserted on the FILTER itself rather than on the resulting pick. Those came apart in the
    2026-07-30 re-ruling of `83661652|0|decision|3`: the pregame placement now happens (Amendment F —
    with no other Pokémon in hand, declining leaves a one-body board), so a `decide(obs) == []`
    assertion would now be reading the price, not the scoping. The guard must stay silent either
    way — the placement is worth 0.0, chosen because nothing outranks it, never forced."""
    pilot = _pilot()
    obs = {"current": {"players": [{"active": [None], "bench": [], "hand": [{"id": MEOWTH}],
                                    "prize": [None] * 6, "deckCount": 47},
                                   {"active": [None], "bench": [], "prize": [None] * 6}],
                       "yourIndex": 0, "turn": 0},
           "select": {"context": _SETUP_BENCH, "minCount": 0, "maxCount": 1,
                      "option": [{"type": 3, "area": 2, "index": 0, "playerIndex": 0}]}}
    select = obs["select"]
    board = pilot._board(obs, select)
    order = list(range(len(select["option"])))
    assert pilot._empty_bench_forced(obs, select, board, select["option"], order) == order


@pytest.mark.req("REQ-DEPLOY-0010")
def test_the_guard_covers_the_PLANNER_branch_too():
    """The guard is a filter over the WHOLE decision, not a step of the scoring path — and the
    planner returns before the scoring path reaches it.

    Found by the ADR-0086 spec review. `decide()` early-returns `planned.next_step` when
    `plan_turn` commits a line, several stanzas above where `_empty_bench_forced` was applied, so a
    planned turn could end post-setup with an empty Bench while a legal deploy sat on the menu —
    the exact case decision 7 obliges the rung to prevent ("must ALSO prevent `_finish_turn_last`
    from ending a post-setup turn with an empty Bench while a deploy was available").

    The first repair was ineffective and the negative cases are why this test carries them: handing
    the guard only `planned.next_step` cannot work, because the guard reorders WITHIN the order it
    is given and the planned step is precisely where the deploy is absent. It is handed the full
    menu instead."""
    stats = {ATTACKER: CardStat(ATTACKER, name="attacker", hp=200, energyType=3, minAttackCost=1,
                                minCostDamage=100, maxDamage=100, attacks=(ATK,)),
             OPPA: CardStat(OPPA, name="opp", hp=60, energyType=7),
             RIOLU: CardStat(RIOLU, name="Riolu", hp=80, energyType=3)}
    provider = DictCardStatProvider(stats, attacks={ATK: AttackStat(ATK, damage=100, cost=1)})

    def _planner_pilot():
        return Pilot(Strategy(roles={ATTACKER: ["primary_attacker"]}), deck=[1] * 60,
                     general_strategy=GENERAL_STRATEGY, stats=provider,
                     functions=CardFunctions({}), deploy_value=True)

    def _decide(bench, hand):
        opts = [{"type": 13, "attackId": ATK}] + ([{"type": _PLAY, "index": 0}] if hand else [])
        obs = {"current": {"players": [
            {"active": [{"id": ATTACKER, "hp": 200, "maxHp": 200, "energies": [3]}],
             "bench": bench, "hand": [{"id": c} for c in hand],
             "prize": [None] * 2, "deckCount": 40},
            {"active": [{"id": OPPA, "hp": 60, "maxHp": 60, "energies": []}],
             "bench": [], "prize": [None] * 2, "deckCount": 40}],
            "yourIndex": 0, "turn": 4},
            "select": {"context": 0, "minCount": 1, "maxCount": 1, "option": opts}}
        dec = _planner_pilot().explain(obs)
        return (opts[dec.chosen[0]]["type"] if dec.chosen else None), dec.planned

    body = [{"id": RIOLU, "hp": 80, "maxHp": 80, "energies": []}]

    # Empty Bench + a legal body: the deploy is FORCED, and no line is reported — the override
    # replaced the plan, so `planned` is deliberately None here and cannot double as the
    # "did we reach the planner branch" probe. The two silent cases below carry that instead.
    picked, planned = _decide([], [RIOLU])
    assert picked == _PLAY and planned is None

    # Nothing to force, and Bench already developed: the guard is silent, so the planner's own line
    # comes back intact — which is also what proves this board reaches the PLANNER branch at all.
    for bench, hand in (([], []), (body, [RIOLU])):
        picked, planned = _decide(bench, hand)
        assert planned is not None, "this board must reach the PLANNER branch or it tests nothing"
        assert picked == 13
        assert planned.next_step == [0]           # the invariant holds when the guard stands down


@pytest.mark.req("REQ-DEPLOY-0010")
def test_when_the_guard_overrides_the_planner_no_line_is_reported():
    """The record stays WELL-FORMED when the guard overrides a planned line.

    `planned.next_step == chosen` is an invariant of the emitted record — asserted at
    `test_planner_engine.py:275`, and the `plan_candidates` / `committed` telemetry rests on it. The
    first version of the planner-branch guard broke it: it forced the deploy into `chosen` while
    still reporting `planned`, so the trace advertised a committed line the agent did not follow.

    CI caught it and this test exists because the local suite could not: the failing case is a LIVE
    drive that only sometimes reaches an empty Bench, so it passed 15/15 locally and failed on repeat
    6 of 15 in the determinism backstop. Asserted here on a board that forces the condition, rather
    than on a drive that stumbles into it."""
    stats = {ATTACKER: CardStat(ATTACKER, name="attacker", hp=200, energyType=3, minAttackCost=1,
                                minCostDamage=100, maxDamage=100, attacks=(ATK,)),
             OPPA: CardStat(OPPA, name="opp", hp=60, energyType=7),
             RIOLU: CardStat(RIOLU, name="Riolu", hp=80, energyType=3)}
    provider = DictCardStatProvider(stats, attacks={ATK: AttackStat(ATK, damage=100, cost=1)})
    pilot = Pilot(Strategy(roles={ATTACKER: ["primary_attacker"]}), deck=[1] * 60,
                  general_strategy=GENERAL_STRATEGY, stats=provider,
                  functions=CardFunctions({}), deploy_value=True)
    obs = {"current": {"players": [
        {"active": [{"id": ATTACKER, "hp": 200, "maxHp": 200, "energies": [3]}],
         "bench": [], "hand": [{"id": RIOLU}], "prize": [None] * 2, "deckCount": 40},
        {"active": [{"id": OPPA, "hp": 60, "maxHp": 60, "energies": []}],
         "bench": [], "prize": [None] * 2, "deckCount": 40}],
        "yourIndex": 0, "turn": 4},
        "select": {"context": 0, "minCount": 1, "maxCount": 1,
                   "option": [{"type": 13, "attackId": ATK}, {"type": _PLAY, "index": 0}]}}
    dec = pilot.explain(obs)
    assert dec.chosen == [1]                 # the guard forced the deploy over the planned attack
    assert dec.planned is None               # ...and no line is claimed, because none was followed
    # the invariant test_planner_engine.py asserts, stated directly:
    assert dec.planned is None or dec.planned.next_step == list(dec.chosen)

