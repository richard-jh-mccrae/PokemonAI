"""The **apply-seam** contract (`common/apply_option.py`, POC-T0 / Issue #259, ADR-0098).

T0 freezes the contract; T4 (Issue #263) implements the transitions. So what is testable now is the
option-kind table, the terminal boundary, the Expectation shape and — most importantly — that
nothing here returns a plausible answer before it means one.

`test_an_unimplemented_transition_refuses_rather_than_returning_the_model_unchanged` is the one that
matters. An identity stub prices every play at exactly 0.0 under differencing, and 0.0 is a real
answer, so an unimplemented build would read as "every play is worthless" rather than as
"unimplemented" — and the planner would confidently decline everything.

Prior art for the style: `test_deploy_value.py` (a seam asserted as plain data in / plain data out)
and `tests/train/test_gates.py` (dict-in/value-out, no engine, no DLL, runs everywhere).
"""
from __future__ import annotations

import pytest

from common import apply_option as ao
from common.strategy.context import _ABILITY, _ATTACH, _ATTACK, _END, _EVOLVE, _PLAY, _RETREAT


# ── the option-kind table ─────────────────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-APPLY-0001")
def test_the_seam_declares_exactly_the_kinds_the_planner_sequences():
    """ADR-0092 §4-T0 item 3 names them: trainer play, attach, evolve, bench/deploy,
    retreat/promote. Bench/deploy and promote arrive as PLAY and RETREAT at the engine level, so the
    engine's four option types are the table — the seam speaks the engine's vocabulary
    (`src/cg/api.py`), never a second spelling of it."""
    assert ao.TRANSITION_KINDS == frozenset({_PLAY, _ATTACH, _EVOLVE, _RETREAT})


@pytest.mark.req("REQ-APPLY-0001")
def test_attack_and_end_are_terminal_and_nothing_else_is():
    """Both END the turn (`docs/rules.md` §3 — an attack ends your turn, 1 per turn), so the beam
    terminates on them. A transition kind leaking into this set would let the planner stop early;
    a terminal kind leaking out would let it sequence past the end of my own turn."""
    assert ao.TERMINAL_KINDS == frozenset({_ATTACK, _END})
    assert not (ao.TERMINAL_KINDS & ao.TRANSITION_KINDS)
    assert ao.is_terminal({"type": _ATTACK}) is True
    assert ao.is_terminal({"type": _END}) is True
    assert ao.is_terminal({"type": _ATTACH}) is False


@pytest.mark.req("REQ-APPLY-0001")
def test_an_undeclared_option_kind_is_REFUSED_not_treated_as_a_no_op():
    """The option vocabulary grows — an ABILITY at the main menu, a SKILL ordering. A seam with a
    default branch would price those as no-ops (exactly 0.0 under differencing) and the planner would
    decline them forever. Fail loud instead, the way cgpy refuses a def-less card."""
    with pytest.raises(ao.UnsupportedTransition):
        ao.transition_kind({"type": _ABILITY})
    with pytest.raises(ao.UnsupportedTransition):
        ao.is_terminal({"type": 999})


@pytest.mark.req("REQ-APPLY-0001")
def test_applying_a_terminal_option_is_an_error_not_an_unchanged_model():
    """There is no successor state to a turn-ender. Returning the model unchanged would silently let
    a beam sequence actions after the attack that ended the turn."""
    with pytest.raises(ValueError):
        ao.apply_option(object(), {"type": _ATTACK})


@pytest.mark.req("REQ-APPLY-0002")
def test_an_unimplemented_transition_refuses_rather_than_returning_the_model_unchanged():
    """The stub that matters. Under differencing an identity transition prices the play at exactly
    0.0 — a real, plausible answer — so an unimplemented build reads as a working one that thinks
    nothing is worth doing."""
    for kind in sorted(ao.TRANSITION_KINDS):
        with pytest.raises(NotImplementedError):
            ao.apply_option(object(), {"type": kind})


# ── the EXPECTATION shape ─────────────────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-APPLY-0003")
def test_a_complete_expectation_sums_to_one_and_a_capped_one_reports_its_truncation():
    """Branching is capped (the value is T4's; the seam promises the shape). A capped enumeration
    that read as a complete one would make an under-explored line look confidently valued — the
    "no silent caps" rule. The probability gap IS the truncation, so it cannot be hidden."""
    complete = ao.Expectation(classes=(ao.OutcomeClass(0.25), ao.OutcomeClass(0.75)))
    assert complete.total_probability == pytest.approx(1.0)
    assert complete.truncated == 0

    capped = ao.Expectation(classes=(ao.OutcomeClass(0.6),), truncated=3)
    assert capped.total_probability == pytest.approx(0.6)
    assert capped.truncated == 3


@pytest.mark.req("REQ-APPLY-0003")
def test_an_outcome_class_carries_its_option_equivalence_fingerprint():
    """Classes are enumerated by Option-Equivalence identity (ADR-0091), not card identity: two
    indistinguishable reveals are ONE outcome, so branching tracks the decisions a reveal poses
    rather than the cards it could name."""
    oc = ao.OutcomeClass(0.5, fingerprint=(7, 0, (("hand", 1121),)))
    assert oc.fingerprint == (7, 0, (("hand", 1121),))
    assert oc.model is None                       # filled by T4


@pytest.mark.req("REQ-APPLY-0003")
def test_an_expectation_defaults_to_empty_rather_than_to_a_certain_outcome():
    """A default of "one class at probability 1.0" would make an unpopulated Expectation read as a
    deterministic transition, which is the wrong fail direction for a stochastic effect."""
    assert ao.Expectation().classes == ()
    assert ao.Expectation().total_probability == 0.0


# ── the quarantine registry ───────────────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-APPLY-0004")
def test_nothing_is_quarantined_before_the_parity_lane_exists():
    """The registry the planner reads to refuse a diverging option kind (ADR-0098 decision 4).
    Empty until T4 wires the lane — and it lives beside the seam, because the SEAM is what diverges
    and more than one consumer (the planner, the coverage report, the telemetry line) must read one
    answer."""
    assert ao.quarantined_kinds() == frozenset()


# ── the seam stays engine-free ────────────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-APPLY-0002")
def test_the_module_never_reaches_for_an_engine():
    """The whole argument for this seam is that the engine is not on the runtime path. A stray
    `from cg import api` would both re-open that decision and map the native library into a suite
    that must run DLL-free."""
    import inspect
    src = inspect.getsource(ao)
    for forbidden in ("from cg import", "import cg.api", "import cgpy", "search_begin("):
        assert forbidden not in src, forbidden


@pytest.mark.req("REQ-APPLY-0002")
def test_the_seam_records_that_it_cannot_price_information_ordering():
    """Not decoration. A later track assuming the planner will discover information-first sequencing
    would ship an agent that commits before it digs — the exact `82225643|1|decision|11` failure.
    The limitation is written where an implementer reads it, not only in an ADR."""
    doc = ao.__doc__ or ""
    assert "cannot capture information value" in doc
    assert "same end state" in doc.lower()
