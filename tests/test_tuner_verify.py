"""The Verifier: inject a candidate Hypothesis, re-fit over all Corrections, gate it (ADR-0018)."""
from common.pilot import Pilot
from common.strategy import Hypothesis, Strategy
from pilot_helpers import HAND, MAIN, card_opt, make_select, state

from train.blunder.correction import build_correction
from train.blunder.decisions import Decision
from train.tuner.verify import verify


def _corr(hand, correct):
    options = [card_opt(HAND, 0), card_opt(HAND, 1)]
    current = state(hand=hand)
    dec = Decision(episode_id=1, frame=5, seat=0, turn=2, select_context=MAIN, select_type=0,
                   options=options, chosen=[0], current=current)
    return build_correction(dec, source="own", agent="x", correct=correct, category="bad_target",
                            rationale="r", obs=make_select(options, context=MAIN, current=current))


def test_verify_accepts_a_candidate_that_satisfies_the_cluster():
    """REQ-TUNER-0009: a candidate the fit can use to reorder the cluster, with no regression, passes."""
    def pilot_with(extra):
        return Pilot(Strategy(hypotheses=extra), deck=[1] * 60)

    corrections = [_corr(hand=[111, 222], correct=[1])]                 # correct = card 222
    candidate = Hypothesis("likes-222", "", when=lambda c: c.card_id == 222, weight=20)

    result = verify(candidate, corrections, pilot_with, seeds={}, cluster=[0])
    assert result.passed and result.cluster_satisfied and not result.regressed


def test_verify_rejects_a_candidate_that_does_not_discriminate_the_cluster():
    """REQ-TUNER-0009: a candidate firing equally for chosen and correct can't reorder → rejected."""
    def pilot_with(extra):
        return Pilot(Strategy(hypotheses=extra), deck=[1] * 60)

    corrections = [_corr(hand=[111, 111], correct=[1])]                 # both options card 111
    candidate = Hypothesis("likes-111", "", when=lambda c: c.card_id == 111, weight=20)  # fires for both

    result = verify(candidate, corrections, pilot_with, seeds={}, cluster=[0])
    assert not result.passed and not result.cluster_satisfied
