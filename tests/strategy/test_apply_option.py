"""The **apply-seam** contract (`common/apply_option.py`, POC-T0 / Issue #259, ADR-0098).

T0 freezes the contract; T4 (Issue #263) implements the transitions. So what is testable now is the
option-kind table, the terminal boundary, the refusal shape, the Expectation shape and — most
importantly — that nothing here returns a plausible answer before it means one.

Two tests carry the weight:

* `test_an_unimplemented_transition_refuses_rather_than_returning_the_model_unchanged` — an identity
  stub prices every play at exactly 0.0 under differencing, and 0.0 is a real answer, so an
  unimplemented build would read as a working one that thinks nothing is worth doing.
* `test_an_unmodellable_kind_returns_a_REFUSAL_not_a_silent_no_op` — the 2026-08-01 ordering
  amendment. The seam is now on the hot path at 1 ply for every option on the menu, so a kind it
  cannot model must be VISIBLE to the composer (always-expand) rather than priced at 0 delta
  (never-explore).

Prior art for the style: `test_deploy_value.py` (a seam asserted as plain data in / plain data out)
and `tests/train/test_gates.py` (dict-in/value-out, no engine, no DLL, runs everywhere).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from common import apply_option as ao
from common.strategy.context import (
    _ABILITY, _ATTACH, _ATTACK, _CARD, _DISCARD_IN_PLAY, _END, _ENERGY, _EVOLVE, _NO, _NUMBER, _PLAY,
    _RETREAT, _SKILL, _SPECIAL_CONDITION, _YES,
)

_API = Path(__file__).resolve().parents[2] / "src" / "cg" / "api.py"


def _engine_option_types() -> set[int]:
    """`OptionType`'s members, READ FROM `src/cg/api.py` rather than imported from it.

    Importing `cg.api` executes `from .sim import lib` and maps the native library — which this suite
    must not do (`CLAUDE.md`: the whole strategy suite runs DLL-free on both platforms). Parsing the
    enum block keeps the assertion anchored to the one authoritative store without paying that."""
    src = _API.read_text(encoding="utf-8-sig")
    block = src.split("class OptionType(IntEnum):", 1)[1].split("\nclass ", 1)[0]
    return {int(v) for v in re.findall(r"^\s{4}[A-Z_]+ = (\d+)", block, flags=re.M)}


# ── the option-kind table ─────────────────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-APPLY-0001")
def test_the_seam_declares_exactly_the_kinds_the_planner_sequences():
    """ADR-0092 §4-T0 item 3 names them: trainer play, attach, evolve, bench/deploy,
    retreat/promote. Bench/deploy and promote arrive as PLAY and RETREAT at the engine level, so the
    engine's four option types are the modelled set — the seam speaks the engine's vocabulary
    (`src/cg/api.py`), never a second spelling of it."""
    assert ao.TRANSITION_KINDS == frozenset({_PLAY, _ATTACH, _EVOLVE, _RETREAT})


@pytest.mark.req("REQ-APPLY-0001")
def test_the_kind_table_is_TOTAL_over_the_engines_option_vocabulary():
    """The 2026-08-01 ordering amendment: 1-ply differencing visits EVERY option on a live select
    menu, so a table covering only the mid-sequence kinds leaves the rest unclassified. Asserted
    against the engine enum itself rather than against a hand-copied list, because a hand-copied list
    is what the table would have to drift from to fail."""
    assert set(ao.KIND_COVERAGE) == _engine_option_types()
    assert set(ao.KIND_COVERAGE.values()) <= {ao.MODELLED, ao.ENGINE_RESOLVED, ao.TERMINAL,
                                              ao.REFUSED}


@pytest.mark.req("REQ-APPLY-0001")
def test_the_derived_kind_sets_partition_the_table():
    """`TRANSITION_KINDS` / `TERMINAL_KINDS` / `REFUSED_KINDS` are DERIVED from one table. A
    hand-kept second copy is the drift ADR-0087 charges for one store over, and here it would let
    the planner believe a kind is modelled while `apply_option` refuses it."""
    sets = (ao.TRANSITION_KINDS, ao.ENGINE_ROUTE_KINDS, ao.TERMINAL_KINDS, ao.REFUSED_KINDS)
    for i, a in enumerate(sets):
        for b in sets[i + 1:]:
            assert not (a & b), (sorted(a), sorted(b))
    assert set().union(*sets) == set(ao.KIND_COVERAGE)


@pytest.mark.req("REQ-APPLY-0001")
def test_attack_and_end_are_terminal_and_nothing_else_is():
    """Both END the turn (`docs/rules.md` §3 — an attack ends your turn, 1 per turn), so the beam
    terminates on them. A transition kind leaking into this set would let the planner stop early;
    a terminal kind leaking out would let it sequence past the end of my own turn."""
    assert ao.TERMINAL_KINDS == frozenset({_ATTACK, _END})
    assert ao.is_terminal({"type": _ATTACK}) is True
    assert ao.is_terminal({"type": _END}) is True
    assert ao.is_terminal({"type": _ATTACH}) is False


@pytest.mark.req("REQ-APPLY-0001")
def test_the_kinds_with_no_uniform_transition_are_declared_refused_not_omitted():
    """Named individually so a later promotion is a visible diff."""
    for kind in (_NUMBER, _YES, _NO, _CARD, _ENERGY, _DISCARD_IN_PLAY, _SKILL, _SPECIAL_CONDITION):
        assert ao.coverage(kind) == ao.REFUSED, kind


# ── §3b: THREE fates, and a silent no-op is never one of them ─────────────────────────────────────


@pytest.mark.req("REQ-APPLY-0008")
def test_there_are_exactly_three_fates_and_terminal_is_not_one():
    """§3b resolves every option to MODELLED / ENGINE-RESOLVED / REFUSED. A turn-ender has no
    transition to have a fate about, and `UNDECLARED` is a refusal REASON — folding either into the
    fate vocabulary would make "how many ways can this end?" unanswerable."""
    assert ao.FATES == (ao.MODELLED, ao.ENGINE_RESOLVED, ao.REFUSED)
    assert ao.TERMINAL not in ao.FATES and ao.UNDECLARED not in ao.FATES


@pytest.mark.req("REQ-APPLY-0008")
def test_ability_is_ELIGIBLE_for_the_engine_route_rather_than_flatly_refused():
    """ABILITY is 17 live MAIN-menu options in the corpus and the kind IS its effect, so there is no
    uniform closed-form transition — but many Abilities touch no RNG and no hidden zone, and §3b's
    whole point is that such an effect gets priced through the engine rather than pruned at 0."""
    assert ao.coverage(_ABILITY) == ao.ENGINE_RESOLVED
    assert _ABILITY in ao.ENGINE_ROUTE_KINDS and _ABILITY not in ao.TRANSITION_KINDS


@pytest.mark.req("REQ-APPLY-0008")
def test_the_engine_gate_is_PROVABLY_DETERMINISTIC_not_merely_unmodelled():
    """The load-bearing wording. `deterministic` is TRI-state and the unproven default refuses: an
    unmodelled effect that MIGHT touch RNG is REFUSED, fail-closed per ADR-0067's yield convention.

    Two independent reasons, both fatal — the engine has no deal-seed, so a shuffle-riding sim is one
    sample and not a distribution (Issue #178); and nondeterminism breaks the deterministic replay
    both gates depend on, which makes the frame unrulable and the gate vacuous."""
    api = object()
    assert ao.fate({"type": _ABILITY}, search_api=api, deterministic=True) == ao.ENGINE_RESOLVED
    assert ao.fate({"type": _ABILITY}, search_api=api, deterministic=None) == ao.REFUSED   # unproven
    assert ao.fate({"type": _ABILITY}, search_api=api, deterministic=False) == ao.REFUSED
    assert ao.fate({"type": _ABILITY}, search_api=api) == ao.REFUSED                       # default


@pytest.mark.req("REQ-APPLY-0008")
def test_depth_2_refuses_because_the_board_is_synthesized():
    """Not a policy choice. At depth ≥ 1 the preceding steps were closed-form applies, so the board
    is a SYNTHESIZED StateModel — and a synthesized model cannot be handed back to the native
    engine. The refusal carries its own scope because "we were two plies deep" is different work
    from "we never proved this deterministic"."""
    api = object()
    assert ao.fate({"type": _ABILITY}, depth=1, search_api=api, deterministic=True) == ao.REFUSED
    r = ao.apply_option(object(), {"type": _ABILITY}, depth=2, search_api=api, deterministic=True)
    assert isinstance(r, ao.Refusal) and r.scope == ao.DEPTH_SCOPE
    assert "synthesized" in r.reason


@pytest.mark.req("REQ-APPLY-0008")
def test_each_engine_precondition_refuses_with_its_own_scope():
    """Three preconditions, three scopes, because the coverage report has to tell them apart — they
    are three different pieces of work (prove determinism / wire the seam / do not go deep)."""
    got = {}
    for kwargs in ({"deterministic": True, "search_api": None},
                   {"deterministic": None, "search_api": object()},
                   {"depth": 3, "deterministic": True, "search_api": object()}):
        r = ao.apply_option(object(), {"type": _ABILITY}, **kwargs)
        got[r.scope] = r.reason
    assert set(got) == {ao.NO_ENGINE_SCOPE, ao.NONDETERMINISM_SCOPE, ao.DEPTH_SCOPE}
    assert all(reason.strip() for reason in got.values())


@pytest.mark.req("REQ-APPLY-0008")
def test_the_engine_route_returns_a_WRAPPER_so_the_telemetry_cannot_be_forgotten():
    """§3b calls this route *"a bridge that makes the vocabulary gap visible for later modelling,
    never a resting place"*, so it emits telemetry. Returning a bare model would make that a
    convention every caller could forget; the wrapper makes the engine's involvement part of the
    value you must handle. `require_model` unwraps it; `must_expand` is False — it IS resolved."""
    er = ao.EngineResolved(model="board", kind=_ABILITY, clause_gap="no clause for Adrena-Brain")
    assert ao.must_expand(er) is False
    assert ao.require_model(er) == "board"
    assert er.clause_gap


@pytest.mark.req("REQ-APPLY-0008")
def test_the_search_api_seam_is_named_as_preserved_not_deleted():
    """Issue #263 retires `_search_api` as a runtime ROLLOUT and keeps the seam precisely so this
    fallback has a home. Recorded where an implementer reads it, because the natural reading of
    "the rollout is retired" is that the seam goes with it."""
    doc = ao.__doc__ or ""
    assert "_search_api" in doc and "do not design as if it disappears" in doc.lower()


# ── §3b: per-kind READ/WRITE footprints ───────────────────────────────────────────────────────────


@pytest.mark.req("REQ-APPLY-0009")
def test_an_uncharacterised_kind_commutes_with_NOTHING():
    """Fail closed. A footprint that under-reports is worse than none — it would license a reorder
    that changes the board, and the composer would collapse two genuinely different lines into one
    candidate. So the default is incomplete, and incomplete commutes with nothing, itself included."""
    assert ao.footprint(_PLAY).complete is False            # per-card effects: no kind-level answer
    assert ao.commutes(_PLAY, _ATTACH) is False
    assert ao.commutes(_PLAY, _PLAY) is False
    assert ao.commutes(999, 999) is False


@pytest.mark.req("REQ-APPLY-0009")
def test_two_kinds_conflict_when_one_reads_what_the_other_writes():
    """The commutativity rule Issue #263 consumes. ATTACH and EVOLVE both take a card from hand, so
    both WRITE `my_hand_ids` — and hand indices are how options encode their card, so reordering
    them genuinely changes the later option set."""
    attach, evolve = ao.footprint(_ATTACH), ao.footprint(_EVOLVE)
    assert attach.complete and evolve.complete
    assert "my_hand_ids" in attach.writes & evolve.writes
    assert ao.commutes(_ATTACH, _EVOLVE) is False


@pytest.mark.req("REQ-APPLY-0009")
def test_a_revealer_never_joins_a_commutative_block_whatever_its_footprint_says():
    """A reveal changes the OPTION SET, not only the board, so read/write analysis cannot clear it:
    reordering around a draw changes what the later choices are. Asserted through `commutes` on two
    otherwise-disjoint complete footprints, so it is the reveal flag doing the work."""
    quiet = ao.Footprint(reads=frozenset({"stadium"}), writes=frozenset({"stadium"}), complete=True)
    other = ao.Footprint(reads=frozenset({"my_prizes"}), writes=frozenset({"my_prizes"}),
                         complete=True)
    revealer = ao.Footprint(reads=frozenset({"my_prizes"}), writes=frozenset({"my_prizes"}),
                            complete=True, reveals_information=True)
    ao.FOOTPRINTS[901], ao.FOOTPRINTS[902] = quiet, other
    try:
        assert ao.commutes(901, 902) is True      # disjoint + complete + no reveal -> commutes
        ao.FOOTPRINTS[902] = revealer             # ...same footprint, now flagged as revealing
        assert ao.commutes(901, 902) is False
    finally:
        del ao.FOOTPRINTS[901], ao.FOOTPRINTS[902]


@pytest.mark.req("REQ-APPLY-0009")
def test_footprints_speak_the_coverage_registrys_field_vocabulary():
    """One store. A footprint naming a zone `snapshot_coverage` has never heard of would look like
    analysis while corresponding to nothing the snapshot was ever checked for."""
    from common import snapshot_coverage as sc
    for kind, fp in ao.FOOTPRINTS.items():
        unknown = sorted((fp.reads | fp.writes) - set(sc.BY_ID))
        assert unknown == [], (kind, unknown)


# ── refusal is a RESULT, not an exception and not a no-op ─────────────────────────────────────────


@pytest.mark.req("REQ-APPLY-0005")
def test_an_unmodellable_kind_returns_a_REFUSAL_not_a_silent_no_op():
    """The ordering amendment's load-bearing assertion. A no-op prices the option at exactly 0.0
    delta, which at ordering time means "never explored" rather than "undervalued" — so an Ability
    the seam cannot model would look like an Ability not worth using, forever, and nothing would
    report the gap."""
    r = ao.apply_option(object(), {"type": _SKILL})
    assert isinstance(r, ao.Refusal)
    assert r.kind == _SKILL and r.scope == ao.KIND_SCOPE and r.reason.strip()


@pytest.mark.req("REQ-APPLY-0005")
def test_a_kind_the_engine_grows_later_refuses_rather_than_raising():
    """`src/cg/api.py` says outright that new members may be appended DURING the competition. Before
    the amendment this path raised; on the 1-ply ordering hot path a raise is a forfeited grader
    match over an option we merely could not price. It refuses, with its own scope so the coverage
    report can tell "we declared this blind" from "the vocabulary moved"."""
    r = ao.apply_option(object(), {"type": 999})
    assert isinstance(r, ao.Refusal) and r.scope == ao.UNDECLARED_SCOPE
    assert ao.coverage(999) == ao.UNDECLARED
    assert ao.transition_kind({"type": 999}) == 999      # never raises


@pytest.mark.req("REQ-APPLY-0005")
def test_a_refusal_means_ALWAYS_EXPAND_and_that_policy_has_one_home():
    """The tempting reading of a refusal at ordering time is the wrong one: an option with no price
    looks like an option with no value. It has no ESTIMATE; expanding is how the beam finds out. The
    policy is a named function so no caller re-derives it from an `isinstance` check."""
    assert ao.must_expand(ao.apply_option(object(), {"type": _ABILITY})) is True
    assert ao.must_expand(ao.Expectation()) is False
    assert ao.must_expand(object()) is False


@pytest.mark.req("REQ-APPLY-0005")
def test_a_refusal_inside_a_modelled_kind_is_expressible_per_option():
    """"The card leaves my hand" is structural for every `_PLAY`, but a Trainer's EFFECT is per-card.
    So refusal cannot be a property of the kind alone — a `_PLAY` of a card the effect compendium
    does not cover refuses at option scope while the kind stays modelled."""
    r = ao.refuse({"type": _PLAY}, "no compendium entry for this Trainer's effect")
    assert r.scope == ao.OPTION_SCOPE and r.kind == _PLAY
    assert ao.coverage(_PLAY) == ao.MODELLED          # the KIND is untouched
    with pytest.raises(ValueError):
        ao.refuse({"type": _PLAY}, "   ")             # a refusal must say why — telemetry reads it


@pytest.mark.req("REQ-APPLY-0005")
def test_a_caller_that_requires_a_model_raises_on_a_refusal():
    """The parity lane (ADR-0098) replays a recorded native trace step by step; a step it cannot
    model is a coverage gap that must fail the run, not a branch to expand. That is the one caller
    allowed to turn a refusal back into an exception — and the ordering path is explicitly not it."""
    with pytest.raises(ao.UnsupportedTransition):
        ao.require_model(ao.apply_option(object(), {"type": _ABILITY}))
    sentinel = ao.Expectation(classes=(ao.OutcomeClass(1.0),))
    assert ao.require_model(sentinel) is sentinel


@pytest.mark.req("REQ-APPLY-0001")
def test_applying_a_terminal_option_is_an_error_not_an_unchanged_model():
    """There is no successor state to a turn-ender. Returning the model unchanged would silently let
    a beam sequence actions after the attack that ended the turn. It RAISES rather than refusing
    because it is an API misuse, not a modelling gap — the caller was told to test `is_terminal`."""
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


@pytest.mark.req("REQ-APPLY-0006")
def test_an_expectation_yields_one_comparable_number_at_1_ply():
    """The amendment's other half: a draw Supporter must be ORDERABLE, not merely expandable. The
    composer ranks it against a Tool attach on the same scale before deciding to expand anything, so
    an expectation shape usable only inside a sequence expansion would leave every draw Supporter
    unranked — which is the pruning failure the ordering ruling exists to fix."""
    e = ao.Expectation(classes=(ao.OutcomeClass(0.25, model="a"), ao.OutcomeClass(0.75, model="b")))
    assert e.expected({"a": 4.0, "b": 8.0}.__getitem__) == pytest.approx(7.0)


@pytest.mark.req("REQ-APPLY-0006")
def test_a_truncated_expectation_orders_on_the_mass_it_enumerated():
    """Renormalised over the surviving mass, i.e. the expectation CONDITIONAL on the enumerated
    branches. Letting truncated mass contribute 0 would bias against the widest enumerations, and the
    widest enumerations are exactly the draw and search effects this must stop pruning. Here: two
    classes worth 6.0 each on 0.5 total mass reads 6.0, not 3.0."""
    e = ao.Expectation(classes=(ao.OutcomeClass(0.25, model="x"), ao.OutcomeClass(0.25, model="y")),
                       truncated=2)
    assert e.total_probability == pytest.approx(0.5)      # the gap stays visible
    assert e.expected(lambda m: 6.0) == pytest.approx(6.0)


@pytest.mark.req("REQ-APPLY-0006")
def test_ordering_an_unenumerated_expectation_raises_rather_than_returning_zero():
    """Zero enumerated mass means the effect was never enumerated. 0.0 is a real score, so returning
    it would price an un-enumerated effect as a worthless one — the same failure the identity-stub
    test guards, one layer up."""
    with pytest.raises(ValueError):
        ao.Expectation().expected(lambda m: 1.0)


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


@pytest.mark.req("REQ-APPLY-0004")
def test_a_quarantined_kind_refuses_through_the_same_path_as_any_other_gap(monkeypatch):
    """Quarantine and the coverage table give ONE answer, so the planner never has to consult two
    registries and agree with itself. A quarantined kind degrades to always-expand — visibly, with
    its own scope for the telemetry line — instead of silently mis-playing."""
    monkeypatch.setattr(ao, "quarantined_kinds", lambda: frozenset({_ATTACH}))
    assert ao.coverage(_ATTACH) == ao.REFUSED
    r = ao.apply_option(object(), {"type": _ATTACH})
    assert isinstance(r, ao.Refusal) and r.scope == ao.QUARANTINE_SCOPE
    assert ao.must_expand(r) is True


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


@pytest.mark.req("REQ-APPLY-0007")
def test_the_seam_states_that_transitions_are_lazy_rather_than_deep_copies():
    """T0 cannot test laziness — nothing is implemented yet — but it can stop T4 from discovering the
    requirement late. 1-ply ordering runs this once per candidate per decision, so an eager deep copy
    per branch is a cost the grader's 2 vCPUs will not absorb; the lazy StateModel of ADR-0068 is
    what the transitions ride."""
    doc = (ao.__doc__ or "") + (ao.apply_option.__doc__ or "")
    assert "lazy" in doc.lower() and "ADR-0068" in doc
    assert "deep copy" in doc.lower()
