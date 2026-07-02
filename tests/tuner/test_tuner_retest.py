"""Retest: diff how the agent would decide now vs the embedded live trace (ADR-0019)."""
from common.pilot import Pilot
from common.strategy import Hypothesis, Strategy
from pilot_helpers import HAND, MAIN, card_opt, make_select, state

from train.blunder.correction import build_correction
from train.blunder.decisions import Decision
from train.tuner.retest import retest


def _correction(obs, *, correct, live_trace):
    d = Decision(episode_id="t", frame=0, seat=0, turn=2, select_context="Main",
                 select_type="Main", options=obs["select"]["option"], chosen=[0],
                 current=obs["current"], obs=obs)
    return build_correction(d, source="own", agent="x", correct=correct,
                            category="bad_target", rationale="r", live_trace=live_trace)


def test_retest_reports_fixed_only_when_correct_now_wins():
    """REQ-TUNER-0014: retest re-derives the decision in live-telemetry format and flags `fixed`
    once the correct option is chosen; `before` comes from the embedded live trace."""
    boost = Hypothesis("boost", "", when=lambda c: c.card_id == 222, weight=0)  # off by default
    obs = make_select([card_opt(HAND, 0), card_opt(HAND, 1)], context=MAIN,
                      current=state(hand=[111, 222]))
    corr = _correction(obs, correct=[1], live_trace={"chosen": [0], "margin": 0})

    base = retest(corr, Pilot(Strategy(hypotheses=[boost]), deck=[1] * 60))
    assert base["chosen_after"] == [0] and base["fixed"] is False     # blunder still occurs
    assert base["chosen_before"] == [0]                                # from live trace

    tuned = retest(corr, Pilot(Strategy(hypotheses=[boost]), deck=[1] * 60, overrides={"boost": 50.0}))
    assert tuned["chosen_after"] == [1] and tuned["fixed"] is True     # fix makes correct win
    assert tuned["after"]["opts"][1]["fired"] == [["boost", 50.0]]     # live-format trace
