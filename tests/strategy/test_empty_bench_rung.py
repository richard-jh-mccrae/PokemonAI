"""The post-setup empty-Bench SOUND RUNG (ADR-0081 decision 7, Issue #197).

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
from common.scouting.provider import CardStat
from common.strategy import Strategy
from common.strategy.context import _MAIN, _PLAY, _SETUP_BENCH
from common.strategy.general_strategy import GENERAL_STRATEGY

RIOLU, MEOWTH, BALL = 677, 1071, 1121


def _pilot():
    stats = {RIOLU: CardStat(RIOLU, name="Riolu", hp=80),
             MEOWTH: CardStat(MEOWTH, name="Meowth ex", hp=170, ex=True),
             BALL: CardStat(BALL, name="Ultra Ball", hp=0)}
    return Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats,
                 functions=CardFunctions({MEOWTH: ["supporter_tutor"]}))


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
    """Decision 7's scoping, and it is REQUIRED rather than merely safe.

    Verified at source (`docs/rules.md` §2): the player going first cannot attack on turn 1, and the
    player going second acts only after that turn — so in either seat MY first turn precedes the
    first legal attack of the game, and declining every pregame placement cannot lose before I can
    bench. The converse is what makes it mandatory: an unscoped guard would fire on
    `setup_bench_decline_f3` — bench empty, Meowth ex the sole option — and force exactly the
    placement decision 3 derives us out of, burning Last-Ditch Catch."""
    pilot = _pilot()
    obs = {"current": {"players": [{"active": [None], "bench": [], "hand": [{"id": MEOWTH}],
                                    "prize": [None] * 6, "deckCount": 47},
                                   {"active": [None], "bench": [], "prize": [None] * 6}],
                       "yourIndex": 0, "turn": 0},
           "select": {"context": _SETUP_BENCH, "minCount": 0, "maxCount": 1,
                      "option": [{"type": 3, "area": 2, "index": 0, "playerIndex": 0}]}}
    assert pilot.decide(obs) == []               # the decline survives the guard
