"""Evolve-value oracle (common/evolve_value.py) — docs/plans/evolve-valuation-grill-spec.md.

The full equation, emitted on `OptionTrace.evolve_shadow`. While it is REPORTING-ONLY (pre-swap) these
assert the equation RANKS the evolve options correctly — the design proof that must hold before the
`baseline_evolution` rungs are deleted. Card facts verified at source (grill spec §Machinery).
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


def _shadows(agent, fixture):
    fx = json.loads((FIXTURES / f"{fixture}.json").read_text(encoding="utf-8"))
    d = _pilot(agent).explain(fx["obs"])
    opts = fx["obs"]["select"]["option"]
    evolve = {i: d.options[i].evolve_shadow for i, o in enumerate(opts) if o.get("type") == 9}
    return fx, d, evolve


def test_income_on_evolve_is_endorsed_f40():
    """f40: Dunsparce→Dudunsparce turns a draw engine ON (one-shot) with no line/deploy — a positive
    income Δ, so the evolve is endorsed (>0) and will sequence ahead of the non-lethal KO."""
    fx, d, evolve = _shadows("dragapult_ex", "dp_evolve_the_draw_engine_f40")
    assert evolve[fx["correct"][0]] > 0, evolve


def test_hold_the_income_off_unready_evolve_f35():
    """f35: Drakloak→Dragapult on {R}{D} — a wincon that CAN'T pay Phantom Dive {R}{P}, forfeiting the
    Recon stream. deploy is the UNREADY tier and the income loss nets it low — below the Recon ability
    (~+18), so once the equation drives the score the premature evolve is suppressed (hold)."""
    fx, d, evolve = _shadows("dragapult_ex", "dp_hold_evolve_until_typed_ready_f35")
    (only_evolve,) = evolve.values()
    assert only_evolve < 18, evolve            # below the Recon dig — will not be chosen
    assert only_evolve < 40                     # far below a READY-wincon deploy (the old flat +40 bug)


def test_which_body_prefers_the_energized_f82():
    """f82: two mid-line Dreepy→Drakloak evolves; the energized body's deploy carries the +5 which-body
    bonus, so its value out-ranks the bare copy."""
    fx, d, evolve = _shadows("dragapult_ex", "dp_evolve_energized_line_body_first_f82")
    best = max(evolve, key=evolve.get)
    assert best == fx["correct"][0], evolve


def test_advance_the_line_beats_spreading_f29():
    """f29: advancing the started line (evolve Drakloak) out-values a spread attach onto a bare base."""
    fx, d, evolve = _shadows("dragapult_ex", "dp_charge_the_line_f29")
    assert evolve[fx["correct"][0]] > 0
    # the evolve out-scores every non-evolve option (the spread attach it should beat)
    non_evolve = [d.options[i].score for i, o in
                  enumerate(fx["obs"]["select"]["option"]) if o.get("type") != 9]
    assert evolve[fx["correct"][0]] >= max(non_evolve, default=0.0), evolve
