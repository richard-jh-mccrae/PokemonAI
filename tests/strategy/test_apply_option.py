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
def test_ability_is_the_kind_the_table_PREFERS_to_send_to_the_engine():
    """ABILITY is 17 live MAIN-menu options in the corpus and the kind IS its effect, so there is no
    uniform closed-form transition — but many Abilities touch no RNG and no hidden zone, and §3b's
    whole point is that such an effect gets priced through the engine rather than pruned at 0.

    Since Issue #299 this is a statement about the TABLE, not about eligibility: every declared
    non-terminal kind can reach the engine route now, so `ENGINE_ROUTE_KINDS` records only which
    kinds have no closed-form answer to fall back to. `_ABILITY` is in it and `_PLAY` is not, even
    though a `_PLAY` whose card effect no clause covers reaches the same route."""
    assert ao.coverage(_ABILITY) == ao.ENGINE_RESOLVED
    assert _ABILITY in ao.ENGINE_ROUTE_KINDS and _ABILITY not in ao.TRANSITION_KINDS


@pytest.mark.req("REQ-APPLY-0008")
def test_a_complete_clause_set_beats_the_kind_table():
    """Issue #299 Q2. Drakloak, Lunatone, Dudunsparce and Fezandipiti ex each carry Effect Clauses
    covering their WHOLE Ability, and every one of them routed to the engine — which then refused it
    for nondeterminism, because an Ability that reads the deck is exactly what the determinism proof
    excludes. The clause work already paid for was unreachable: a routing bug, not a coverage gap.

    A complete clause set is strictly better evidence than a kind-level default (closed-form,
    deterministic in distribution, and what the compendium exists to provide), so it wins outright —
    `whatever the kind says`, including a kind the table sends to the engine."""
    assert ao.coverage(_ABILITY) == ao.ENGINE_RESOLVED          # still engine-PREFERRED in the table
    assert ao.fate({"type": _ABILITY}, clauses_cover=True) == ao.MODELLED
    # ...and with no engine wired and no determinism proof, which is the four cards' real situation.
    assert ao.fate({"type": _ABILITY}, clauses_cover=True, deterministic=False) == ao.MODELLED
    # MODELLED sends the call to the closed-form transition. `_ABILITY` has none — the kind IS its
    # effect — so it refuses at OPTION scope: the KIND resolved, this option's board change did not.
    r = ao.apply_option(object(), {"type": _ABILITY}, clauses_cover=True)
    assert isinstance(r, ao.Refusal) and r.scope == ao.OPTION_SCOPE


@pytest.mark.req("REQ-APPLY-0008")
def test_a_PARTIAL_clause_set_refuses_a_kind_the_table_calls_MODELLED():
    """The other half of the same wiring, and the reason Issue #300 declared the verdict at all.
    `_covers: partial` reaches here as `clauses_cover=False`, and before this it could not: MODELLED
    was a pure kind lookup, so a `_PLAY` whose clauses cover part of the printed card priced as if
    they covered all of it and the uncovered leg differenced to exactly 0 — §3c's silent zero,
    arriving through the compendium instead of through the snapshot."""
    assert ao.coverage(_PLAY) == ao.MODELLED
    assert ao.fate({"type": _PLAY}, clauses_cover=False) == ao.REFUSED
    assert ao.fate({"type": _PLAY}, clauses_cover=True) == ao.MODELLED


@pytest.mark.req("REQ-APPLY-0008")
def test_an_UNRULED_clause_verdict_still_lets_the_structural_transition_through():
    """`None` is NOT the same falsey answer as `False` here, and the difference is most of the pool.

    A vanilla Basic's deploy, a Basic Energy attach and a Tool attach carry no card effect for a
    clause to cover, so `CardEffects.clauses_cover` answers `None` for all of them — refusing on
    `None` would refuse the structural transitions this seam exists to provide. The residue is the
    CALLER's: T4 passes `False`, not `None`, for a card that HAS a printed effect no clause covers,
    because absence-of-a-compendium-entry cannot tell those two apart on its own."""
    for kind in sorted(ao.TRANSITION_KINDS):
        assert ao.fate({"type": kind}) == ao.MODELLED, kind
        assert ao.fate({"type": kind}, clauses_cover=None) == ao.MODELLED, kind


