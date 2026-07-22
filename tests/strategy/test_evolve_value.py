"""Evolve-value shadow oracle (common/evolve_value.py) — docs/plans/evolve-valuation-grill-spec.md.

Increment 1: the ability-income Δ. The oracle is emitted REPORTING-ONLY on `OptionTrace.evolve_shadow`
(not in `score`), so these assert the SIGN of the shadow value on the corpus targets — the design proof
that must hold before any swap — while the live decision is still driven by the rungs (the corpus
family's `xfail` targets stay xfail).
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


def _decide(agent, fixture):
    fx = _fixture(fixture)
    d = _pilot(agent).explain(fx["obs"])
    opts = fx["obs"]["select"]["option"]
    return fx, d, opts


def _evolve_option_indices(opts):
    return [i for i, o in enumerate(opts) if o.get("type") == 9]   # 9 = OptionType.EVOLVE


def test_income_on_evolve_scores_positive_shadow_f40():
    """86090164 f40: Dunsparce(no draw) → Dudunsparce(Run Away Draw) turns a draw engine ON → the
    shadow income Δ is POSITIVE. The evolve is the top-scoring EVOLVE by the shadow."""
    fx, d, opts = _decide("dragapult_ex", "dp_evolve_the_draw_engine_f40")
    ei = _evolve_option_indices(opts)
    assert ei, "expected an EVOLVE option in f40"
    evolve_shadows = {i: d.options[i].evolve_shadow for i in ei}
    # the correct option (evolve Dunsparce->Dudunsparce) carries a positive income shadow
    assert d.options[fx["correct"][0]].evolve_shadow > 0, evolve_shadows


def test_income_off_evolve_scores_negative_shadow_f35():
    """86091435 f35: Drakloak(Recon dig) → Dragapult(no draw) turns the engine OFF → the shadow income
    Δ is NEGATIVE (a hold pressure), even though the rung `evolve-into-wincon` still picks it live."""
    fx, d, opts = _decide("dragapult_ex", "dp_hold_evolve_until_typed_ready_f35")
    ei = _evolve_option_indices(opts)
    assert ei, "expected an EVOLVE option in f35"
    # the chosen (rung-driven) option is the Drakloak->Dragapult evolve; its income shadow is negative
    assert d.options[d.chosen[0]].evolve_shadow < 0, {i: d.options[i].evolve_shadow for i in ei}


def test_shadow_is_zero_off_evolve_and_inert():
    """The shadow is 0.0 on non-EVOLVE options and REPORTING-ONLY — the live pick is unchanged
    (f35's rung-driven evolve is still chosen; the corpus family's xfail targets stay xfail)."""
    fx, d, opts = _decide("dragapult_ex", "dp_hold_evolve_until_typed_ready_f35")
    non_evolve = [i for i, o in enumerate(opts) if o.get("type") != 9]
    assert all(d.options[i].evolve_shadow == 0.0 for i in non_evolve)
    assert d.chosen == fx["chosen"]   # still the rung's (wrong) pick — shadow did not drive
