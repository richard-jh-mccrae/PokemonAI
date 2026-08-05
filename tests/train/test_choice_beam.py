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
    """**The defect, measured — and the measurement is sharper than the issue's own wording.**

    Issue #392 calls a retreat's 1-ply delta a *near*-zero. On both acceptance frames it is **exactly
    0.0**: `board_delta._retreat` writes ``allowance_retreat_used`` alone, and no `state_value` family
    reads the retreat allowance, so the delta is not small — there is nothing there. Issue #263's
    amendment rules what that means: *"a 0 delta at ordering time means **never explored**, not
    undervalued."*"""
    for name, report in probes.items():
        assert report["deferred_target_option"] is not None, name
        assert report["unexpanded"]["shape"] == "point", name
        assert report["unexpanded"]["delta"] == 0.0, (name, report["unexpanded"])


@pytest.mark.req("REQ-APPLY-0002")
def test_expansion_makes_the_same_option_a_real_positive_comparable_number(probes):
    """The other half: armed, the option resolves to a choice node and its 1-ply delta is the **max**
    over the classes — strictly positive on both frames, where it was exactly nothing.

    Measured at this commit: **f32 +0.00075 prizes over 2 classes**, **f35 +0.00186 over 4**. The
    magnitudes are small because a retreat moves bodies rather than prizes and the leaf is
    prize-denominated; what matters for the pruning defect is that the number is no longer 0, because
    a 0 is what the beam reads as *never explore this*."""
    for name, report in probes.items():
        assert report["expanded"]["shape"].startswith("choice["), name
        assert report["expanded"]["delta"] > 0.0, (name, report["expanded"])
        assert report["expanded"]["delta"] > report["unexpanded"]["delta"], name


@pytest.mark.req("REQ-APPLY-0002")
def test_the_margin_to_the_kth_candidate_is_UNDEFINED_here_and_that_is_the_finding(probes):
    """**The acceptance criterion this build does NOT discharge, asserted so it cannot be mistaken for
    one it does.**

    Issue #392 asks that f32 and f35 *"reach the beam at the chosen width, demonstrated by § Beam-quality
    package item-3 margin telemetry — rank at 1-ply ordering relative to `k`, and score margin to the
    k-th candidate."* The rank half is measurable and is **1 on both frames**. The margin half is not:
    at `k=3` there are fewer than three SCORED candidates on either menu, because the apply seam refuses
    most of the rest (f32: 1 scored / 3 refused / 1 terminal; f35: 2 scored / 2 refused / 1 terminal).

    A refusal is not a pruned option — `must_expand` makes it the always-expand path — so the shortfall
    is not a defect in the ordering. It is a fact about apply-seam COVERAGE at this commit, and it means
    the margin telemetry becomes computable when the seam covers more of a Trainer-heavy menu, not when
    the composer lands. Pinned rather than described so that a later commit which widens coverage turns
    this test red at the line that stopped being true, instead of leaving a stale claim in prose."""
    for name, report in probes.items():
        assert report["unexpanded"]["rank"] == 1, (name, report["unexpanded"])
        assert report["expanded"]["rank"] == 1, (name, report["expanded"])
        assert report["expanded"]["scored"] < report["expanded"]["k"], (name, report["expanded"])
        assert report["expanded"]["margin_to_kth"] is None, (name, report["expanded"])
        assert report["expanded"]["refused"] > 0, (name, report["expanded"])


@pytest.mark.req("REQ-APPLY-0002")
def test_the_expansion_costs_are_reported_against_BOARD_EXPECTATIONS_OWN_figures():
    """The cost criterion, in the units `board_expectation.BRANCH_CAP`'s derivation uses — leaf P95
    **4.46 ms**, per-decision P95 **53.5 ms**, grader floor **>= 3.0 s** — and NOT the stale 6.4 ms /
    79 ms in Issue #392's original body.

    The assertion is on the CLASS COUNT rather than on a millisecond figure, deliberately: the class
    count is a property of the board and reproducible on any box, while wall clock moves ~10%
    run-to-run and ~45% between boxes, which is the same argument `board_expectation`'s header makes
    for anchoring its cap to the menu width instead of the clock. Both frames enumerate far under the
    cap, so the expansion costs 1 and 3 extra leaf evaluations respectively — against a per-decision
    budget of 12."""
    for name in sorted(choice_beam.FRAMES):
        cost = choice_beam.cost_report(name)
        assert cost["classes"] >= 1, (name, cost)
        assert cost["truncated"] == 0, (name, cost)
        assert cost["classes"] <= cost["cap"], (name, cost)
        assert cost["extra_leaves_vs_point"] == cost["classes"] - 1, (name, cost)