@pytest.mark.req("REQ-APPLY-0008")
def test_a_MODELLED_kind_with_partial_clauses_still_needs_the_determinism_PROOF():
    """The regression that would silently undo ADR-0067 here. Opening the engine route per-option
    must not let a `_PLAY` reach it on easier terms than an `_ABILITY` ever could: the gate is still
    a PROOF, so an unproven `deterministic` refuses even though the kind is MODELLED and the caller
    wired a live engine."""
    api = object()
    assert ao.fate({"type": _PLAY}, clauses_cover=False, search_api=api) == ao.REFUSED
    assert ao.fate({"type": _PLAY}, clauses_cover=False, search_api=api,
                   deterministic=None) == ao.REFUSED
    assert ao.fate({"type": _PLAY}, clauses_cover=False, search_api=api,
                   deterministic=False) == ao.REFUSED
    assert ao.fate({"type": _PLAY}, clauses_cover=False, search_api=api,
                   deterministic=True) == ao.ENGINE_RESOLVED


@pytest.mark.req("REQ-APPLY-0008")
def test_the_engine_route_is_open_to_every_declared_non_terminal_kind():
    """Issue #299 Q1. The kind table answers *"is there a uniform transition for this KIND?"*; the
    fate answers *"can we resolve THIS option?"*. Conflating them left 46 refused sites on MODELLED
    kinds carrying no RNG, hidden-zone or opponent-choice marker at all — the exact shape §3b calls
    ENGINE-RESOLVED — with nowhere to be sent.

    So eligibility is no longer membership of `ENGINE_ROUTE_KINDS`. Asserted over every declared
    non-terminal kind rather than over a sample, since the point is that no kind is excluded."""
    api = object()
    for kind in sorted(set(ao.KIND_COVERAGE) - ao.TERMINAL_KINDS):
        assert ao.fate({"type": kind}, search_api=api, deterministic=True,
                       clauses_cover=False) == ao.ENGINE_RESOLVED, kind
    assert ao.ENGINE_ROUTE_KINDS == frozenset({_ABILITY})       # the TABLE is deliberately unmoved


@pytest.mark.req("REQ-APPLY-0008")
def test_a_table_REFUSED_kind_IS_rescued_by_a_complete_clause_set():
    """The deliberate boundary of the guard above, asserted so nobody "tightens" it later.

    `KIND_COVERAGE` rules that a kind like `_SKILL` or `_YES` has no uniform transition because its
    *"whole content is a card effect"* — which is exactly what a complete clause set covers. That is
    a RULING about the kind, not ignorance of it, so it is nothing like UNDECLARED. And it is the
    same argument that rescues `_ABILITY`: refusing `_YES` on evidence that rescues `_ABILITY` would
    contradict Q2 rather than reinforce it."""
    for kind in (_SKILL, _YES, _NUMBER, _CARD):
        assert ao.coverage(kind) == ao.REFUSED, kind
        assert ao.fate({"type": kind}, clauses_cover=True) == ao.MODELLED, kind
        assert ao.fate({"type": kind}) == ao.REFUSED, kind          # ...and only on that evidence


@pytest.mark.req("REQ-APPLY-0004")
def test_quarantine_outranks_a_complete_clause_set(monkeypatch):
    """A parity divergence says the seam's model of this kind is WRONG. No per-option evidence can
    speak over that — least of all a clause set, which is a claim about the CARD while quarantine is
    a measured fact about the KIND. Asserted on `fate` as well as `apply_option` because Issue #299
    moved the clause gate ahead of the kind lookup, and quarantine had to move ahead of it in turn or
    a clause-complete card would have walked straight through a diverging kind."""
    monkeypatch.setattr(ao, "quarantined_kinds", lambda: frozenset({_PLAY}))
    assert ao.fate({"type": _PLAY}, clauses_cover=True) == ao.REFUSED
    assert ao.fate({"type": _PLAY}, clauses_cover=True, search_api=object(),
                   deterministic=True) == ao.REFUSED
    r = ao.apply_option(object(), {"type": _PLAY}, clauses_cover=True)
    assert isinstance(r, ao.Refusal) and r.scope == ao.QUARANTINE_SCOPE


