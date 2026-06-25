"""Featurizing a Correction by replaying the Pilot on its embedded obs (ADR-0017)."""
from common.pilot import Pilot
from common.strategy import Hypothesis, Strategy
from pilot_helpers import HAND, MAIN, card_opt, make_select, state

from train.blunder.correction import build_correction
from train.blunder.decisions import Decision
from train.tuner.featurize import featurize


def _decision(options, current):
    return Decision(episode_id=1, frame=5, seat=0, turn=2, select_context=MAIN,
                    select_type=0, options=options, chosen=[0], current=current)


def test_featurize_derives_attribution_from_pilot_fired_diff():
    """REQ-TUNER-0002: featurize replays the Pilot on the Correction's obs and reads which
    Hypotheses fired for correct vs chosen, then derives the attribution."""
    likes_111 = Hypothesis("likes-111", "", when=lambda c: c.card_id == 111, weight=20)
    likes_222 = Hypothesis("likes-222", "", when=lambda c: c.card_id == 222, weight=20)
    pilot = Pilot(Strategy(hypotheses=[likes_111, likes_222]), deck=[1] * 60)

    options = [card_opt(HAND, 0), card_opt(HAND, 1)]          # card 111 vs card 222
    current = state(hand=[111, 222])
    obs = make_select(options, context=MAIN, current=current)
    corr = build_correction(_decision(options, current), source="own", agent="x",
                            correct=[1], category="bad_target", rationale="r", obs=obs)

    feat = featurize(corr, pilot)
    assert set(feat.chosen_fired) == {"likes-111"}
    assert set(feat.correct_fired) == {"likes-222"}
    assert feat.attribution == "hypothesis:likes-111,likes-222"


def test_featurize_flags_missing_hypothesis_when_no_rule_discriminates():
    """REQ-TUNER-0002: identical fired sets + no combat gap → missing_hypothesis."""
    likes_111 = Hypothesis("likes-111", "", when=lambda c: c.card_id == 111, weight=20)
    pilot = Pilot(Strategy(hypotheses=[likes_111]), deck=[1] * 60)

    options = [card_opt(HAND, 0), card_opt(HAND, 1)]          # both card 111
    current = state(hand=[111, 111])
    obs = make_select(options, context=MAIN, current=current)
    corr = build_correction(_decision(options, current), source="own", agent="x",
                            correct=[1], category="sequencing_error", rationale="r", obs=obs)

    assert featurize(corr, pilot).attribution == "missing_hypothesis"
