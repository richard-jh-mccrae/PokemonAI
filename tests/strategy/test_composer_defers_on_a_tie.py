"""The composer must not decide what its own numbers say it has no view on — ADR-0131 (Issue #386).

`selection_key` always returns something. That is correct as a tie-break *within* an Option
Equivalence Class — indistinguishable options are one decision (ADR-0091), so which member wins is a
tie about nothing. It is wrong between genuinely different actions, because there a tied score is the
composer REPORTING that both end the turn in the same place, and *"they end the same"* is not the
same claim as *"take this one"*.

`sound_rules.information-before-commitment` is the standing ruling on that case and says outright
that it is unreachable from the end state: *"both orders reach the same end state, so no function of
that state separates them (ADR-0095 decision 3)."* A composer is a function of the end state. So on
a tie the structural sequencer decides, and `_composer_line` defers — the fourth of its defers, and
the same kind as the three it already documents.

**Measured rather than assumed, because a defer that fires everywhere hollows out the swap:**

    MAIN single-pick corpus frames    164
      composer decides                104   63.4%
      tie-defer                        43   26.2%
      other defer (no chosen / gap)    17   10.4%

and the Decision Gate's unruled REGRESSION count goes 58 -> 44.
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
def test_the_composer_really_does_tie_every_option_on_the_anchor_frame(anchor):
    """The premise, measured. Without this the test below could pass because the composer AGREED
    with the sequencer, which would prove nothing about the defer.

    Seven of ten options price at exactly 0.0 here — the ruled Pokégear 3.0, both Crushing Hammers,
    both Tools, an attach and End. That is not a near-tie needing a floor; it is the same number."""
    fx, pilot, _dec = anchor
    from common import composer as cp
    obs, sel = fx["obs"], fx["obs"]["select"]
    pilot._board(obs, sel)
    model = pilot._leaf_state_model(obs, int((obs.get("current") or {}).get("yourIndex") or 0))
    order = dict(cp.compose(model, sel["option"], shed=pilot.cost_shed_indices).order)
    ruled = fx["correct"][0]
    top = max(order.values())
    tied = [i for i, d in order.items() if d == top]
    assert ruled in tied, f"the ruled option is not among the tied top: {order}"
    assert len(tied) > 1, f"nothing ties here, so this frame does not exercise the defer: {order}"


@pytest.mark.req("REQ-PLANNER-0012")
def test_the_planner_defers_and_says_so_in_the_trace(anchor):
    """The defer is visible, not silent. A `composer` telemetry block that showed a chosen line on a
    frame the composer abstained from would make the abstention unauditable in a live trace."""
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
    """The other direction, and the one that matters for whether the swap still means anything.

    An abstention rule is only worth having if it abstains SOMETIMES. Asserted on a frame where the
    composer's margin is real, so a future widening of the tie test — an epsilon band instead of the
    float-noise floor, say — turns this red rather than quietly handing every sub-epsilon decision
    back to the ladder."""
    fx = json.loads((FIXTURES / "pr_whether_should_retreat_f37.json").read_text(encoding="utf-8"))
    pilot = _pilot("dragapult_ex")
    pilot._turn_plan = None
    pilot._composer_trace = None
    dec = pilot.explain(fx["obs"])
    trace = pilot._composer_trace or {}
    assert not trace.get("tied_first_steps"), (
        "the defer fired on a frame whose composer margin is 2.43 prizes — the tie test has stopped "
        "being a float-noise floor and become a band")
    assert getattr(getattr(dec, "planned", None), "ranked_by", None) == "composer"