@pytest.mark.req("REQ-APPLY-0008")
def test_terminal_and_undeclared_are_not_rescued_by_a_complete_clause_set():
    """The two guards that sit AHEAD of "a complete clause set wins". A turn-ender has no successor
    state for any evidence to describe. An undeclared kind is worse: a clause verdict speaks for the
    card's EFFECT and never for the half of the transition the KIND contributes, and for a kind the
    engine grew underneath us that half is entirely unknown — so `src/cg/api.py`'s warning that the
    enum grows *during the competition* makes this a live grader path, not a theoretical one."""
    api = object()
    for kind in (_ATTACK, _END, 999):
        assert ao.fate({"type": kind}, clauses_cover=True) == ao.REFUSED, kind
        assert ao.fate({"type": kind}, clauses_cover=True, search_api=api,
                       deterministic=True) == ao.REFUSED, kind
    r = ao.apply_option(object(), {"type": 999}, clauses_cover=True, search_api=api,
                        deterministic=True)
    assert isinstance(r, ao.Refusal) and r.scope == ao.UNDECLARED_SCOPE


@pytest.mark.req("REQ-APPLY-0008")
def test_apply_option_resolves_the_same_way_fate_does():
    """One resolution order, asserted rather than kept by hand in two cascades. `apply_option` adds
    only the refusal SCOPES; if it ever disagreed with `fate` about the FATE, the census (which
    mirrors `fate`) and the composer (which calls `apply_option`) would price the same option
    differently and nothing would say so."""
    api = object()
    for kind in sorted(set(ao.KIND_COVERAGE) - ao.TERMINAL_KINDS) + [999]:
        for cover in (True, False, None):
            for det in (True, False, None):
                for search in (api, None):
                    kw = dict(search_api=search, deterministic=det, clauses_cover=cover)
                    want = ao.fate({"type": kind}, **kw)
                    r = ao.apply_option(object(), {"type": kind}, **kw)
                    assert isinstance(r, ao.Refusal), (kind, kw)
                    assert r.scope and r.reason.strip(), (kind, kw)
                    # The SCOPE is where the two answers have to agree. A `fate` of REFUSED is a
                    # kind/precondition refusal and never carries option scope; a non-REFUSED fate
                    # that still cannot produce a board (this caller hands `object()`, which is not a
                    # model) refuses at OPTION scope — the transition's own answer, on a kind the
                    # table still calls resolvable. Collapsing those two would let a coverage report
                    # blame the kind for what the option could not do, which is the distinction
                    # `refuse`'s `scope=` exists to keep (POC-T4/1, Issue #382).
                    if want == ao.REFUSED:
                        assert r.scope != ao.OPTION_SCOPE, (kind, kw)
                    else:
                        assert r.scope in (ao.OPTION_SCOPE, ao.NO_ENGINE_SCOPE), (kind, kw, r.scope)


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
    er = ao.EngineResolved(model="board", kind=_ABILITY,
                           clause_gap="1182 Boss’s Orders: no `gust` clause kind")
    assert ao.must_expand(er) is False
    assert ao.require_model(er) == "board"
    assert er.clause_gap


