"""The `baseline/` cluster split (ADR-0025) — a characterization guard that the move preserved the
roster. Asserts on id SETS, not weights: weights are tuned (ADR-0009), but a refactor must never
drop, duplicate, or misfile a rule. The decision-context axis is the contract — each `baseline_*`
cluster owns exactly the rules that fire on its select.
"""
import pytest

from common.strategy.baseline import (
    BASELINE_HYPOTHESES, BENCH_HYPOTHESES, DISRUPTION_HYPOTHESES, ENERGY_HYPOTHESES,
    EVOLUTION_HYPOTHESES, HEAL_HYPOTHESES, OPENING_HYPOTHESES, PROMOTE_HYPOTHESES,
    RETREAT_HYPOTHESES, SEQUENCING_HYPOTHESES, SNIPE_HYPOTHESES,
)
from common.strategy.doctrines import (FETCH_HYPOTHESES, GUST_HYPOTHESES, REFRESH_HYPOTHESES,
                                       TOOL_HYPOTHESES as TOOL_DOCTRINE_HYPOTHESES)
from common.strategy.general_strategy import GENERAL_STRATEGY


def _ids(hyps):
    return {h.id for h in hyps}


# The decision-context contract: which rule lives in which cluster (ADR-0025).
CLUSTERS = {
    "energy": (ENERGY_HYPOTHESES, {
        "power-up-attacker", "attach-energy-last", "use-acceleration", "dont-feed-the-doomed",
        "dont-waste-discard-energy", "build-active-wincon", "spread-attach-to-the-needy",
        "concentrate-energy-on-wincon", "prefer-reusable-over-burst", "prefer-active-attach-in-setup",
        "dont-overbuild-the-doomed-wincon", "feed-the-firing-accelerator",
        "dont-attach-discard-energy-turn1", "concentrate-accel-on-one-line-body",
        "conserve-burst-when-no-ko", "advance-the-accel-pieces",
        "conserve-discard-energy-prefer-basic", "dont-waste-off-type-energy"}),
    "snipe": (SNIPE_HYPOTHESES, {
        "snipe-the-threat", "snipe-for-the-ko", "snipe-the-top-threat",
        # counter placement/move family (Phantom Dive spread + Munkidori — adjacent bench-targeting):
        "place-counter-to-convert", "move-counters-off-the-damaged", "move-max-counters"}),
    "bench": (BENCH_HYPOTHESES, {"keep-a-bench", "dont-bench-multiprize", "pre-position-attacker",
                                 "develop-the-accel-recipient", "develop-a-basic-in-setup"}),
    "promote": (PROMOTE_HYPOTHESES, {
        "promote-the-accelerator-for-the-ko", "interpose-the-cheap-attacker-to-preserve-the-wincon",
        "promote-the-ready-wincon", "promote-the-staller", "dont-promote-into-their-prize-reach"}),
    "retreat": (RETREAT_HYPOTHESES, {"hold-position-in-setup", "retreat-to-ready-attacker",
                                     "swap-out-the-locked-attacker"}),
    "evolution": (EVOLUTION_HYPOTHESES, {
        "evolve-into-wincon", "advance-the-evolution-line", "evolve-the-energized-body-first",
        "prefer-rush-evolve-tutor", "dont-rush-evolve-without-target"}),
    "heal": (HEAL_HYPOTHESES, {"hold-clutch-heal", "dont-waste-clutch-heal"}),
    "opening": (OPENING_HYPOTHESES, {"keep-a-startable-hand", "open-the-accelerator",
                                     "honor-preferred-start"}),
    "sequencing": (SEQUENCING_HYPOTHESES, {"dig-before-commit",
                                           "dont-play-damage-boost-when-cant-attack"}),
    "disruption": (DISRUPTION_HYPOTHESES, {
        "play-energy-denial", "play-harlequin-vs-hand-size", "disrupt-when-unfavored",
        "dont-gift-a-refresh-when-favored"}),
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
