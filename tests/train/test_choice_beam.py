"""`train.probes.choice_beam` — the beam-margin instrument, and the two acceptance frames it measures
(POC-T4/5, Issue #392; Issue #263 § *Beam-quality package* item 3).

`tests/strategy/test_board_choice.py` asserts the choice node's arithmetic on hand-built boards, which
is the right seam for a rules claim. It cannot make the claim this file makes: those fixtures carry
`CardStat`s with no attacks, so `state_value`'s families read almost nothing off them and the leaf
cannot tell one promoted body from another. The defect Issue #392 exists to delete is about what the
LEAF sees, so it has to be measured on a real board with real card data — a built Pilot, engine-backed.

The frames are Issue #263's own acceptance corpus, both retreat-to-wall lines, and the retired
`retreat-to-wall-the-line` +30 rung existed precisely because the flat-scored world could not otherwise
reach them.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from train.probes import choice_beam                     # noqa: E402


@pytest.fixture(scope="module")
def probes():
    return {name: choice_beam.probe(name) for name in sorted(choice_beam.FRAMES)}


@pytest.mark.req("REQ-APPLY-0002")
def test_an_unexpanded_retreat_prices_at_EXACTLY_zero_on_both_acceptance_frames(probes):
    """Measured: a retreat's 1-ply delta is EXACTLY 0.0 on both acceptance frames, because `_retreat`
    writes `allowance_retreat_used` alone and no `state_value` family reads the retreat allowance."""
    for name, report in probes.items():
        assert report["deferred_target_option"] is not None, name
        assert report["unexpanded"]["shape"] == "point", name
        assert report["unexpanded"]["delta"] == 0.0, (name, report["unexpanded"])


@pytest.mark.req("REQ-APPLY-0002")
def test_expansion_makes_the_same_option_a_real_positive_comparable_number(probes):
    """Armed, the option resolves to a choice node and its 1-ply delta is the MAX over the classes —
    strictly positive where it was nothing, and a 0 is what the beam reads as *never explore this*."""
    for name, report in probes.items():
        assert report["expanded"]["shape"].startswith("choice["), name
        assert report["expanded"]["delta"] > 0.0, (name, report["expanded"])
        assert report["expanded"]["delta"] > report["unexpanded"]["delta"], name


@pytest.mark.req("REQ-APPLY-0002")
def test_the_item3_MARGIN_telemetry_at_every_width_the_frame_can_support(probes):
    """Issue #263 item 3 — rank at 1-ply ordering relative to `k`, and margin to the k-th candidate.
    The margin is a CURVE because no `k` is derived anywhere; the width it stops at is the finding."""
    f35 = probes["f35"]
    assert f35["unexpanded"]["rank"] == 1 and f35["expanded"]["rank"] == 1, f35

    assert f35["expanded"]["scored"] == 2, f35
    assert f35["unexpanded"]["margin_by_k"][2] == pytest.approx(0.001125, abs=1e-6)
    assert f35["expanded"]["margin_by_k"][2] == pytest.approx(0.002985, abs=1e-6)
    assert f35["expanded"]["margin_by_k"][2] > f35["unexpanded"]["margin_by_k"][2] * 2

    f32 = probes["f32"]
    assert f32["unexpanded"]["rank"] == 2 and f32["expanded"]["rank"] == 2, f32
    assert f32["expanded"]["scored"] == 2, f32
    assert f32["expanded"]["refused"] == 2, f32
    assert list(f32["expanded"]["margin_by_k"]) == [1, 2], f32   # k >= 2 now exists on this menu
    assert f32["expanded"]["margin_by_k"][2] == 0.0, f32          # k=2: retreat IS the 2nd candidate
    assert f32["unexpanded"]["margin_by_k"][1] < 0.0, f32         # k=1: the now-visible evolve leads


@pytest.mark.req("REQ-APPLY-0002")
def test_the_expansion_costs_are_reported_against_BOARD_EXPECTATIONS_OWN_figures():
    """The cost criterion, in `board_expectation.BRANCH_CAP`'s own units. Asserted on the CLASS COUNT
    rather than a millisecond figure: the count is a board property, wall clock moves ~45% per box."""
    for name in sorted(choice_beam.FRAMES):
        cost = choice_beam.cost_report(name)
        assert cost["classes"] >= 1, (name, cost)
        assert cost["truncated"] == 0, (name, cost)
        assert cost["classes"] <= cost["cap"], (name, cost)
        assert cost["extra_leaves_vs_point"] == cost["classes"] - 1, (name, cost)