@pytest.mark.req("REQ-APPLY-0008")
def test_the_engine_telemetry_names_the_CARD_now_that_every_kind_can_reach_it():
    """Issue #299's telemetry consequence, and it is not cosmetic. While the route was
    `_ABILITY`-only the `kind` field was nearly an identifier for the work owed; with the route open
    to every declared non-terminal kind a backlog line reading *"kind 7"* covers the corpus's 699
    `_PLAY` options at once, and a modelling backlog nobody can group by card is unreadable.

    Extended in the EXISTING field rather than beside it: the backlog is grouped by this one string,
    and a second card field would let half of it be dropped by a caller that filled only the older
    one. Asserted on the docstring because T0 freezes contracts — the field is a `str` and T4 is what
    populates it."""
    import inspect
    fields = set(ao.EngineResolved.__dataclass_fields__)
    assert "clause_gap" in fields
    assert not (fields & {"card", "card_id", "card_name"}), "extend the field, do not add a second"
    src = inspect.getsource(ao.EngineResolved)
    assert "must name the CARD" in src and "<card id> <card name>" in src


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
def test_playing_a_stadium_DISPLACES_the_one_in_play_and_spends_the_allowance():
    """**Issue #304.** A Stadium REPLACES the one in play, so *displacing one that is hurting me* is
    a real play — and while nothing named the zone, the seam could not see it and the swap
    differenced to ~0. `_PLAY` now carries a footprint naming `stadium`, `allowance_stadium_played`
    and both discards, checked at source rather than recalled:

    * `docs/rulebook.txt` L135-137 — *"A Stadium stays in play when you play it. Only one Stadium can
      be in play at a time—if a new one comes into play, discard the old one and end its effects. You
      can't play a Stadium card if a Stadium with the same name is already in play."*
    * `docs/rulebook.txt` L112 / L138, and `docs/rules.md` §3 — one Stadium per turn, *"and only if
      it differs from the one in play"*.
    * `docs/rulebook.txt` L78 — *"Each player has their own discard pile"*, which is why BOTH
      discards are written: the displaced Stadium goes to its own owner's pile, and displacing
      THEIRS is the case that made this worth naming.

    **The footprint stays INCOMPLETE and that is deliberate**, so this changes no commutativity
    answer: a Trainer play writes whatever its Effect Clauses write, which is per-card. The sets are
    a declared FLOOR — what T4 must at least write — and `complete=False` is the statement that the
    true set is larger. The kind still commutes with nothing, itself included, which the test above
    asserts and this one re-asserts so the two cannot be changed apart."""
    fp = ao.footprint(_PLAY)
    assert fp.complete is False and ao.commutes(_PLAY, _PLAY) is False
    assert {"stadium", "allowance_stadium_played"} <= fp.reads
    assert {"stadium", "allowance_stadium_played"} <= fp.writes
    # Displacement is a DISCARD on whichever side owned the old Stadium, and the played card leaves
    # my hand. All three are the structural half — no card's effect text is read to know them.
    assert {"my_hand_ids", "my_discard_contents", "their_discard_contents"} <= fp.writes
    # Not an empty claim: the floor is asserted to be a floor by naming a zone only the per-card
    # EFFECT can write, which must NOT be in it.
    assert "deck_odds" not in (fp.reads | fp.writes)


@pytest.mark.req("REQ-APPLY-0009")
def test_footprints_speak_the_coverage_registrys_field_vocabulary():
    """One store. A footprint naming a zone `snapshot_coverage` has never heard of would look like
    analysis while corresponding to nothing the snapshot was ever checked for."""
    from common import snapshot_coverage as sc
    for kind, fp in ao.FOOTPRINTS.items():
        unknown = sorted((fp.reads | fp.writes) - set(sc.BY_ID))
        assert unknown == [], (kind, unknown)


