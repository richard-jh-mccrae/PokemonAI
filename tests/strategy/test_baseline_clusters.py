"""The `baseline/` cluster split (ADR-0025) — a characterization guard that the move preserved the
roster. Asserts on id SETS, not weights: weights are tuned (ADR-0009), but a refactor must never
drop, duplicate, or misfile a rule. The decision-context axis is the contract — each `baseline_*`
cluster owns exactly the rules that fire on its select.
"""
import pytest

from common.strategy.baseline import (
    BASELINE_HYPOTHESES, BENCH_HYPOTHESES, DISRUPTION_HYPOTHESES, ENERGY_HYPOTHESES,
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
    "snipe": (SNIPE_HYPOTHESES, {
        "snipe-the-threat", "snipe-for-the-ko", "snipe-the-top-threat",
        "snipe-on-the-path",                    # Tier-3 Prize Path (ADR-0040)
        "snipe-the-forced-promotion",           # ADR-0044 Forced-Promotion Read
        "snipe-the-evolving-threat",            # restored 2026-07-09 (forward-wincon pre-evo, form-absent gated)
        # counter placement/move family (Phantom Dive spread + Munkidori — adjacent bench-targeting):
        "place-counter-to-convert", "move-counters-off-the-damaged", "move-max-counters"}),
    "bench": (BENCH_HYPOTHESES, {"keep-a-bench", "dont-bench-multiprize", "pre-position-attacker",
                                 "develop-the-accel-recipient", "develop-a-basic-in-setup",
                                 "develop-the-wincon-base-first",   # prefer the wincon Line base among develops
                                 "dont-bench-onto-their-path"}),   # Tier-3 Path Denial (ADR-0040)
    "promote": (PROMOTE_HYPOTHESES, {
        "promote-the-accelerator-for-the-ko", "interpose-the-cheap-attacker-to-preserve-the-wincon",
        "promote-the-ready-wincon", "promote-the-staller", "dont-promote-into-their-prize-reach",
        "promote-the-ko-attacker",          # KO-aware, boost-inclusive promote (promote_ko_aware)
        "dont-promote-onto-their-path"}),   # Tier-3 Path Denial (ADR-0040)
    "retreat": (RETREAT_HYPOTHESES, {"hold-position-in-setup", "retreat-to-ready-attacker",
                                     "swap-out-the-locked-attacker", "dont-play-switch-for-no-gain",
                                     "retreat-to-wall-the-line"}),
    "evolution": (EVOLUTION_HYPOTHESES, {
                        "dont-rush-evolve-without-target"}),
    "heal": (HEAL_HYPOTHESES, {"hold-clutch-heal", "dont-waste-clutch-heal"}),
    "opening": (OPENING_HYPOTHESES, {"keep-a-startable-hand", "open-the-accelerator",
                                     "honor-preferred-start", "dont-open-multiprize-active",
                                     "dont-open-with-the-engine",   # opener half of the utility-body read
                                     "open-the-item-lock-starter"}),
    "sequencing": (SEQUENCING_HYPOTHESES, {"dig-before-commit",
                                           "dont-play-damage-boost-when-cant-attack",
                                           "use-the-draw-engine-ability",
                                           "dont-spend-unneeded-supporter"}),  # BUILD 4 (weight-0, deferred)
    "disruption": (DISRUPTION_HYPOTHESES, {
        "play-harlequin-vs-hand-size", "disrupt-when-unfavored",   # play-energy-denial RETIRED (ADR-0062)
        "dont-gift-a-refresh-when-favored",
        "strip-the-stacked-engine-hand",   # ADR-0060: narrowed to ONE-SIDED strips
        "disrupt-the-tailored-hand",            # mirror of strip-the-stacked (tailored-DOWN hand); weight-0
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
