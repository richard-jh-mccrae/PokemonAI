"""The `baseline/` cluster split (ADR-0025) — a characterization guard that the move preserved the
roster. Asserts on id SETS, not weights: weights are tuned (ADR-0009), but a refactor must never
drop, duplicate, or misfile a rule. The decision-context axis is the contract — each `baseline_*`
cluster owns exactly the rules that fire on its select.
"""
import pytest

from common.strategy.baseline import (
    BASELINE_HYPOTHESES, DISRUPTION_HYPOTHESES, ENERGY_HYPOTHESES,
    EVOLUTION_HYPOTHESES, HEAL_HYPOTHESES, OPENING_HYPOTHESES, PHASES_HYPOTHESES,
    POSTURE_HYPOTHESES, PROMOTE_HYPOTHESES, RETREAT_HYPOTHESES, SEQUENCING_HYPOTHESES,
    SNIPE_HYPOTHESES,
)
from common.strategy.doctrines import (FETCH_HYPOTHESES, GUST_HYPOTHESES, REFRESH_HYPOTHESES,
                                       TOOL_HYPOTHESES as TOOL_DOCTRINE_HYPOTHESES)
from common.strategy.general_strategy import GENERAL_STRATEGY
from common.strategy.strategy import Hypothesis


def _ids(hyps):
    return {h.id for h in hyps}


