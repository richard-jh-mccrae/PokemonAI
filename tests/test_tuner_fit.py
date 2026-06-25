"""Ranking constraints and the weight fit (Job A, ADR-0009 / ADR-0017)."""
from train.tuner.featurize import Featurization
from train.tuner.fit import Constraint, fit_weights, ranking_constraint, satisfied_after_fit


def test_ranking_constraint_signs_only_discriminating_hypotheses():
    """REQ-TUNER-0003: `correct ≻ chosen` becomes a signed sparse delta over the
    discriminating Hypotheses (shared ones cancel) plus the combat-term advantage."""
    feat = Featurization(attribution="x", chosen_fired=["a", "shared"],
                         correct_fired=["b", "shared"], tactical_delta=10)
    con = ranking_constraint(feat)
    assert con.deltas == {"b": 1, "a": -1}      # +1 favors correct, -1 favors chosen
    assert con.tactical_delta == 10


def test_fit_weights_nudges_a_violated_constraint_until_correct_outranks_chosen():
    """REQ-TUNER-0004: from the authored seeds, the fit pushes discriminating weights until
    `Σ wᵢ·Δᵢ + Δtactical > 0` (correct outscores chosen)."""
    con = Constraint(deltas={"good": 1, "bad": -1}, tactical_delta=0)
    w = fit_weights([con], seeds={"good": 10.0, "bad": 10.0})   # margin 0 at seed -> violated
    margin = w["good"] - w["bad"] + con.tactical_delta
    assert margin > 0
    assert w["good"] > 10 and w["bad"] < 10


def test_fit_leaves_an_already_satisfied_constraint_unchanged():
    """REQ-TUNER-0004: a constraint already satisfied at the seeds produces no weight change."""
    con = Constraint(deltas={"good": 1}, tactical_delta=0)
    assert fit_weights([con], seeds={"good": 5.0}) == {"good": 5.0}


def test_satisfied_after_fit_marks_independent_constraints_satisfiable():
    """REQ-TUNER-0008: independent ranking constraints are all satisfiable after the fit."""
    cons = [Constraint(deltas={"a": 1}, tactical_delta=0),
            Constraint(deltas={"b": 1}, tactical_delta=0)]
    assert satisfied_after_fit(cons, seeds={}) == [True, True]


def test_satisfied_after_fit_flags_a_contradiction():
    """REQ-TUNER-0008: contradictory constraints (one lever, opposite signs) can't all hold."""
    cons = [Constraint(deltas={"x": 1}, tactical_delta=0),
            Constraint(deltas={"x": -1}, tactical_delta=0)]
    assert not all(satisfied_after_fit(cons, seeds={}))
