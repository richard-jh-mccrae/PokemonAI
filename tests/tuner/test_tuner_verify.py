"""The Verifier: inject a candidate Hypothesis, re-fit over all Corrections, gate it (ADR-0018)."""
import pytest
from common.pilot import Pilot
from common.strategy import Hypothesis, Strategy
from pilot_helpers import HAND, MAIN, card_opt, make_select, state

from train.blunder.correction import build_correction
from train.blunder.decisions import Decision
from train.tuner import verify as verify_mod
from train.tuner.verify import union_verify, verify


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


# --- union_verify: the parallel-mode JOIN gate (ADR-0018) --------------------------------------

def test_union_verify_passes_when_independent_rules_each_fix_their_cluster():
    """REQ-TUNER-0010: two file- and behavior-independent rules verified TOGETHER each satisfy their
    cluster with no regression -> the merged round passes."""
    def pilot_with(extra):
        return Pilot(Strategy(hypotheses=list(extra)), deck=[1] * 60)

    corrections = [_corr(hand=[111, 222], correct=[1]), _corr(hand=[333, 444], correct=[1])]
    authored = [Hypothesis("a-fix", "", when=lambda c: c.card_id == 222, weight=20),
                Hypothesis("b-fix", "", when=lambda c: c.card_id == 444, weight=20)]

    result = union_verify(authored, corrections, pilot_with, seeds={}, clusters={"a": [0], "b": [1]})
    assert result.passed
    assert result.clusters_satisfied == {"a": True, "b": True}
    assert not result.regressed and result.newly_fixed == [0, 1]


def test_union_verify_catches_a_cross_cluster_regression(monkeypatch):
    """REQ-TUNER-0010: the hazard the join exists for — each cluster is satisfied in the union, yet a
    previously-satisfied (e.g. ``covered``) Correction regresses. Per-cluster verify misses it; the
    union gate must fail the round. (``_satisfied`` is stubbed: the fit's nonlinearity is verify-level
    behaviour already covered above; here we pin ``union_verify``'s base-vs-union wiring.)"""
    seq = iter([[True, True, True],           # base (seeds-only): all three satisfied
                [True, True, False]])          # union: clusters a & b hold, covered Correction breaks
    monkeypatch.setattr(verify_mod, "_satisfied", lambda *a, **k: next(seq))

    def pilot_with(extra):
        return Pilot(Strategy(hypotheses=list(extra)), deck=[1] * 60)

    corrections = [_corr([111, 222], [1]), _corr([333, 444], [1]), _corr([555, 666], [1])]
    authored = [Hypothesis("a-fix", "", when=lambda c: c.card_id == 222, weight=20),
                Hypothesis("b-fix", "", when=lambda c: c.card_id == 444, weight=20)]

    result = union_verify(authored, corrections, pilot_with, seeds={}, clusters={"a": [0], "b": [1]})
    assert result.clusters_satisfied == {"a": True, "b": True}   # both clusters individually fine
    assert result.regressed == [2]                               # ...but covered Correction broke
    assert not result.passed                                     # so merged round must NOT pass


def test_union_verify_rejects_a_contaminated_baseline():
    """REQ-TUNER-0010: if ``pilot_with([])`` already holds an authored rule, base==union for it and
    ``regressed`` goes blind — guard rejects it rather than silently masking interference."""
    def pilot_with(extra):
        seeded = Hypothesis("a-fix", "", when=lambda c: False, weight=0)   # baseline ALREADY holds a-fix
        return Pilot(Strategy(hypotheses=[seeded, *extra]), deck=[1] * 60)

    authored = [Hypothesis("a-fix", "", when=lambda c: c.card_id == 222, weight=20)]
    with pytest.raises(ValueError, match="already contains"):
        union_verify(authored, [_corr([111, 222], [1])], pilot_with, seeds={}, clusters={"a": [0]})


def test_union_verify_rejects_duplicate_authored_ids():
    """REQ-TUNER-0010: two clusters whose authored ids collide would lose one to a dict-merge (a
    completion-mandate breach) and double-weight it in the pilot — guard rejects it."""
    def pilot_with(extra):
        return Pilot(Strategy(hypotheses=list(extra)), deck=[1] * 60)

    authored = [Hypothesis("dup", "", when=lambda c: c.card_id == 222, weight=20),
                Hypothesis("dup", "", when=lambda c: c.card_id == 444, weight=20)]
    with pytest.raises(ValueError, match="duplicate"):
        union_verify(authored, [_corr([111, 222], [1])], pilot_with, seeds={}, clusters={"a": [0]})
