"""Evolve-valuation corpus — the Round-0 safety net for the evolve-value equation
(docs/plans/evolve-valuation-grill-spec.md).

The evolve decision is being converged from a pile of rungs
(baseline_evolution.py + the dragapult `hold-evolution` deck rung) onto ONE equation: the marginal
change in board need-coverage an evolve produces, priced in the one currency (Needs). This file is the
pre-build baseline measured 2026-07-15 through the real engine-backed Pilot:

  * PINS — the covered anchors the equation must NOT regress when the rungs fold.
  * TARGETS — currently-failing corrections the equation must fix, marked ``xfail(strict)`` so each
    flips to a hard failure (XPASS) the moment the equation lands, forcing the mark's removal.

FRESH Pilot per replay (no cross-fixture state). Card facts verified at source (grill spec §Machinery).
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures" / "corrections"


def _pilot(agent: str):
    spec = importlib.util.spec_from_file_location("tune_mod", REPO / "tools" / "train" / "tune.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._build_pilot(agent)[0]


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


# ── PINS: covered today; must survive the rung→equation fold ─────────────────────────────────────
@pytest.mark.parametrize("agent,fixture,leg", [
    ("dragapult_ex", "dragapult_promote_over_fragile_base_f31", "promote-preserve-the-line"),
    ("dragapult_ex", "dp_charge_the_line_f29", "line-progress (advance over spread)"),
    ("dragapult_ex", "dragapult_concentrate_line_preevo_f85", "concentrate on the started line"),
    # Promoted from TARGET on the swap (#140): the income-ON one-shot burst the equation was built
    # to fix. Its `xfail(strict)` XPASSed the moment the decider landed, which is what forced this move.
    ("dragapult_ex", "dp_evolve_the_draw_engine_f40", "income-ON (one-shot burst)"),
])
def test_evolve_corpus_pin(agent, fixture, leg):
    """A covered evolve/line decision the equation must keep correct after the fold."""
    fx = _fixture(fixture)
    chosen = _pilot(agent).explain(fx["obs"]).chosen
    assert chosen == fx["correct"], (
        f"[{leg}] regression: {fixture} chose {chosen}, expected {fx['correct']} ({fx.get('correct_label')})")


# ── CLAIMS: what a fixture asserts, declared in its own `claims` block (ADR-0071 decision 3) ──────
@pytest.mark.parametrize("agent,fixture", [
    ("dragapult_ex", "dp_hold_evolve_until_typed_ready_f35"),
])
def test_evolve_corpus_claims(agent, fixture):
    """Assert exactly what the fixture declares, rather than only whole-decision equality.

    f35 is the worked case. Its Decision Claim was RE-RULED 2026-07-26 (user, #167 decision-5
    sitting) from `[2]` (Recon first) to `[1]` (Poké Pad first): the Poké Pad's job in this deck is
    fetching the 2nd Drakloak so a bench Dreepy becomes a 2nd Recon Directive body — two digs instead
    of one — and resolving the deterministic tutor first also thins the deck by a known non-{P} card,
    improving both digs. Its **Endorsement Claim** is what credits the 1b swap: the sole evolve on the
    menu went 45.0 -> 0.0 with no rule firing, and a single-option lane cannot express that as an
    ordering (ADR-0071 amendment A)."""
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


# ── TARGETS: the equation's job. xfail(strict) → XPASS (hard fail) the moment it lands. ───────────
@pytest.mark.parametrize("agent,fixture,leg", [
    ("dragapult_ex", "dp_open_utility_over_fragile_line_base_f2", "exposure / opener (line-shape)"),
])
@pytest.mark.xfail(strict=True, reason="awaits the evolve-value equation (evolve-valuation-grill-spec.md)")
def test_evolve_corpus_target(agent, fixture, leg):
    """A correction the current rungs miss; the evolve-value equation must make it pass."""
    fx = _fixture(fixture)
    chosen = _pilot(agent).explain(fx["obs"]).chosen
    assert chosen == fx["correct"], (
        f"[{leg}] {fixture} chose {chosen}, expected {fx['correct']} ({fx.get('correct_label')})")


# ── f82: a PIN since ADR-0071 removed the shared-budget inflation (was PLANNER SCOPE) ─────────────
def test_evolve_corpus_planner_scope_f82():
    """f82: the Pilot picks the human's body through the real decision path.

    PROMOTED from strict-xfail to PIN by ADR-0071 (#163). The xfail's premise was that *"the evolve
    equation's standalone read is CORRECT (it prefers the benched body, whose clocks genuinely
    move)"* — but those clocks did NOT genuinely move. The bench held two more bodies at 50 against
    a single 60 spread, so evolving one Dreepy out of range only chose which body died; the 37.5 it
    scored was the per-body reading of a shared budget. Read as a Harvest at UNAVOIDABLE both bodies
    read `ko = 2` — evolving buys zero survival — the benched option falls to 25.0 against the
    Active's 30.0, and the Pilot reaches `correct` without any lethal tier having landed.

    The five-step maneuver is still the better play and still belongs to #165. This pin no longer
    waits on it."""
    fx = _fixture("dp_evolve_energized_line_body_first_f82")
    chosen = _pilot("dragapult_ex").explain(fx["obs"]).chosen
    assert chosen == fx["correct"], (
        f"dp_evolve_energized_line_body_first_f82 chose {chosen}, expected {fx['correct']}")
