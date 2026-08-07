"""The `baseline/` cluster split (ADR-0025) — a characterization guard on id SETS, not weights.

CONVENTION: a cluster that is GONE is ABSENT from `CLUSTERS`, never present-and-empty, and the
comment in its place records who took its rungs. `promote`'s empty set is therefore deliberate — the
rungs are gone, the module still exists.
"""
import pytest

from common.strategy.baseline import (
    BASELINE_HYPOTHESES, ENERGY_HYPOTHESES, EVOLUTION_HYPOTHESES, OPENING_HYPOTHESES,
    PHASES_HYPOTHESES, POSTURE_HYPOTHESES, PROMOTE_HYPOTHESES, SNIPE_HYPOTHESES,
)
from common.strategy.doctrines import FETCH_HYPOTHESES, GUST_HYPOTHESES, REFRESH_HYPOTHESES
from common.strategy.general_strategy import GENERAL_STRATEGY
from common.strategy.strategy import Hypothesis


def _ids(hyps):
    return {h.id for h in hyps}


# The decision-context contract: which rule lives in which cluster (ADR-0025).
CLUSTERS = {
    # TINY since the attach-decider swap (ADR-0069): 19 of 23 rungs DELETED, only STRUCTURE survives.
    # A rung reappearing here means a weight coincidence came back.
    "energy": (ENERGY_HYPOTHESES, {
        "use-acceleration",                     # PLAY-side accel source pick (currency-clean)
        "prefer-active-attach-in-setup",        # positional prior, below one scaled build step
        "feed-the-line-for-disruptor-lock"}),   # OFFENSIVE item-lock maneuver step 1
    # The six DAMAGE(15) TARGET rungs are DELETED (ADR-0085); `common/snipe_relevance.py` decides.
    # What survives is the counter placement/move family, on contexts 13/14/16/40.
    "snipe": (SNIPE_HYPOTHESES, {
        "place-counter-to-convert", "move-counters-off-the-damaged", "move-max-counters"}),
    # The BENCH cluster no longer EXISTS: six rungs went to `common.deploy_value` (ADR-0086) and
    # ADR-0096 d2 deleted the seventh. EMPTY here since ADR-0100: the promote/retreat DECIDER prices it.
    "promote": (PROMOTE_HYPOTHESES, set()),
    # The RETREAT cluster no longer EXISTS: four rungs to ADR-0100's decider, the fifth to the
    # sequence composer (Issue #386), which can score the later steps the maneuver was standing in for.
    "evolution": (EVOLUTION_HYPOTHESES, {
                        "prefer-rush-evolve-tutor", "dont-rush-evolve-without-target"}),
    # The HEAL cluster no longer EXISTS (Issue #386) — the composer answers it as a `survival` delta.
    # The Set-Up ACTIVE pick is one rule over `Strategy.starter_priority`'s ORDER since ADR-0079.
    "opening": (OPENING_HYPOTHESES, {"keep-a-startable-hand", "honor-preferred-start",
                                     "open-the-declared-starter"}),
    # The SEQUENCING and DISRUPTION clusters no longer EXIST (Issue #386). The information-before-
    # commitment ORDER survives as a whitelisted sound rule and the composer's in-block ordering.
    "phases": (PHASES_HYPOTHESES, {   # ADR-0040 advisory bands — the one c.board.phase consumer
        "phase-stabilize-prefer-heal", "phase-close-stop-developing"}),
    "posture": (POSTURE_HYPOTHESES, {  # ADR-0026 prize-position posture; weight-0
        "play-safe-when-ahead-on-prizes"}),
}


@pytest.mark.req("REQ-GEN-0025")
@pytest.mark.parametrize("name", list(CLUSTERS))
def test_each_baseline_cluster_owns_exactly_its_decision_context_rules(name):
    hyps, expected = CLUSTERS[name]
    assert _ids(hyps) == expected


@pytest.mark.req("REQ-GEN-0025")
def test_baseline_hypotheses_is_the_disjoint_union_of_the_clusters():
    expected = set().union(*(ids for _, ids in CLUSTERS.values()))
    assert _ids(BASELINE_HYPOTHESES) == expected
    assert len(BASELINE_HYPOTHESES) == sum(len(ids) for _, ids in CLUSTERS.values())


@pytest.mark.req("REQ-GEN-0025")
def test_general_strategy_assembles_baseline_plus_doctrines_with_no_loss_or_dup():
    # The TOOL doctrine is GONE, Mixin and all (Issue #386) — the leaf's `survival` term replaced it.
    doctrines = _ids(GUST_HYPOTHESES) | _ids(FETCH_HYPOTHESES) | _ids(REFRESH_HYPOTHESES)
    assert _ids(GENERAL_STRATEGY.hypotheses) == _ids(BASELINE_HYPOTHESES) | doctrines
    ids = [h.id for h in GENERAL_STRATEGY.hypotheses]
    assert len(ids) == len(set(ids))


@pytest.mark.req("REQ-GEN-0025")
def test_attach_before_hand_shuffle_stays_in_the_shuffle_doctrine_not_baseline_energy():
    # Doctrine cohesion outranks the decision-context axis (ADR-0025).
    assert "attach-before-hand-shuffle" in _ids(REFRESH_HYPOTHESES)
    assert "attach-before-hand-shuffle" not in _ids(BASELINE_HYPOTHESES)


def test_a_hypothesis_cannot_be_authored_silently_inert():
    """`Hypothesis.weight` has NO default: weight=0 stays a first-class deliberate seed, but a dropped
    kwarg can no longer produce one by accident."""
    with pytest.raises(TypeError):
        Hypothesis(id="forgot-the-weight", rationale="...", when=lambda c: True)   # no weight=
    deliberate = Hypothesis(id="ladder-gated-seed", rationale="SEED(ladder): 22", when=lambda c: True,
                            weight=0)
    assert deliberate.weight == 0
