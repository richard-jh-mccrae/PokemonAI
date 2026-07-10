"""The Tuner orchestration: route each Correction to weights (W) or a proposal (H)."""
from common.pilot import Pilot
from common.strategy import Hypothesis, Strategy
from pilot_helpers import HAND, MAIN, card_opt, make_select, state

from train.blunder.correction import build_correction
from train.blunder.decisions import Decision
from train.tuner.run import tune


def _corr(hand, correct, category, *, chosen=(0,), frame=5, scope="decision"):
    options = [card_opt(HAND, 0), card_opt(HAND, 1)]
    current = state(hand=hand)
    dec = Decision(episode_id=1, frame=frame, seat=0, turn=2, select_context=MAIN,
                   select_type=0, options=options, chosen=list(chosen), current=current)
    return build_correction(dec, source="own", agent="mega_starmie", correct=correct,
                            category=category, rationale="r", scope=scope,
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

    assert result.fit_adopted                                                   # fit beat the seeds
    assert result.overrides["likes-222"] > result.overrides["likes-111"]       # W lifted correct
    assert len(result.proposals) == 1 and "missed-win" in result.proposals[0].id
    assert not result.skipped


def test_fit_not_adopted_when_it_cannot_beat_the_seeds():
    """REQ-TUNER-0007: contradictory W corrections (one wants 222≻111, the other 111≻222) can't both
    hold; the fit satisfies no more than the seeds already do, so the priors are kept (no drift) and
    the un-honourable correction is surfaced rather than overfit away."""
    likes_111 = Hypothesis("likes-111", "", when=lambda c: c.card_id == 111, weight=10)
    likes_222 = Hypothesis("likes-222", "", when=lambda c: c.card_id == 222, weight=20)
    pilot = Pilot(Strategy(hypotheses=[likes_111, likes_222]), deck=[1] * 60)
    seeds = {"likes-111": 10.0, "likes-222": 20.0}                              # seeds satisfy 222≻111

    corr_ok = _corr(hand=[111, 222], chosen=[0], correct=[1], category="bad_target", frame=5)   # 222≻111 (holds)
    corr_bad = _corr(hand=[111, 222], chosen=[1], correct=[0], category="bad_target", frame=9)  # 111≻222 (conflict)

    result = tune([corr_ok, corr_bad], pilot, seeds)

    assert result.base_satisfied == 1
    assert not result.fit_adopted                                              # drift bought nothing
    assert result.overrides == seeds                                           # priors kept
    assert len(result.unsatisfied) == 1                                        # conflict surfaced


def test_a_scoped_correction_never_becomes_a_ranking_constraint():
    """ADR-0049: a turn/match blunder is a plan-layer error. Even when it names a discriminating
    `correct` at its Anchor — the shape that WOULD tune weights at decision scope — it is routed
    straight to the open worklist, so a sequencing error can never move a Tier-0 weight."""
    likes_111 = Hypothesis("likes-111", "", when=lambda c: c.card_id == 111, weight=10)
    likes_222 = Hypothesis("likes-222", "", when=lambda c: c.card_id == 222, weight=10)
    pilot = Pilot(Strategy(hypotheses=[likes_111, likes_222]), deck=[1] * 60)
    seeds = {"likes-111": 10.0, "likes-222": 10.0}

    turn = _corr(hand=[111, 222], correct=[1], category="sequencing_error", scope="turn")
    match = _corr(hand=[111, 111], correct=[], category="slow_setup", scope="match", frame=9)

    result = tune([turn, match], pilot, seeds)

    assert result.n_constraints == 0 and not result.fit_adopted
    assert result.overrides == seeds                     # weights untouched
    assert not result.unsatisfied and not result.skipped
    assert {p.scope for p in result.proposals} == {"turn", "match"}
    assert {p.subject for p in result.proposals} == {2, None}      # the Turn, and nothing


def test_a_scoped_proposal_records_the_fired_hypothesis_diff_as_information():
    """The Anchor's fired-Hypothesis diff is still computed and carried as `attribution` — useful
    context for /blunder-buster's routing — but it is INFORMATION, never a fitted constraint. A
    match-scope record has no prescription to diff, so it has no attribution."""
    likes_111 = Hypothesis("likes-111", "", when=lambda c: c.card_id == 111, weight=10)
    likes_222 = Hypothesis("likes-222", "", when=lambda c: c.card_id == 222, weight=10)
    pilot = Pilot(Strategy(hypotheses=[likes_111, likes_222]), deck=[1] * 60)

    turn = _corr(hand=[111, 222], correct=[1], category="sequencing_error", scope="turn")
    match = _corr(hand=[111, 111], correct=[], category="slow_setup", scope="match", frame=9)
    proposals = tune([turn, match], pilot, {"likes-111": 10.0, "likes-222": 10.0}).proposals

    by_scope = {p.scope: p for p in proposals}
    assert by_scope["turn"].attribution == "hypothesis:likes-111,likes-222"
    assert by_scope["match"].attribution is None
    assert by_scope["turn"].seed_weight == 0.0           # no weight to seed: the fix is planner code
