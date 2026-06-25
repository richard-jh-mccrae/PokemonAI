"""The Tuner orchestration: route each Correction to weights (W) or a proposal (H)."""
from common.pilot import Pilot
from common.strategy import Hypothesis, Strategy
from pilot_helpers import HAND, MAIN, card_opt, make_select, state

from train.blunder.correction import build_correction
from train.blunder.decisions import Decision
from train.tuner.run import tune


def _corr(hand, correct, category):
    options = [card_opt(HAND, 0), card_opt(HAND, 1)]
    current = state(hand=hand)
    dec = Decision(episode_id=1, frame=5, seat=0, turn=2, select_context=MAIN,
                   select_type=0, options=options, chosen=[0], current=current)
    return build_correction(dec, source="own", agent="mega_starmie", correct=correct,
                            category=category, rationale="r",
                            obs=make_select(options, context=MAIN, current=current))


def test_tune_routes_to_weights_and_proposals():
    """REQ-TUNER-0007: a discriminating Correction tunes weights (W); a non-discriminating one
    becomes a Hypothesis proposal (H)."""
    likes_111 = Hypothesis("likes-111", "", when=lambda c: c.card_id == 111, weight=10)
    likes_222 = Hypothesis("likes-222", "", when=lambda c: c.card_id == 222, weight=10)
    pilot = Pilot(Strategy(hypotheses=[likes_111, likes_222]), deck=[1] * 60)

    corr_w = _corr(hand=[111, 222], correct=[1], category="bad_target")        # 111 vs 222 → W
    corr_h = _corr(hand=[111, 111], correct=[1], category="missed_win")        # 111 vs 111 → H

    result = tune([corr_w, corr_h], pilot, seeds={"likes-111": 10.0, "likes-222": 10.0})

    assert result.overrides["likes-222"] > result.overrides["likes-111"]       # W lifted correct
    assert len(result.proposals) == 1 and "missed-win" in result.proposals[0].id
    assert not result.skipped