# ── §3b: PER-OPTION footprints (POC-T4/2, Issue #383) ─────────────────────────────────────────────
#
# The kind table cannot answer for `_PLAY` — a Trainer play writes whatever its Effect Clauses write,
# which is per-card. `option_footprint` is the answer: the kind's structural FLOOR plus the union of
# `snapshot_coverage.CLAUSE_WRITES` over the card's own clauses, with `reveals_information` armed off
# `REVEALING_CLAUSES`.
#
# Every fixture row below is COPIED from `src/common/card_effects.json`, and its card TYPE read off
# `data/EN_Card_Data.csv` — both checked at source, never recalled:
#   1125 Master Ball        Item      `[{"kind": "fetch", "target": "pokemon", "zone": "deck"}]`
#                                     — REVEALING
#   1182 Boss's Orders      Supporter `[{"kind": "gust", "target": "any"}]` — writes, reveals nothing
#   1141 Premium Power Pro  Item      `null` — NO clauses at all: the clause-less blind spot, which
#                                     must read as UNKNOWN and never as "writes nothing, so commutes
#                                     with everything"
_ITEM_TYPE, _SUPPORTER_TYPE = 1, 3


def _footprint_model(card_id, *, clauses, card_type=_ITEM_TYPE):
    """A one-card hand over a dict-backed provider — the same DLL-free seam the rest of this file
    uses, extended with a `CardEffects` because a per-OPTION footprint is a question about a card."""
    from common.cards import CardFunctions
    from common.effects import CardEffects
    from common.option_equivalence import AREA_HAND
    from common.scouting.provider import CardStat, DictCardStatProvider
    from common.state_model import StateModel
    from common.strategy.combat import CombatMath
    stats = {card_id: CardStat(card_id, synthetic=True, name=f"footprint fixture {card_id}",
                               cardType=card_type)}
    combat = CombatMath(DictCardStatProvider(stats), functions=CardFunctions({}), transients=None,
                        effects=CardEffects({card_id: clauses} if clauses is not None else {}))
    player = {"active": [], "bench": [], "benchMax": 5,
              "hand": [{"id": card_id, "serial": 700, "playerIndex": 0}], "handCount": 1,
              "discard": [], "prize": [None] * 6}
    obs = {"current": {"players": [player, dict(player, hand=[], handCount=0)], "yourIndex": 0,
                       "stadium": []},
           "select": {"context": 0, "option": []}}
    option = {"type": _PLAY, "area": AREA_HAND, "index": 0}
    return StateModel.build(obs, combat=combat, deck=[card_id]), option


@pytest.mark.req("REQ-APPLY-0009")
def test_a_per_option_footprint_unions_the_cards_clause_writes_onto_the_kinds_floor():
    """Boss's Orders' `gust` writes `bodies_in_play`, `special_conditions` and `transient_grants` —
    none of them in `_PLAY`'s structural floor, all three in the per-OPTION answer."""
    from common import snapshot_coverage as sc
    model, option = _footprint_model(1182, clauses=[{"kind": "gust", "target": "any"}],
                                     card_type=_SUPPORTER_TYPE)
    fp = ao.option_footprint(model, option, clauses_cover=True)
    assert ao.footprint(_PLAY).writes <= fp.writes                 # the floor survives
    assert sc.CLAUSE_WRITES["gust"] <= fp.writes                   # ...and the clauses join it
    assert fp.reveals_information is False                         # a gust moves a body, reveals none


@pytest.mark.req("REQ-APPLY-0009")
def test_a_per_option_footprint_ARMS_reveals_information_from_the_registry():
    """**The reveal veto was unarmed code until now** — no entry in `FOOTPRINTS` sets the flag, so
    `commutes` could never reach that clause on a real option. Positive control that the absence is
    real and not a bad search: the kind table still sets it nowhere, while a `fetch` card's per-option
    footprint sets it True."""
    assert [k for k, f in ao.FOOTPRINTS.items() if f.reveals_information] == []
    model, option = _footprint_model(
        1125, clauses=[{"kind": "fetch", "target": "pokemon", "zone": "deck"}])
    fp = ao.option_footprint(model, option, clauses_cover=True)
    assert fp.reveals_information is True
    assert ao.footprints_commute(fp, ao.footprint(_RETREAT)) is False


