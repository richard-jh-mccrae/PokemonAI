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
    ("dragapult_ex", "dp_evolve_energized_line_body_first_f82", "which-body"),
    ("dragapult_ex", "dragapult_promote_over_fragile_base_f31", "promote-preserve-the-line"),
    ("dragapult_ex", "dp_charge_the_line_f29", "line-progress (advance over spread)"),
    ("dragapult_ex", "dragapult_concentrate_line_preevo_f85", "concentrate on the started line"),
])
def test_evolve_corpus_pin(agent, fixture, leg):
    """A covered evolve/line decision the equation must keep correct after the fold."""
    fx = _fixture(fixture)
    chosen = _pilot(agent).explain(fx["obs"]).chosen
    assert chosen == fx["correct"], (
        f"[{leg}] regression: {fixture} chose {chosen}, expected {fx['correct']} ({fx.get('correct_label')})")


# ── TARGETS: the equation's job. xfail(strict) → XPASS (hard fail) the moment it lands. ───────────
@pytest.mark.parametrize("agent,fixture,leg", [
    ("dragapult_ex", "dp_evolve_the_draw_engine_f40", "income-ON (one-shot burst)"),
    ("dragapult_ex", "dp_hold_evolve_until_typed_ready_f35", "income-OFF hold + typed readiness + scoped doom"),
    ("dragapult_ex", "dp_open_utility_over_fragile_line_base_f2", "exposure / opener (line-shape)"),
])
@pytest.mark.xfail(strict=True, reason="awaits the evolve-value equation (evolve-valuation-grill-spec.md)")
def test_evolve_corpus_target(agent, fixture, leg):
    """A correction the current rungs miss; the evolve-value equation must make it pass."""
    fx = _fixture(fixture)
    chosen = _pilot(agent).explain(fx["obs"]).chosen
    assert chosen == fx["correct"], (
        f"[{leg}] {fixture} chose {chosen}, expected {fx['correct']} ({fx.get('correct_label')})")
