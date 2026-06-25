"""Deriving a Correction's attribution from the fired-Hypothesis diff (ADR-0017)."""
from train.tuner.attribution import derive_attribution


def test_differing_fired_sets_attribute_to_the_discriminating_hypotheses():
    """REQ-TUNER-0001: when correct and chosen fire different Hypotheses, the blunder is
    attributable to those (a weight fix can reorder them)."""
    a = derive_attribution(chosen_ids={"open-cinderace"}, correct_ids={"tutor", "accel"},
                           tactical_delta=0)
    assert a == "hypothesis:accel,open-cinderace,tutor"     # sorted symmetric difference


def test_identical_fired_sets_with_no_combat_gap_are_missing_hypothesis():
    """REQ-TUNER-0001: identical features + equal combat → no weight can reorder → a new rule."""
    assert derive_attribution(chosen_ids={"tutor"}, correct_ids={"tutor"},
                              tactical_delta=0) == "missing_hypothesis"


def test_identical_fired_sets_with_combat_gap_are_tactical():
    """REQ-TUNER-0001: identical features but the gap is the combat term → tactical."""
    assert derive_attribution(chosen_ids={"tutor"}, correct_ids={"tutor"},
                              tactical_delta=50) == "tactical"