@pytest.mark.req("REQ-APPLY-0009")
def test_a_CLAUSELESS_play_card_is_UNKNOWN_and_never_an_empty_write_set():
    """The blind spot `footprints_writing_unhomed` names by card. Premium Power Pro (1141), Black
    Belt's Training (1211) and Brave Bangle (1175) return NOTHING from `card_effects.json`, so a
    union over their clauses is the empty set — and an empty write-set reads as *"conflicts with
    nobody"*, which would license every reorder involving them. It must read as UNKNOWN instead."""
    model, option = _footprint_model(1141, clauses=None)
    fp = ao.option_footprint(model, option)
    assert fp.complete is False
    assert ao.footprints_commute(fp, fp) is False
    assert ao.footprints_commute(fp, ao.footprint(_RETREAT)) is False
    # ...and a CALLER asserting coverage cannot complete it either. `CardEffects.clauses_cover`
    # returns `None` for a card it has never heard of, but `fate`'s contract requires the caller to
    # join that against whether the card carries printed text — so `True` can reach here, and over an
    # empty clause list it would be coverage asserted over the compendium's silence. 1141's printed
    # text is *"During this turn, attacks used by your {F} Pokémon do 30 more damage…"*, so it very
    # much HAS an effect; the compendium simply does not hold it.
    assert ao.option_footprint(model, option, clauses_cover=True).complete is False
    assert ao.option_footprint(model, option, clauses_cover=True).writes == ao.footprint(_PLAY).writes


@pytest.mark.req("REQ-APPLY-0009")
def test_completeness_needs_the_CALLERS_clause_coverage_proof_not_merely_some_clauses():
    """`clauses_cover` is the same tri-state `fate` takes and it means the same thing here. `True`
    completes the `_PLAY` floor; `False` is Issue #300's *partial* verdict and can never complete
    anything; `None` is absence of a compendium verdict and fails closed."""
    model, option = _footprint_model(1182, clauses=[{"kind": "gust", "target": "any"}],
                                     card_type=_SUPPORTER_TYPE)
    assert ao.option_footprint(model, option, clauses_cover=True).complete is True
    assert ao.option_footprint(model, option, clauses_cover=False).complete is False
    assert ao.option_footprint(model, option, clauses_cover=None).complete is False


@pytest.mark.req("REQ-APPLY-0009")
def test_an_undeclared_clause_value_makes_the_footprint_unknown_rather_than_narrower():
    """Fail closed against vocabulary drift: a clause value `snapshot_coverage.CLAUSE_WRITES` has
    never heard of contributes no zones, and treating that silence as "writes nothing" is exactly the
    under-report `Footprint` calls *worse than none*."""
    model, option = _footprint_model(1182, clauses=[{"kind": "a_clause_nobody_declared"}])
    assert ao.option_footprint(model, option, clauses_cover=True).complete is False


@pytest.mark.req("REQ-APPLY-0009")
def test_a_clause_write_is_also_declared_a_clause_READ():
    """`CLAUSE_WRITES` is a WRITE registry; §3b's read-set for a clause is not shipped. So every zone
    a clause writes is declared read as well — OVER-reporting, which can only make `commutes` refuse
    a block it might have allowed, never license one it should have refused. Under-reporting a read
    is the direction that silently collapses two genuinely different lines."""
    from common import snapshot_coverage as sc
    model, option = _footprint_model(1182, clauses=[{"kind": "gust", "target": "any"}],
                                     card_type=_SUPPORTER_TYPE)
    fp = ao.option_footprint(model, option, clauses_cover=True)
    assert sc.CLAUSE_WRITES["gust"] <= fp.reads


