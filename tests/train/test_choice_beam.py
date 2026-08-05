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
def test_the_item3_MARGIN_telemetry_at_every_width_the_frame_can_support(probes):
    """**Issue #263 § *Beam-quality package* item 3, and the criterion it discharges** — *"rank at
    1-ply ordering relative to `k`, and score margin to the k-th candidate."*

    **Rank: 1 on both frames, in both modes**, so the line survives any `k >= 1`. That is the whole
    of the rank half.

    **Margin: reported as a CURVE, because `k` is not derived anywhere.** Neither Issue #263 nor Issue
    #392 fixes a beam width, so quoting one figure at an undefended `k` would report the caller's
    choice as a property of the frame. `margin_by_k` therefore carries every width the menu actually
    supports, and the width at which it stops is itself the finding.

    * **f35 discharges the criterion.** Two scored candidates, so `k=2` is real: the margin to the
      2nd candidate is **0.001125 unexpanded** and **0.002985 expanded** — expansion widens the line's
      lead over its rival by **2.65x**. That is exactly the demonstration the criterion asks for.
    * **f32 cannot, and the reason is coverage rather than ordering.** Its menu scores ONE candidate
      (3 refused, 1 terminal), so no `k >= 2` margin exists to measure at any width. A refusal is not a
      pruned option — `must_expand` makes it the always-expand path — so this is a fact about how much
      of a Trainer-heavy menu the apply seam can price at this commit, and it will become computable
      when that coverage grows rather than when Issue #385's composer lands.

    Pinned as numbers so a commit that widens seam coverage turns this red at the line that stopped
    being true, instead of leaving a stale claim in prose."""
    f32, f35 = probes["f32"], probes["f35"]
    for report in (f32, f35):
        assert report["unexpanded"]["rank"] == 1 and report["expanded"]["rank"] == 1, report

    assert f35["expanded"]["scored"] == 2, f35
    assert f35["unexpanded"]["margin_by_k"][2] == pytest.approx(0.001125, abs=1e-6)
    assert f35["expanded"]["margin_by_k"][2] == pytest.approx(0.002985, abs=1e-6)
    assert f35["expanded"]["margin_by_k"][2] > f35["unexpanded"]["margin_by_k"][2] * 2

    assert f32["expanded"]["scored"] == 1, f32
    assert f32["expanded"]["refused"] == 3, f32
    assert list(f32["expanded"]["margin_by_k"]) == [1], f32     # no k >= 2 exists on this menu


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
