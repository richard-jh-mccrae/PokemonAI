"""Evolve-valuation corpus: the anchors the rung→equation fold must not regress.

ADR-0070.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from poc_t4_flips import param_for

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures" / "corrections"


def _pilot(agent: str):
    spec = importlib.util.spec_from_file_location("tune_mod", REPO / "tools" / "train" / "tune.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._build_pilot(agent)[0]


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("agent,fixture,leg", [
    param_for("dp_evolve_the_draw_engine_f40",
              "dragapult_ex", "dp_evolve_the_draw_engine_f40", "income-ON (one-shot burst)",
              id="dragapult_ex-dp_evolve_the_draw_engine_f40"),
])
def test_evolve_corpus_pin(agent, fixture, leg):
    fx = _fixture(fixture)
    chosen = _pilot(agent).explain(fx["obs"]).chosen
    assert chosen == fx["correct"], (
        f"[{leg}] regression: {fixture} chose {chosen}, expected {fx['correct']} ({fx.get('correct_label')})")


@pytest.mark.parametrize("agent,fixture", [
    param_for("dp_hold_evolve_until_typed_ready_f35",
              "dragapult_ex", "dp_hold_evolve_until_typed_ready_f35",
              id="dragapult_ex-dp_hold_evolve_until_typed_ready_f35"),
])
def test_evolve_corpus_claims(agent, fixture):
    """Assert what the fixture's own `claims` block declares (ADR-0072 decision 3)."""
    from train.gates import (evaluate_axis_claim, evaluate_decision_claim,
                             evaluate_endorsement_claim, parse_claims)
    fx = _fixture(fixture)
    claims = parse_claims(fx)
    dec = _pilot(agent).explain(fx["obs"])
    options = (fx["obs"].get("select") or {}).get("option") or []
    ctx = (fx["obs"].get("select") or {}).get("context")
    scores = [None] * len(options)
    for o in dec.options:
        scores[o.index] = o.score

    assert evaluate_decision_claim(claims.decision, chosen=dec.chosen) is True, (
        f"{fixture} decision claim: chose {dec.chosen}, claimed {claims.decision.correct}")
    for c in claims.axis:
        assert evaluate_axis_claim(c, options=options, scores=scores, select_context=ctx) is True, (
            f"{fixture} axis claim {c.prefer} over {c.over}: scores={scores}")
    for c in claims.endorsement:
        assert evaluate_endorsement_claim(c, options=options, scores=scores,
                                          select_context=ctx) is True, (
            f"{fixture} endorsement claim slot={c.slot} endorsed={c.endorsed}: scores={scores}")


# `dp_open_utility_over_fragile_line_base_f2` is out of scope here (ADR-0079): it is a `_SETUP_ACTIVE`
# placement, covered by tests/strategy/test_setup_active_placement.py.


def test_evolve_corpus_planner_scope_f82():
    fx = _fixture("dp_evolve_energized_line_body_first_f82")
    chosen = _pilot("dragapult_ex").explain(fx["obs"]).chosen
    assert chosen == fx["correct"], (
        f"dp_evolve_energized_line_body_first_f82 chose {chosen}, expected {fx['correct']}")