@pytest.mark.req("REQ-APPLY-0009")
def test_commutes_delegates_to_the_ONE_disjointness_test():
    """One rule, one home. `commutes` is the per-KIND door onto `footprints_commute`, and the
    per-OPTION door is `option_footprint` — two callers, never two copies of the test, which is the
    drift ADR-0087 charges for one store over."""
    quiet = ao.Footprint(reads=frozenset({"stadium"}), writes=frozenset({"stadium"}), complete=True)
    other = ao.Footprint(reads=frozenset({"my_prizes"}), writes=frozenset({"my_prizes"}),
                         complete=True)
    assert ao.footprints_commute(quiet, other) is True
    assert ao.footprints_commute(quiet, quiet) is False           # both write `stadium`
    ao.FOOTPRINTS[903], ao.FOOTPRINTS[904] = quiet, other
    try:
        assert ao.commutes(903, 904) is ao.footprints_commute(quiet, other)
    finally:
        del ao.FOOTPRINTS[903], ao.FOOTPRINTS[904]


@pytest.mark.req("REQ-APPLY-0009")
def test_the_element_level_granularity_is_NOT_assumed_while_the_ruling_is_open():
    """Issue #383 §B item 2 requested an element-level refinement on Issue #263 as a wave-packet
    ruling line, with a stated fail-closed fallback: **zone granularity, blocks never form**. Until
    that ruling lands the fallback is what ships, and this asserts it rather than leaving the
    difference invisible — a session that quietly implemented the refinement would be self-ruling a
    contract extension.

    So `commutes` still licenses NOTHING over the shipped table, and Issue #263's own worked example
    (Energy + evolution + Tool) still fails on `my_hand_ids`."""
    import itertools
    kinds = sorted(ao.KIND_COVERAGE)
    assert [(a, b) for a, b in itertools.combinations_with_replacement(kinds, 2)
            if ao.commutes(a, b)] == []
    assert "my_hand_ids" in ao.footprint(_ATTACH).writes & ao.footprint(_EVOLVE).writes


# ── refusal is a RESULT, not an exception and not a no-op ─────────────────────────────────────────


@pytest.mark.req("REQ-APPLY-0005")
def test_an_unmodellable_kind_returns_a_REFUSAL_not_a_silent_no_op():
    """The ordering amendment's load-bearing assertion. A no-op prices the option at exactly 0.0
    delta, which at ordering time means "never explored" rather than "undervalued" — so an Ability
    the seam cannot model would look like an Ability not worth using, forever, and nothing would
    report the gap.

    **The SCOPE moved in Issue #299 and the claim did not.** `_SKILL` used to refuse at
    `KIND_SCOPE`, because the kind table was the gate; now that the engine route is open to every
    declared non-terminal kind, "this kind has no uniform transition" is no longer why the option
    refuses — it refuses at whichever engine precondition it missed, which here is the determinism
    proof, and that is the work actually owed. `KIND_SCOPE` is documented as no longer emitted rather
    than deleted; see its definition."""
    r = ao.apply_option(object(), {"type": _SKILL})
    assert isinstance(r, ao.Refusal)
    assert r.kind == _SKILL and r.scope == ao.NONDETERMINISM_SCOPE and r.reason.strip()
    assert ao.coverage(_SKILL) == ao.REFUSED         # the TABLE still says the kind is unmodellable


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
def test_a_transition_that_cannot_be_computed_refuses_rather_than_returning_the_model_unchanged():
    """The claim that matters, and it OUTLIVED the stub it was written for.

    Until POC-T4/1 every modelled kind raised `NotImplementedError` here, because at T0 there was no
    transition to run and an identity return would have priced the play at exactly 0.0 — a real,
    plausible answer, so an unimplemented build would have read as a working one that thinks nothing
    is worth doing.

    The transitions exist now (`common.board_delta`), so the raise is gone; the property is not. Fed
    a model it cannot transition from — here `object()`, which carries no observation — the seam
    still must not hand back something that differences to zero. It returns a `Refusal`, which the
    composer answers by always-expanding (`must_expand`), and which carries a sentence saying why."""
    for kind in sorted(ao.TRANSITION_KINDS):
        r = ao.apply_option(object(), {"type": kind})
        assert isinstance(r, ao.Refusal), kind
        assert r.kind == kind and r.scope == ao.OPTION_SCOPE and r.reason.strip(), kind
        assert ao.must_expand(r) is True, kind


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
