"""The composer must not decide what its own numbers say it has no view on — ADR-0131 (Issue #386).

`selection_key` always returns something: correct as a tie-break *within* an Option Equivalence Class
(ADR-0091), wrong between genuinely different actions, where a tied score REPORTS that both end the
turn in the same place. `sound_rules.information-before-commitment` rules that case unreachable from
the end state (ADR-0095 decision 3), and a composer is a function of the end state — so on a tie the
structural sequencer decides and `_composer_line` defers.
"""
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures" / "corrections"
ANCHOR = "ms_information_before_commitment_f11"


def _pilot(agent):
    from train.tune import _build_pilot          # `tools/` is on the path via tests/conftest.py
    p = _build_pilot(agent)[0]
    p._planning = False
    return p


@pytest.fixture(scope="module")
def anchor():
    fx = json.loads((FIXTURES / f"{ANCHOR}.json").read_text(encoding="utf-8"))
    pilot = _pilot("mega_starmie")
    pilot._turn_plan = None
    pilot._composer_trace = None
    return fx, pilot, pilot.explain(fx["obs"])


@pytest.mark.req("REQ-PLANNER-0012")
def test_the_composer_ties_the_scored_options_without_pricing_the_unknown_one(anchor):
    """The scored options tie; the ruled unknown remains a sentinel, never a numeric zero."""
    fx, pilot, _dec = anchor
    from common import composer as cp
    obs, sel = fx["obs"], fx["obs"]["select"]
    pilot._board(obs, sel)
    model = pilot._leaf_state_model(obs, int((obs.get("current") or {}).get("yourIndex") or 0))
    result = cp.compose(model, sel["option"], shed=pilot.cost_shed_indices)
    order = dict(result.order)
    ruled = fx["correct"][0]
    assert result.fanned[ruled] is None and ruled not in order
    top = max(order.values())
    tied = [i for i, d in order.items() if d == top]
    assert len(tied) > 1, f"nothing ties here, so this frame does not exercise the defer: {order}"


@pytest.mark.req("REQ-PLANNER-0012")
def test_the_planner_defers_and_says_so_in_the_trace(anchor):
    """A telemetry block showing a chosen line on an abstained frame is unauditable in a live trace."""
    _fx, pilot, _dec = anchor
    trace = pilot._composer_trace or {}
    assert trace.get("tied_first_steps"), (
        "the planner committed a composer line on a frame where its own scores tie — or the trace "
        "no longer records the abstention, which is the same problem one layer down")
    assert "chosen" not in trace, (
        "a deferred decision must not also publish a chosen line; a reader cannot tell which one "
        "the agent acted on")


@pytest.mark.req("REQ-PLANNER-0012")
def test_the_structural_sequencer_gets_the_turn_and_plays_the_ruled_dig(anchor):
    """What the defer is FOR. ADR-0095's falsifiable prediction, restored end-to-end."""
    fx, _pilot, dec = anchor
    assert list(dec.chosen) == list(fx["correct"])


@pytest.mark.req("REQ-PLANNER-0012")
def test_the_defer_does_not_fire_where_the_composer_has_a_real_view():
    """An abstention rule is only worth having if it abstains SOMETIMES. On a frame with a real
    margin, so widening the tie test into an epsilon band turns this red rather than deferring all."""
    fx = json.loads((FIXTURES / "ml0705_ppp_cant_attack_f14.json").read_text(encoding="utf-8"))
    pilot = _pilot("mega_lucario")
    pilot._turn_plan = None
    pilot._composer_trace = None
    dec = pilot.explain(fx["obs"])
    trace = pilot._composer_trace or {}
    assert not trace.get("tied_first_steps"), (
        "the defer fired on a frame with a positive composer plan — the tie test has stopped being a "
        "float-noise floor and become a band")
    assert getattr(getattr(dec, "planned", None), "ranked_by", None) == "composer"
