"""The **State Value** contract (`common/state_value.py`, POC-T0 / Issue #259, ADR-0092 §4-T0).

T0 freezes the contract; T3 (Issue #262) fills in the equations. So what is testable NOW is exactly
what T0 delivers: the coverage map, the double-counting rule, the unit basis, and the fact that no
entry point returns a plausible number before it means one.

The two tests that matter most here are `test_no_fact_is_priced_twice` and
`test_no_fact_is_priced_by_nobody`. They are the executable form of T0's headline rule, and the rule
earned its enforcement — an empty Bench under a knock-outable Active reached the draft sound-rule
whitelist through THREE mechanisms simultaneously (a terminal rung, an order filter and a +60
weight), and nothing about writing that list prompted the question (ADR-TEMP-259c).

Prior art for the style: `test_deploy_value.py` (a value equation asserted as plain arithmetic, no
engine / obs / Pilot) and `test_currency.py` (a constant asserted against its derivation rather than
pinned as a literal).
"""
from __future__ import annotations

import pytest

from common import state_value as sv


# ── the coverage map — T0's headline rule, executable ─────────────────────────────────────────────


@pytest.mark.req("REQ-VALUE-0001")
def test_no_fact_is_priced_twice():
    """`every board fact enters through exactly ONE term family` (ADR-0092 §4-T0).

    A fact priced by two families is counted twice in the scalar, and the error is invisible: the
    number still looks plausible, which is precisely how the empty-Bench fact acquired three guards
    without anyone noticing while writing them down."""
    assert sv.double_counted() == []


@pytest.mark.req("REQ-VALUE-0001")
def test_no_fact_is_priced_by_nobody():
    """The rule's other half. A play that changes state and that no family reads prices 0 — and a
    silent 0 is indistinguishable from a correct 0. `does_not_read` is what gives a gap an address:
    a fact one family disclaims and no family claims is a hole, reported here rather than discovered
    as a mis-priced decision three tracks later."""
    assert sv.registry_gaps() == []


@pytest.mark.req("REQ-VALUE-0001")
def test_the_registry_holds_exactly_the_six_families_the_plan_names():
    """The families are ADR-0092 §4-T0's, and the set is the contract other tracks build against —
    T3 implements these and no others, and `working` carries exactly these keys."""
    assert [f.name for f in sv.REGISTRY] == [
        "prize_race", "survival", "threat", "readiness", "hand", "development"]
    assert set(sv.FAMILIES) == {f.name for f in sv.REGISTRY}


@pytest.mark.req("REQ-VALUE-0001")
def test_every_family_states_what_it_refuses_as_well_as_what_it_prices():
    """A family declaring no `does_not_read` has opted out of the gap-detection above — it can never
    contribute a named hole, so the coverage map would silently weaken as families were added."""
    for f in sv.REGISTRY:
        assert f.reads, f.name
        assert f.does_not_read, f.name
        assert f.composition.strip(), f.name


# ── the unit basis ────────────────────────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-VALUE-0002")
def test_the_worth_scaffold_is_absent_until_T3_authors_it_with_its_reasoning():
    """T0 approves the MECHANISM and its bindings, never a number (ADR-TEMP-259d). A default value
    here would be the authored constant arriving without the reconciliation that makes it honest."""
    assert sv.POC_WORTH_PRIZE_RATE is None


@pytest.mark.req("REQ-VALUE-0002")
def test_the_worth_scaffold_never_migrates_into_currency():
    """`common/currency.py`'s contract is "DERIVED and never tuned"; this constant is the opposite,
    and ADR-0080's underivability measurement stands as the historical record of what was true.

    Asserted rather than trusted to review, because the migration is the tempting one: a second
    consumer arrives, someone hoists it "where the other rates live", and the module that promises
    derivation is quietly holding an invention."""
    from common import currency
    assert not hasattr(currency, "POC_WORTH_PRIZE_RATE")
    assert not hasattr(currency, "WORTH_DAMAGE_RATE"), (
        "ADR-0080 ran the anchor gate and it FAILED — the constant is absent BY DESIGN, not pending")


# ── inertness — T0 ships a contract, not an implementation ────────────────────────────────────────


@pytest.mark.req("REQ-VALUE-0003")
def test_every_scoring_entry_point_refuses_rather_than_returning_a_plausible_zero():
    """0.0 is exactly what a correct-but-neutral position scores, so a stub returning it would make
    an unimplemented build read as a working one right up until the ladder disagreed. Every entry
    point fails loud instead — the same `fail-loud, never guess` discipline cgpy applies to a
    def-less card (`UnsupportedCard`)."""
    with pytest.raises(NotImplementedError):
        sv.state_value(object())
    with pytest.raises(NotImplementedError):
        sv.prize_race(my_prizes_remaining=6, their_prizes_remaining=6)
    with pytest.raises(NotImplementedError):
        sv.survival([(1.0, 2)])
    with pytest.raises(NotImplementedError):
        sv.threat([1.0])
    with pytest.raises(NotImplementedError):
        sv.readiness([(1.0, 0.5, 1.0)])
    with pytest.raises(NotImplementedError):
        sv.hand(assignment_coverage=0.0, re_access=0.0, hand_worth=0.0)
    with pytest.raises(NotImplementedError):
        sv.development(deploy_marginal=0.0, evolve_marginal=0.0, bench_slot_price=0.0,
                       line_topology=0.0)


@pytest.mark.req("REQ-VALUE-0003")
def test_the_module_reaches_for_no_engine_no_obs_and_no_pilot():
    """The seam, asserted at import: `state_value` takes a StateModel and the families take plain
    numbers, so nothing here may pull in the Pilot, the native engine or cgpy. A value equation that
    can reach for the board it was handed facts about stops being testable with numbers."""
    import inspect
    src = inspect.getsource(sv)
    for forbidden in ("from cg import", "import cgpy", "from common.pilot", "import pilot"):
        assert forbidden not in src, forbidden
