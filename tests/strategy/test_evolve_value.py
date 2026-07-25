"""Evolve DECIDER on real frames (common/evolve_value.py) — ADR-0070, #140.

The equation's per-option TERM row, read off `OptionTrace.evolve_working` with the decider's
kill-switch forced ON. These assert it RANKS the corpus frames correctly — the design proof that
must hold before the `baseline_evolution` rungs are deleted. The algebra itself is pinned at the
pure-function seam (`test_evolve_decider.py`); this is the same claims through the real Pilot.

Card facts verified at source (data/EN_Card_Data.csv): Drakloak (120) HP 90, Dragon Headbutt {R}{P}
70, Recon Directive "top 2, put 1 in hand"; Dragapult ex (121) HP 320, Phantom Dive {R}{P} 200 —
the IDENTICAL cost that makes the doctrine derive.
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
    """(fixture, decision, {option index -> the evolve decider's total}) with the switch forced ON."""
    fx = json.loads((FIXTURES / f"{fixture}.json").read_text(encoding="utf-8"))
    pilot = _pilot(agent)
    pilot.evolve_value = True                    # price the frames even while PROFILE ships it OFF
    d = pilot.explain(fx["obs"])
    opts = fx["obs"]["select"]["option"]
    evolve = {i: (d.options[i].evolve_working or {}).get("tactical", 0.0)
              for i, o in enumerate(opts) if o.get("type") == 9}
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


@pytest.mark.xfail(strict=True, reason="FLIP AWAITING USER RULING (#140 swap protocol, ADR-0069 §8): "
                   "the decider prefers evolving the BENCHED bare Dreepy (37.5) over the energized "
                   "ACTIVE one (30.0). The Active body is doomed either way (ko 1 -> 1), so its evolve "
                   "buys only tempo — a real 70 swing; the benched body's evolve crosses the snipe "
                   "threshold (70 -> 90 HP, ko 1 -> 3) and banks survival. Rule: is the rescue right, "
                   "or is the forward payoff over-credited on a body two turns from arming?")
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
    # The DECISION is the claim. Since the attach swap (#139, ADR-0069) an attach's score is a real
    # damage currency rather than a flat rung, so a build step can out-NUMBER an evolve rung — and it
    # no longer needs to lose on score to lose the turn: free development is tier 0 and the
    # irreversible attach is tier 2, so the evolve is taken first and the attach follows.
    assert d.chosen == fx["correct"], (
        f"the evolve lost the turn to a non-evolve option: chosen={d.chosen}, correct={fx['correct']}")