# The decision-context contract: which rule lives in which cluster (ADR-0025).
CLUSTERS = {
    # ENERGY is deliberately TINY since the attach-decider swap (#139, ADR-0069): 19 of its 23 rungs
    # were DELETED when `Pilot._attach_value` became the real decider, and only STRUCTURE survives —
    # a PLAY-side source pick plus two band-constrained positional claims. This set is the deletion's
    # characterization guard: a rung reappearing here means a weight coincidence came back.
    "energy": (ENERGY_HYPOTHESES, {
        "use-acceleration",                     # PLAY-side accel source pick (currency-clean)
        "prefer-active-attach-in-setup",        # positional prior, below one scaled build step
        "feed-the-line-for-disruptor-lock"}),   # OFFENSIVE item-lock maneuver step 1 (dragapult f20)
    # The six DAMAGE(15) TARGET rungs are DELETED since ADR-0085 (#188) — `snipe-for-the-ko` (60),
    # `snipe-the-evolving-threat` (45), `snipe-the-forced-promotion` (40), `snipe-the-top-threat` (30),
    # `snipe-the-threat` (20), `snipe-on-the-path` (12). The bench-target pick is decided by
    # `common/snipe_relevance.py`'s [0,1] scalar, with the KO half as the structural
    # `_snipe_ko_dominator`. The same shape as `promote` below (ADR-0100) and `energy` (ADR-0069):
    # a decider replaces its rung family outright rather than standing it down.
    # What SURVIVES here is the counter placement/move family — a different set of select contexts
    # (13/14/16/40), untouched by decision 5's scope.
    "snipe": (SNIPE_HYPOTHESES, {
        "place-counter-to-convert", "move-counters-off-the-damaged", "move-max-counters"}),
    # The BENCH cluster no longer EXISTS (Issue #261 item 2d) — deliberately gone rather than empty,
    # so its absence from this table is the characterization guard. The deploy-decider swap
    # (Issue #197, ADR-0086) deleted six of its seven rungs into `common.deploy_value` (`dont-bench-multiprize` is
    # the exposure leg, `dont-bench-onto-their-path` the Prize-Path delta,
    # `develop-the-accel-recipient` the accel unlock, the three develop/prefer rungs the assignment
    # relevance), and ADR-0096 decision 2 deleted the seventh: `keep-a-bench` (+60) guarded nothing
    # `Pilot._empty_bench_forced` does not already guarantee, and it WAS the spare-body cliff.
    # EMPTY since ADR-0100 (#141): all seven promote rungs are DELETED — the promote/retreat DECIDER
    # prices the family as the Sub-lethal Residual, so the KO half is `_promote_ko_tactical` and the
    # rest is emergent from reachable damage and prize Exposure.
    "promote": (PROMOTE_HYPOTHESES, set()),
    # Four of five retreat rungs DELETED by the same ruling. `retreat-to-wall-the-line` SURVIVES
    # because it is a MANEUVER, not a value claim: its payoff lands on later steps, which a
    # per-option equation cannot see. Owner #165.
    "retreat": (RETREAT_HYPOTHESES, {"retreat-to-wall-the-line"}),
    "evolution": (EVOLUTION_HYPOTHESES, {
                        "prefer-rush-evolve-tutor", "dont-rush-evolve-without-target"}),
    "heal": (HEAL_HYPOTHESES, {"hold-clutch-heal", "dont-waste-clutch-heal"}),
    # The Set-Up ACTIVE pick is ONE rule over one deck declaration since ADR-0079 — `open-the-
    # accelerator`, `open-the-item-lock-starter`, `dont-open-multiprize-active` and
    # `dont-open-with-the-engine` were DELETED, not folded into a successor rung, and their job is
    # now the ORDER of each deck's `Strategy.starter_priority`.
    "opening": (OPENING_HYPOTHESES, {"keep-a-startable-hand", "honor-preferred-start",
                                     "open-the-declared-starter"}),
    "sequencing": (SEQUENCING_HYPOTHESES, {"dig-before-commit",
                                           "dont-play-damage-boost-when-cant-attack",
                                           "use-the-draw-engine-ability",
                                           "dont-spend-unneeded-supporter"}),  # BUILD 4 (weight-0, deferred)
    # `play-energy-denial` RETIRED (ADR-0062); `play-harlequin-vs-hand-size` (+25),
    # `disrupt-when-unfavored` (+18) and `strip-the-stacked-engine-hand` (+22) RETIRED (ADR-0102) —
    # the first two replaced by `pilot._hand_size_relief_tactical`, the third an unfired forward
    # contract carrying a live weight.
    "disruption": (DISRUPTION_HYPOTHESES, {
        "dont-gift-a-refresh-when-favored",
        "disrupt-the-tailored-hand",            # one-sided-strip forward contract; weight-0
        "unfair-stamp-comeback-posture"}),      # post-KO don't-empty-hand vs Stamp opponent; weight-0
    "phases": (PHASES_HYPOTHESES, {   # ADR-0040 advisory bands — the one c.board.phase consumer
        "phase-stabilize-prefer-heal", "phase-close-stop-developing"}),
    "posture": (POSTURE_HYPOTHESES, {  # ADR-0026 prize-position posture (learnthetcg risk-scaling); weight-0
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
    # disjoint + complete: no rule is in two clusters, none lost in assembly.
    assert len(BASELINE_HYPOTHESES) == sum(len(ids) for _, ids in CLUSTERS.values())


@pytest.mark.req("REQ-GEN-0025")
def test_general_strategy_assembles_baseline_plus_doctrines_with_no_loss_or_dup():
    doctrines = (_ids(GUST_HYPOTHESES) | _ids(FETCH_HYPOTHESES) | _ids(REFRESH_HYPOTHESES)
                 | _ids(TOOL_DOCTRINE_HYPOTHESES))
    assert _ids(GENERAL_STRATEGY.hypotheses) == _ids(BASELINE_HYPOTHESES) | doctrines
    # no duplicate ids across the whole assembled strategy.
    ids = [h.id for h in GENERAL_STRATEGY.hypotheses]
    assert len(ids) == len(set(ids))


@pytest.mark.req("REQ-GEN-0025")
def test_attach_before_hand_shuffle_stays_in_the_shuffle_doctrine_not_baseline_energy():
    # Doctrine cohesion outranks decision-context axis: this ATTACH rule belongs to
    # Shuffle-Refresh doctrine's sequencing story, not baseline_energy (ADR-0025).
    assert "attach-before-hand-shuffle" in _ids(REFRESH_HYPOTHESES)
    assert "attach-before-hand-shuffle" not in _ids(BASELINE_HYPOTHESES)


def test_a_hypothesis_cannot_be_authored_silently_inert():
    """`Hypothesis.weight` carries no default (2026-07-14). Authoring a rung at weight=0 stays a
    first-class pattern -- the ladder-gated seed, minted inert until corrections exercise it and the
    tuner promotes it off zero. What is now impossible is authoring one inert by ACCIDENT: a dropped
    kwarg used to yield 0.0 silently, indistinguishable at runtime from a deliberate seed."""
    with pytest.raises(TypeError):
        Hypothesis(id="forgot-the-weight", rationale="...", when=lambda c: True)   # no weight=
    deliberate = Hypothesis(id="ladder-gated-seed", rationale="SEED(ladder): 22", when=lambda c: True,
                            weight=0)                                              # explicit: intended
    assert deliberate.weight == 0
