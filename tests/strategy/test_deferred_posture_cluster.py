"""BASELINE cluster: POSTURE — `play-safe-when-ahead-on-prizes` (proposal
`risk-scales-with-prize-position`, the *ahead* half). Risk scales with prize position: when I'm
clearly AHEAD on prizes, demote the one broadly-recognizable high-variance PLAY — a `shuffle_hand`
refresh (trade a working hand for a random redraw). Keyed on the PRIZE-lead axis
(`opp_prizes_remaining − my_prizes_remaining >= _AHEAD_MARGIN`), orthogonal to the disruption
cluster's hand-size / favorability rules.

Ships DEFAULT-OFF: an opponent-position prior stays telemetry-only (`weight=0`, `status="assumed"`)
until the ladder tunes the seed. These tests assert the `when()` trigger fires ahead-by-margin and
stays silent at even / behind, plus the default-off contract.
"""
from common.pilot import Board, Context
from common.strategy import Plan
from common.strategy.baseline import BASELINE_HYPOTHESES
from common.strategy.baseline.baseline_posture import _AHEAD_MARGIN, HYPOTHESES
from common.strategy.context import _ATTACH, _PLAY
from common.strategy.general_strategy import GENERAL_STRATEGY

_RULE = next(h for h in HYPOTHESES if h.id == "play-safe-when-ahead-on-prizes")


def _ctx(*, my_prizes, opp_prizes, tags=("shuffle_hand",), option_type=_PLAY):
    """A PLAY of a `shuffle_hand` refresh, with the prize counts under test on the Board."""
    return Context(plan=Plan.RACE, select_context=0, option_type=option_type, card_id=1213,
                   tags=list(tags),
                   board=Board(my_prizes_remaining=my_prizes, opp_prizes_remaining=opp_prizes))


def test_fires_when_ahead_by_the_margin():
    # I still need FEWER prizes than the opponent (I'm ahead) by at least _AHEAD_MARGIN.
    assert bool(_RULE.when(_ctx(my_prizes=2, opp_prizes=2 + _AHEAD_MARGIN)))
    assert bool(_RULE.when(_ctx(my_prizes=1, opp_prizes=4)))          # clearly ahead


def test_silent_at_even_or_behind():
    assert not _RULE.when(_ctx(my_prizes=3, opp_prizes=3))            # even -> no variance nudge
    assert not _RULE.when(_ctx(my_prizes=4, opp_prizes=2))            # BEHIND (gamble tier's job)
    assert not _RULE.when(_ctx(my_prizes=0, opp_prizes=0))            # unpopulated default -> silent
    assert not _RULE.when(_ctx(my_prizes=6, opp_prizes=6))            # opening -> silent


def test_silent_just_short_of_the_margin():
    # Ahead by strictly less than the margin does NOT engage the prior (margin guards "clearly ahead").
    assert not _RULE.when(_ctx(my_prizes=3, opp_prizes=3 + _AHEAD_MARGIN - 1))


def test_scoped_to_a_shuffle_hand_play():
    ahead = dict(my_prizes=1, opp_prizes=3)
    assert not _RULE.when(_ctx(tags=("draw",), **ahead))             # not a shuffle_hand refresh
    assert not _RULE.when(_ctx(option_type=_ATTACH, **ahead))        # not a PLAY


def test_ships_default_off_and_wired_into_the_general_strategy():
    # Default-OFF contract: weight 0 (telemetry-only, no argmax effect) + assumed status.
    assert _RULE.weight == 0
    assert _RULE.status == "assumed"
    # Wired: registered in the baseline roster and assembled into the General Strategy.
    assert _RULE.id in {h.id for h in BASELINE_HYPOTHESES}
    assert _RULE.id in {h.id for h in GENERAL_STRATEGY.hypotheses}
