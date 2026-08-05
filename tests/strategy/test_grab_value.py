"""The GRAB decider's equation (`common/grab_value.py`, ADR-0121 / Issue #406).

Pure arithmetic over resolved board facts — no engine, no obs, no Pilot — the seam every per-seam
equation in this repo is tested at. Prior art for the style: `test_deploy_value.py` (ADR-0086),
`test_evolve_value.py` (ADR-0070), `test_promote_retreat_value.py` (ADR-0100).

Two properties carry the design and nothing else in the suite would catch either:

* `test_the_add_marginal_is_dimensionless` — the whole currency argument is that the Worth points
  CANCEL in a ratio. A regression that "simplified" the ratio into a raw magnitude would leave every
  number plausible and every other test green.
* `test_candidate_ordering_is_invariant_to_the_band` — acceptance criterion 3. A `_TO_HAND` menu is
  homogeneous, so the band cannot change WHICH candidate wins; asserting that is what lets the band
  be pinned by preservation rather than derived.
"""
from __future__ import annotations

import pytest

from common import currency
from common.grab_value import GrabInputs, grab_value


# ── composition ──────────────────────────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-GRAB-0001")
def test_a_grab_that_covers_nothing_is_worth_nothing():
    """The floor matters as much as the ceiling. A candidate whose need my hand already covers must
    land at exactly 0.0 — that is what lets the single-pick take-fewer bar and `_greedy_grab`'s
    ``<= 0`` decline it, and it is the reading a one-sided rung ladder could never express (a rung
    that does not fire is silent, which is indistinguishable from a rung that has not been written)."""
    assert grab_value(GrabInputs(add_marginal=0.0)).total == 0.0


@pytest.mark.req("REQ-GRAB-0001")
def test_a_full_yardstick_marginal_is_worth_the_whole_band():
    """The composition, end to end: a candidate contributing the ceiling on one card's assignment
    contribution (`DEPLOY_WORTH_SCALE`) reads relevance 1.0 and crosses at exactly `DEPLOY_BAND`."""
    v = grab_value(GrabInputs(add_marginal=currency.DEPLOY_WORTH_SCALE))
    assert v.add_relevance == pytest.approx(1.0)
    assert v.total == pytest.approx(currency.DEPLOY_BAND)


@pytest.mark.req("REQ-GRAB-0001")
def test_the_marginal_saturates_at_the_yardstick():
    """One freakishly large marginal cannot swamp the damage-native tactical legs it sums beside."""
    huge = grab_value(GrabInputs(add_marginal=currency.DEPLOY_WORTH_SCALE * 50))
    assert huge.add_relevance == pytest.approx(1.0)
    assert huge.total == pytest.approx(currency.DEPLOY_BAND)


@pytest.mark.req("REQ-GRAB-0001")
def test_the_working_is_legible_because_the_decision_gate_is_ruled_by_reading_it():
    """A bare total would make a Decision-Gate flip unrulable — the human needs to see WHICH leg
    moved. One leg today, and the dict shape is what keeps a second one from arriving unannounced."""
    assert grab_value(GrabInputs(add_marginal=15.0)).working() == {
        "add_relevance": pytest.approx(0.5), "total": pytest.approx(0.5 * currency.DEPLOY_BAND)}


# ── the currency property the whole design rests on ──────────────────────────────────────────────


@pytest.mark.req("REQ-GRAB-0002")
def test_the_add_marginal_is_dimensionless(monkeypatch):
    """**The load-bearing property.** The leg is `marginal / DEPLOY_WORTH_SCALE`, so the Worth POINTS
    CANCEL — re-banding every tier by a constant factor must leave the grab score untouched, because
    both the marginal and the yardstick move together.

    This is why the yardstick is read from `currency` at call time rather than bound at import, and
    why `worth_relevance` lives in `currency` at all: the deploy equation's identical test re-points
    the same constant, and two private copies of the ratio would let one of them go stale."""
    v1 = grab_value(GrabInputs(add_marginal=15.0))
    monkeypatch.setattr(currency, "DEPLOY_WORTH_SCALE", currency.DEPLOY_WORTH_SCALE * 7.0)
    v2 = grab_value(GrabInputs(add_marginal=15.0 * 7.0))
    assert v2.total == pytest.approx(v1.total)
    assert v2.add_relevance == pytest.approx(v1.add_relevance)


@pytest.mark.req("REQ-GRAB-0002")
def test_candidate_ordering_is_invariant_to_the_band(monkeypatch):
    """**Acceptance criterion 3.** A `_TO_HAND` menu is HOMOGENEOUS — every option is a grab, and the
    equation never competes against an attack or against `End`, because a follow-up select is not
    `_MAIN`. So the band cannot change which candidate wins; it only sets the units the winner's
    margin is quoted in.

    That is what lets `DEPLOY_BAND` be pinned by preservation rather than derived at this seam. Any
    POSITIVE band must give the same order, so the test sweeps several rather than checking one."""
    marginals = [0.0, 1.5, 7.0, 7.0, 22.0, 30.0]

    def order_at(band):
        monkeypatch.setattr(currency, "DEPLOY_BAND", band)
        scored = [grab_value(GrabInputs(add_marginal=m)).total for m in marginals]
        return sorted(range(len(marginals)), key=lambda i: (-scored[i], i))

    baseline = order_at(currency.DEPLOY_BAND)
    for band in (0.5, 1.0, 25.0, 100.0, 1e4):
        assert order_at(band) == baseline


@pytest.mark.req("REQ-GRAB-0002")
def test_the_grab_never_speaks_against_taking_a_card():
    """A DEPLOY marginal is signed — a body worth less than what it displaces is an active mistake.
    A GRAB marginal cannot be: `keep_v2` is ``V(superset) - V(subset)`` over a monotone assignment.

    That is a deliberate limit rather than an oversight. What a card COSTS to take — it thins the
    deck, and it must then be held — is the take-fewer bar's jurisdiction, and the two must not both
    charge it. The equation is therefore floored at 0 by its own input's range, and this test records
    the contract so a later "let it go negative" change has to argue with the take-fewer bar."""
    assert grab_value(GrabInputs(add_marginal=0.0)).total == 0.0
    assert all(grab_value(GrabInputs(add_marginal=m)).total >= 0.0
               for m in (0.0, 0.1, 5.0, 30.0, 900.0))
