"""The apply-seam contract (`common/apply_option.py`, POC-T0 / Issue #259, ADR-0098).

The one property the whole file exists for: nothing here returns a plausible answer before it means
one. An identity return prices every play at exactly 0.0 under differencing, and 0.0 is a REAL
answer, so an unimplemented transition would read as a working one that thinks nothing is worth
doing — and a kind the seam cannot model would be priced at 0 delta (never-explore) rather than
made visible to the composer (always-expand).

Plain data in, plain data out: no engine, no DLL, runs everywhere.
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
    """READ FROM `src/cg/api.py`, never imported: importing `cg.api` maps the native library, which
    this suite must not do."""
    src = _API.read_text(encoding="utf-8-sig")
    block = src.split("class OptionType(IntEnum):", 1)[1].split("\nclass ", 1)[0]
    return {int(v) for v in re.findall(r"^\s{4}[A-Z_]+ = (\d+)", block, flags=re.M)}


# ── the option-kind table ─────────────────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-APPLY-0001")
def test_the_seam_declares_exactly_the_kinds_the_planner_sequences():
    """Bench/deploy and promote arrive as PLAY and RETREAT: the seam speaks the ENGINE's vocabulary
    (`src/cg/api.py`), never a second spelling of it."""
    assert ao.TRANSITION_KINDS == frozenset({_PLAY, _ATTACH, _EVOLVE, _RETREAT})


@pytest.mark.req("REQ-APPLY-0001")
def test_the_kind_table_is_TOTAL_over_the_engines_option_vocabulary():
    """1-ply differencing visits EVERY option on a live menu. Asserted against the engine enum
    itself: a hand-copied list is what the table would have to drift from to fail."""
    assert set(ao.KIND_COVERAGE) == _engine_option_types()
    assert set(ao.KIND_COVERAGE.values()) <= {ao.MODELLED, ao.ENGINE_RESOLVED, ao.TERMINAL,
                                              ao.REFUSED}


@pytest.mark.req("REQ-APPLY-0001")
def test_the_derived_kind_sets_partition_the_table():
    """One store (ADR-0087): a second copy would let the planner believe a kind is modelled while
    `apply_option` refuses it."""
    sets = (ao.TRANSITION_KINDS, ao.ENGINE_ROUTE_KINDS, ao.TERMINAL_KINDS, ao.REFUSED_KINDS)
    for i, a in enumerate(sets):
        for b in sets[i + 1:]:
            assert not (a & b), (sorted(a), sorted(b))
    assert set().union(*sets) == set(ao.KIND_COVERAGE)


@pytest.mark.req("REQ-APPLY-0001")
def test_attack_and_end_are_terminal_and_nothing_else_is():
    """A leak either way lets the planner stop early, or sequence past the end of my own turn."""
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
    """A turn-ender has no transition to have a fate about, and `UNDECLARED` is a refusal REASON."""
    assert ao.FATES == (ao.MODELLED, ao.ENGINE_RESOLVED, ao.REFUSED)
    assert ao.TERMINAL not in ao.FATES and ao.UNDECLARED not in ao.FATES


@pytest.mark.req("REQ-APPLY-0008")
def test_ability_is_the_kind_the_table_PREFERS_to_send_to_the_engine():
    """A statement about the TABLE, not about eligibility: `ENGINE_ROUTE_KINDS` records which kinds
    have no closed-form answer to fall back to, and every non-terminal kind can reach the route."""
    assert ao.coverage(_ABILITY) == ao.ENGINE_RESOLVED
    assert _ABILITY in ao.ENGINE_ROUTE_KINDS and _ABILITY not in ao.TRANSITION_KINDS


@pytest.mark.req("REQ-APPLY-0008")
def test_a_complete_clause_set_beats_the_kind_table():
    """A complete clause set is strictly better evidence than a kind-level default, so it wins
    outright — including over a kind the table sends to the engine (Issue #299 Q2)."""
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
    """`_covers: partial` reaches here as `clauses_cover=False`. On a pure kind lookup the uncovered
    leg differences to exactly 0 — §3c's silent zero, arriving through the compendium (Issue #300)."""
    assert ao.coverage(_PLAY) == ao.MODELLED
    assert ao.fate({"type": _PLAY}, clauses_cover=False) == ao.REFUSED
    assert ao.fate({"type": _PLAY}, clauses_cover=True) == ao.MODELLED


@pytest.mark.req("REQ-APPLY-0008")
def test_an_UNRULED_clause_verdict_still_lets_the_structural_transition_through():
    """`None` (no card effect to cover) is NOT `False` (a printed effect no clause covers), and the
    CALLER owns the join — absence of a compendium entry cannot tell the two apart on its own."""
    for kind in sorted(ao.TRANSITION_KINDS):
        assert ao.fate({"type": kind}) == ao.MODELLED, kind
        assert ao.fate({"type": kind}, clauses_cover=None) == ao.MODELLED, kind


@pytest.mark.req("REQ-APPLY-0008")
def test_a_MODELLED_kind_with_partial_clauses_still_needs_the_determinism_PROOF():
    """The gate is still a PROOF (ADR-0067): opening the route per-option must not let a `_PLAY`
    reach it on easier terms than an `_ABILITY` ever could."""
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
    """The kind table answers "is there a uniform transition for this KIND?"; the fate answers "can
    we resolve THIS option?". Eligibility is no longer membership of `ENGINE_ROUTE_KINDS`."""
    api = object()
    for kind in sorted(set(ao.KIND_COVERAGE) - ao.TERMINAL_KINDS):
        assert ao.fate({"type": kind}, search_api=api, deterministic=True,
                       clauses_cover=False) == ao.ENGINE_RESOLVED, kind
    assert ao.ENGINE_ROUTE_KINDS == frozenset({_ABILITY})       # the TABLE is deliberately unmoved


@pytest.mark.req("REQ-APPLY-0008")
def test_a_table_REFUSED_kind_IS_rescued_by_a_complete_clause_set():
    """A kind whose "whole content is a card effect" is exactly what a complete clause set covers,
    so refusing `_YES` on evidence that rescues `_ABILITY` would contradict the ruling above."""
    for kind in (_SKILL, _YES, _NUMBER, _CARD):
        assert ao.coverage(kind) == ao.REFUSED, kind
        assert ao.fate({"type": kind}, clauses_cover=True) == ao.MODELLED, kind
        assert ao.fate({"type": kind}) == ao.REFUSED, kind          # ...and only on that evidence


@pytest.mark.req("REQ-APPLY-0004")
def test_quarantine_outranks_a_complete_clause_set(monkeypatch):
    """A clause set is a claim about the CARD; quarantine is a measured fact about the KIND, so it
    must sit ahead of the clause gate or a clause-complete card walks through a diverging kind."""
    monkeypatch.setattr(ao, "quarantined_kinds", lambda: frozenset({_PLAY}))
    assert ao.fate({"type": _PLAY}, clauses_cover=True) == ao.REFUSED
    assert ao.fate({"type": _PLAY}, clauses_cover=True, search_api=object(),
                   deterministic=True) == ao.REFUSED
    r = ao.apply_option(object(), {"type": _PLAY}, clauses_cover=True)
    assert isinstance(r, ao.Refusal) and r.scope == ao.QUARANTINE_SCOPE


@pytest.mark.req("REQ-APPLY-0008")
def test_terminal_and_undeclared_are_not_rescued_by_a_complete_clause_set():
    """A clause verdict speaks for the card's EFFECT, never for the half the KIND contributes — and
    `src/cg/api.py` warns the enum grows DURING the competition, so this is a live grader path."""
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
    """`apply_option` adds only the refusal SCOPES: a disagreement about the FATE would let the
    census and the composer price the same option differently, with nothing to say so."""
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
                    # Collapsing kind-scope into option-scope would let a coverage report blame
                    # the KIND for what the OPTION could not do (Issue #382).
                    if want == ao.REFUSED:
                        assert r.scope != ao.OPTION_SCOPE, (kind, kw)
                    else:
                        assert r.scope in (ao.OPTION_SCOPE, ao.NO_ENGINE_SCOPE), (kind, kw, r.scope)


@pytest.mark.req("REQ-APPLY-0008")
def test_the_engine_gate_is_PROVABLY_DETERMINISTIC_not_merely_unmodelled():
    """`deterministic` is TRI-state and the UNPROVEN default refuses: the engine has no deal-seed, so
    a shuffle-riding sim is one sample and not a distribution (ADR-0067, Issue #178)."""
    api = object()
    assert ao.fate({"type": _ABILITY}, search_api=api, deterministic=True) == ao.ENGINE_RESOLVED
    assert ao.fate({"type": _ABILITY}, search_api=api, deterministic=None) == ao.REFUSED   # unproven
    assert ao.fate({"type": _ABILITY}, search_api=api, deterministic=False) == ao.REFUSED
    assert ao.fate({"type": _ABILITY}, search_api=api) == ao.REFUSED                       # default


@pytest.mark.req("REQ-APPLY-0008")
def test_depth_2_refuses_because_the_board_is_synthesized():
    """At depth >= 1 the board is a SYNTHESIZED StateModel, which cannot be handed back to the
    native engine. Its own scope, because that is different work from proving determinism."""
    api = object()
    assert ao.fate({"type": _ABILITY}, depth=1, search_api=api, deterministic=True) == ao.REFUSED
    r = ao.apply_option(object(), {"type": _ABILITY}, depth=2, search_api=api, deterministic=True)
    assert isinstance(r, ao.Refusal) and r.scope == ao.DEPTH_SCOPE
    assert "synthesized" in r.reason


@pytest.mark.req("REQ-APPLY-0008")
def test_each_engine_precondition_refuses_with_its_own_scope():
    """Three different pieces of work: prove determinism / wire the seam / do not go deep."""
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
    """A bare model would make the telemetry a convention every caller can forget; the wrapper makes
    the engine's involvement part of the value you must handle."""
    er = ao.EngineResolved(model="board", kind=_ABILITY,
                           clause_gap="1182 Boss’s Orders: no `gust` clause kind")
    assert ao.must_expand(er) is False
    assert ao.require_model(er) == "board"
    assert er.clause_gap


@pytest.mark.req("REQ-APPLY-0008")
def test_the_engine_telemetry_names_the_CARD_now_that_every_kind_can_reach_it():
    """With the route open to every kind, a backlog line reading "kind 7" covers most of the corpus
    at once. Extended in the EXISTING field, so a caller filling only one cannot drop half of it."""
    import inspect
    fields = set(ao.EngineResolved.__dataclass_fields__)
    assert "clause_gap" in fields
    assert not (fields & {"card", "card_id", "card_name"}), "extend the field, do not add a second"
    src = inspect.getsource(ao.EngineResolved)
    assert "must name the CARD" in src and "<card id> <card name>" in src


@pytest.mark.req("REQ-APPLY-0008")
def test_the_search_api_seam_is_named_as_preserved_not_deleted():
    """Issue #263 retires `_search_api` as a runtime ROLLOUT and keeps the SEAM, which is not the
    natural reading of "the rollout is retired"."""
    doc = ao.__doc__ or ""
    assert "_search_api" in doc and "do not design as if it disappears" in doc.lower()


# ── §3b: per-kind READ/WRITE footprints ───────────────────────────────────────────────────────────


@pytest.mark.req("REQ-APPLY-0009")
def test_an_uncharacterised_kind_commutes_with_NOTHING():
    """A footprint that UNDER-reports licenses a reorder that changes the board, so the default is
    incomplete — and incomplete commutes with nothing, itself included."""
    assert ao.footprint(_PLAY).complete is False            # per-card effects: no kind-level answer
    assert ao.commutes(_PLAY, _ATTACH) is False
    assert ao.commutes(_PLAY, _PLAY) is False
    assert ao.commutes(999, 999) is False


@pytest.mark.req("REQ-APPLY-0009")
def test_two_kinds_conflict_when_one_reads_what_the_other_writes():
    """Hand INDICES are how options encode their card, so reordering two hand plays genuinely
    changes the later option set."""
    attach, evolve = ao.footprint(_ATTACH), ao.footprint(_EVOLVE)
    assert attach.complete and evolve.complete
    assert "my_hand_ids" in attach.writes & evolve.writes
    assert ao.commutes(_ATTACH, _EVOLVE) is False


@pytest.mark.req("REQ-APPLY-0009")
def test_a_revealer_never_joins_a_commutative_block_whatever_its_footprint_says():
    """A reveal changes the OPTION SET, not only the board, so read/write analysis cannot clear it."""
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
    """A Stadium REPLACES the one in play, and both discards are written because the displaced one
    goes to its OWNER's pile. The footprint stays INCOMPLETE: the sets are a declared FLOOR."""
    fp = ao.footprint(_PLAY)
    assert fp.complete is False and ao.commutes(_PLAY, _PLAY) is False
    assert {"stadium", "allowance_stadium_played"} <= fp.reads
    assert {"stadium", "allowance_stadium_played"} <= fp.writes
    # the structural half: no card's effect text is read to know any of these three
    assert {"my_hand_ids", "my_discard_contents", "their_discard_contents"} <= fp.writes
    # the floor is asserted to BE a floor by naming a zone only the per-card EFFECT can write
    assert "deck_odds" not in (fp.reads | fp.writes)


@pytest.mark.req("REQ-APPLY-0009")
def test_footprints_speak_the_coverage_registrys_field_vocabulary():
    """A zone `snapshot_coverage` never heard of looks like analysis and corresponds to nothing."""
    from common import snapshot_coverage as sc
    for kind, fp in ao.FOOTPRINTS.items():
        unknown = sorted((fp.reads | fp.writes) - set(sc.BY_ID))
        assert unknown == [], (kind, unknown)


# ── §3b: PER-OPTION footprints (POC-T4/2, Issue #383) ─────────────────────────────────────────────
# The kind's FLOOR unioned with `CLAUSE_WRITES` over the card's own clauses. Fixtures are COPIED.
_ITEM_TYPE, _SUPPORTER_TYPE = 1, 3


def _footprint_model(card_id, *, clauses, card_type=_ITEM_TYPE):
    """Carries a `CardEffects`, because a per-OPTION footprint is a question about a CARD."""
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
    """`gust` writes three zones absent from `_PLAY`'s structural floor."""
    from common import snapshot_coverage as sc
    model, option = _footprint_model(1182, clauses=[{"kind": "gust", "target": "any"}],
                                     card_type=_SUPPORTER_TYPE)
    fp = ao.option_footprint(model, option, clauses_cover=True)
    assert ao.footprint(_PLAY).writes <= fp.writes                 # the floor survives
    assert sc.CLAUSE_WRITES["gust"] <= fp.writes                   # ...and the clauses join it
    assert fp.reveals_information is False                         # a gust moves a body, reveals none


@pytest.mark.req("REQ-APPLY-0009")
def test_a_per_option_footprint_ARMS_reveals_information_from_the_registry():
    """No entry in `FOOTPRINTS` sets the flag, so the kind table alone can never reach that clause.
    The empty list is the positive control: absence is real, not a bad search."""
    assert [k for k, f in ao.FOOTPRINTS.items() if f.reveals_information] == []
    model, option = _footprint_model(
        1125, clauses=[{"kind": "fetch", "target": "pokemon", "zone": "deck"}])
    fp = ao.option_footprint(model, option, clauses_cover=True)
    assert fp.reveals_information is True
    assert ao.footprints_commute(fp, ao.footprint(_RETREAT)) is False


@pytest.mark.req("REQ-APPLY-0009")
def test_a_CLAUSELESS_play_card_is_UNKNOWN_and_never_an_empty_write_set():
    """A union over NO clauses is the empty set, and an empty write-set reads as "conflicts with
    nobody" — licensing every reorder. It must read as UNKNOWN instead."""
    model, option = _footprint_model(1141, clauses=None)
    fp = ao.option_footprint(model, option)
    assert fp.complete is False
    assert ao.footprints_commute(fp, fp) is False
    assert ao.footprints_commute(fp, ao.footprint(_RETREAT)) is False
    # ...and a CALLER asserting coverage cannot complete it either: `True` over an EMPTY clause
    # list is coverage asserted over the compendium's silence.
    assert ao.option_footprint(model, option, clauses_cover=True).complete is False
    assert ao.option_footprint(model, option, clauses_cover=True).writes == ao.footprint(_PLAY).writes


@pytest.mark.req("REQ-APPLY-0009")
def test_completeness_needs_the_CALLERS_clause_coverage_proof_not_merely_some_clauses():
    """The same tri-state `fate` takes: `False` is Issue #300's *partial* verdict and can never
    complete anything; `None` is absence of a verdict and fails closed."""
    model, option = _footprint_model(1182, clauses=[{"kind": "gust", "target": "any"}],
                                     card_type=_SUPPORTER_TYPE)
    assert ao.option_footprint(model, option, clauses_cover=True).complete is True
    assert ao.option_footprint(model, option, clauses_cover=False).complete is False
    assert ao.option_footprint(model, option, clauses_cover=None).complete is False


@pytest.mark.req("REQ-APPLY-0009")
def test_an_undeclared_clause_value_makes_the_footprint_unknown_rather_than_narrower():
    """Fail closed against vocabulary drift: an unknown clause contributes no zones, and treating
    that silence as "writes nothing" is the under-report `Footprint` calls worse than none."""
    model, option = _footprint_model(1182, clauses=[{"kind": "a_clause_nobody_declared"}])
    assert ao.option_footprint(model, option, clauses_cover=True).complete is False


@pytest.mark.req("REQ-APPLY-0009")
def test_a_clause_write_is_also_declared_a_clause_READ():
    """No read-set for a clause is shipped, so every zone a clause writes is declared READ too:
    over-reporting only refuses a block it might have allowed, never licenses a wrong one."""
    from common import snapshot_coverage as sc
    model, option = _footprint_model(1182, clauses=[{"kind": "gust", "target": "any"}],
                                     card_type=_SUPPORTER_TYPE)
    fp = ao.option_footprint(model, option, clauses_cover=True)
    assert sc.CLAUSE_WRITES["gust"] <= fp.reads


@pytest.mark.req("REQ-APPLY-0009")
def test_commutes_delegates_to_the_ONE_disjointness_test():
    """`commutes` is the per-KIND door onto `footprints_commute` and `option_footprint` the
    per-OPTION one: two callers, never two copies of the test (ADR-0087)."""
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
def test_the_KIND_level_answer_is_UNCHANGED_by_the_element_ruling():
    """An element is an INSTANCE and a KIND has no instance, so the element-level refinement
    (ADR-0098 Amendment D) lives entirely in `option_footprint` and licenses nothing here."""
    import itertools
    kinds = sorted(ao.KIND_COVERAGE)
    assert [(a, b) for a, b in itertools.combinations_with_replacement(kinds, 2)
            if ao.commutes(a, b)] == []
    assert "my_hand_ids" in ao.footprint(_ATTACH).writes & ao.footprint(_EVOLVE).writes
    assert ao.footprint(_ATTACH).write_elements == frozenset()      # a KIND has no instance


# ── the RULED element-level granularity (Issue #263, granted 2026-08-04) ──────────────────────────
# `docs/rules.md` §3 caps the MANUAL Energy attachment; a Tool is an ordinary Trainer play.
_RIOLU, _MEGA_LUC, _E_F, _TOOL = 677, 678, 6, 1159
_TOOL_TYPE, _BASIC_ENERGY_TYPE = 2, 5
_FIGHTING = 6


def _triple_board():
    """Distinct targets ON PURPOSE: a fixture pointing all three at one body would test the
    rejection, not the licence."""
    from common.cards import CardFunctions
    from common.effects import CardEffects
    from common.scouting.provider import CardStat, DictCardStatProvider
    from common.state_model import StateModel
    from common.strategy.combat import CombatMath
    stats = {
        _RIOLU: CardStat(_RIOLU, name="Riolu", hp=80, energyType=_FIGHTING),
        _MEGA_LUC: CardStat(_MEGA_LUC, name="Mega Lucario ex", hp=340, megaEx=True, ex=True,
                            energyType=_FIGHTING, evolvesFrom="Riolu"),
        _E_F: CardStat(_E_F, name="Basic {F} Energy", cardType=_BASIC_ENERGY_TYPE,
                       energyType=_FIGHTING),
        _TOOL: CardStat(_TOOL, synthetic=True, name="Flat-HP Tool", cardType=_TOOL_TYPE,
                        hpBonus=100),
    }
    combat = CombatMath(DictCardStatProvider(stats), functions=CardFunctions({}), transients=None,
                        effects=CardEffects({}))

    def body(serial):
        return {"id": _RIOLU, "serial": serial, "playerIndex": 0, "hp": 80, "maxHp": 80,
                "appearThisTurn": False, "energies": [], "energyCards": [], "tools": [],
                "preEvolution": []}
    # Hand indices are load-bearing below: 0 Energy / 1 evolution / 2 Tool is the commuting
    # triple, 3 a SECOND Energy, 4-5 two Basics.
    me = {"active": [body(10)], "bench": [body(11), body(12)], "benchMax": 5,
          "hand": [{"id": _E_F, "serial": 701, "playerIndex": 0},
                   {"id": _MEGA_LUC, "serial": 702, "playerIndex": 0},
                   {"id": _TOOL, "serial": 703, "playerIndex": 0},
                   {"id": _E_F, "serial": 704, "playerIndex": 0},
                   {"id": _RIOLU, "serial": 705, "playerIndex": 0},
                   {"id": _RIOLU, "serial": 706, "playerIndex": 0}],
          "handCount": 6, "discard": [], "prize": [None] * 6}
    opp = {"active": [], "bench": [], "benchMax": 5, "hand": [], "handCount": 0, "discard": [],
           "prize": [None] * 6}
    obs = {"current": {"players": [me, opp], "yourIndex": 0, "stadium": []},
           "select": {"context": 0, "option": []}}
    return StateModel.build(obs, combat=combat, deck=[_RIOLU] * 4)


@pytest.mark.req("REQ-APPLY-0009")
def test_the_ENERGY_EVOLUTION_TOOL_triple_provably_commutes():
    """At ZONE granularity this was unprovable — all three collide on `my_hand_ids`. Element-level,
    each names a distinct hand serial and target body, so the 3! orderings are ONE candidate."""
    from common.option_equivalence import AREA_ACTIVE, AREA_BENCH, AREA_HAND
    model = _triple_board()
    energy = ao.option_footprint(model, {"type": _ATTACH, "area": AREA_HAND, "index": 0,
                                         "inPlayArea": AREA_BENCH, "inPlayIndex": 0})
    evolve = ao.option_footprint(model, {"type": _EVOLVE, "area": AREA_HAND, "index": 1,
                                         "inPlayArea": AREA_BENCH, "inPlayIndex": 1})
    tool = ao.option_footprint(model, {"type": _ATTACH, "area": AREA_HAND, "index": 2,
                                       "inPlayArea": AREA_ACTIVE, "inPlayIndex": 0})
    assert energy.complete and evolve.complete and tool.complete
    assert ao.footprints_commute(energy, evolve) is True
    assert ao.footprints_commute(energy, tool) is True
    assert ao.footprints_commute(evolve, tool) is True


@pytest.mark.req("REQ-APPLY-0009")
def test_two_ENERGY_attaches_do_NOT_commute_on_the_per_turn_allowance():
    """Two Energy attaches have disjoint ELEMENTS everywhere an element exists, so the only thing
    left to refuse them is `allowance_energy_attached` being whole-zone. The last assertion proves it."""
    import dataclasses

    from common import snapshot_coverage as sc
    from common.option_equivalence import AREA_BENCH, AREA_HAND
    model = _triple_board()
    a = ao.option_footprint(model, {"type": _ATTACH, "area": AREA_HAND, "index": 0,
                                    "inPlayArea": AREA_BENCH, "inPlayIndex": 0})
    b = ao.option_footprint(model, {"type": _ATTACH, "area": AREA_HAND, "index": 3,
                                    "inPlayArea": AREA_BENCH, "inPlayIndex": 1})
    assert a.complete and b.complete
    assert a.write_elements != b.write_elements                            # genuinely distinct cards
    assert "allowance_energy_attached" in a.writes & b.writes
    assert "allowance_energy_attached" not in sc.ELEMENT_ZONES             # the load-bearing fact
    assert ao.footprints_commute(a, b) is False
    without = [dataclasses.replace(fp, reads=fp.reads - {"allowance_energy_attached"},
                                   writes=fp.writes - {"allowance_energy_attached"})
               for fp in (a, b)]
    assert ao.footprints_commute(*without) is True     # ...so the allowance WAS the only rejector


@pytest.mark.req("REQ-APPLY-0009")
def test_two_BASICS_competing_for_the_last_bench_slot_do_NOT_commute():
    """Three assertions, and only two bite: a clause-less `_PLAY` is independently UNKNOWN, so the
    end-to-end pair would refuse anyway. Forcing both `complete` is what isolates `bench_occupancy`."""
    import dataclasses

    from common.option_equivalence import AREA_HAND
    # 1. the mechanism, isolated: same footprints, with and without the zone-level bench write.
    slotless_a = ao.Footprint(reads=frozenset({"my_hand_ids"}), writes=frozenset({"my_hand_ids"}),
                              complete=True,
                              read_elements=frozenset({("my_hand_ids", 701)}),
                              write_elements=frozenset({("my_hand_ids", 701)}))
    slotless_b = ao.Footprint(reads=frozenset({"my_hand_ids"}), writes=frozenset({"my_hand_ids"}),
                              complete=True,
                              read_elements=frozenset({("my_hand_ids", 702)}),
                              write_elements=frozenset({("my_hand_ids", 702)}))
    assert ao.footprints_commute(slotless_a, slotless_b) is True     # distinct hand instances
    bench_a = ao.Footprint(reads=slotless_a.reads | {"bench_occupancy"},
                           writes=slotless_a.writes | {"bench_occupancy"}, complete=True,
                           read_elements=slotless_a.read_elements,
                           write_elements=slotless_a.write_elements)
    bench_b = ao.Footprint(reads=slotless_b.reads | {"bench_occupancy"},
                           writes=slotless_b.writes | {"bench_occupancy"}, complete=True,
                           read_elements=slotless_b.read_elements,
                           write_elements=slotless_b.write_elements)
    assert ao.footprints_commute(bench_a, bench_b) is False          # the last-slot rejection
    # 2. end to end, on the two REAL Riolu deploys (hand indices 4 and 5, serials 705 / 706).
    model = _triple_board()
    play_a = ao.option_footprint(model, {"type": _PLAY, "area": AREA_HAND, "index": 4})
    play_b = ao.option_footprint(model, {"type": _PLAY, "area": AREA_HAND, "index": 5})
    assert play_a.write_elements != play_b.write_elements       # distinct hand instances...
    assert "bench_occupancy" in play_a.writes & play_b.writes   # ...contending for one slot count
    assert ao.footprints_commute(play_a, play_b) is False
    # 3. ...and NOT merely because a clause-less `_PLAY` is UNKNOWN. Grant both completeness — the
    #    one gate that would otherwise short-circuit the test — and `bench_occupancy` must still bite.
    assert play_a.complete is False and play_b.complete is False
    forced = [dataclasses.replace(fp, complete=True) for fp in (play_a, play_b)]
    assert ao.footprints_commute(*forced) is False


@pytest.mark.req("REQ-APPLY-0009")
def test_two_writes_to_the_SAME_instance_do_not_commute():
    """Not pedantic: `board_delta._attach` re-derives provision against the target's STAGE, so
    Ignition Energy renders `[0]` on a Basic and `[0,0,0]` on an Evolution."""
    from common.option_equivalence import AREA_BENCH, AREA_HAND
    model = _triple_board()
    energy = ao.option_footprint(model, {"type": _ATTACH, "area": AREA_HAND, "index": 0,
                                         "inPlayArea": AREA_BENCH, "inPlayIndex": 0})
    evolve_same = ao.option_footprint(model, {"type": _EVOLVE, "area": AREA_HAND, "index": 1,
                                              "inPlayArea": AREA_BENCH, "inPlayIndex": 0})
    assert ao.footprints_commute(energy, evolve_same) is False
    # ...and the ONLY difference from the commuting pair above is which body it names.
    evolve_other = ao.option_footprint(model, {"type": _EVOLVE, "area": AREA_HAND, "index": 1,
                                               "inPlayArea": AREA_BENCH, "inPlayIndex": 1})
    assert ao.footprints_commute(energy, evolve_other) is True


@pytest.mark.req("REQ-APPLY-0009")
def test_an_element_zone_with_UNDECLARED_elements_commutes_with_nothing():
    """A footprint may write an element zone WITHOUT knowing which element — a shuffle rewrites the
    whole hand, and a `_RETREAT` carries no target at all. Unresolved is UNKNOWN, so it conflicts."""
    named = ao.Footprint(reads=frozenset(), writes=frozenset({"my_hand_ids"}), complete=True,
                         write_elements=frozenset({("my_hand_ids", 701)}))
    unresolved = ao.Footprint(reads=frozenset(), writes=frozenset({"my_hand_ids"}), complete=True)
    assert ao.footprints_commute(named, unresolved) is False
    assert ao.footprints_commute(unresolved, unresolved) is False
    # ...while two NAMED, distinct instances are exactly what the ruling licenses.
    other = ao.Footprint(reads=frozenset(), writes=frozenset({"my_hand_ids"}), complete=True,
                         write_elements=frozenset({("my_hand_ids", 702)}))
    assert ao.footprints_commute(named, other) is True


@pytest.mark.req("REQ-APPLY-0009")
def test_the_element_refinement_does_not_loosen_ANY_item_1_fail_closed_rule():
    """All three gates still veto BEFORE elements are consulted, so no amount of instance precision
    rescues an incomplete, partial or revealing footprint."""
    elems = frozenset({("my_hand_ids", 701)})
    other = frozenset({("my_hand_ids", 702)})
    incomplete = ao.Footprint(writes=frozenset({"my_hand_ids"}), write_elements=elems)
    complete = ao.Footprint(writes=frozenset({"my_hand_ids"}), complete=True, write_elements=other)
    revealer = ao.Footprint(writes=frozenset({"my_hand_ids"}), complete=True, write_elements=other,
                            reveals_information=True)
    assert ao.footprints_commute(incomplete, complete) is False       # unknown => nothing
    assert ao.footprints_commute(revealer, ao.Footprint(
        writes=frozenset({"my_hand_ids"}), complete=True, write_elements=elems)) is False
    # ...and a clause-less `_PLAY` is still UNKNOWN however precisely it names its hand card.
    model, option = _footprint_model(1141, clauses=None)
    assert ao.option_footprint(model, option, clauses_cover=True).complete is False


@pytest.mark.req("REQ-APPLY-0009")
def test_a_TOOL_attach_does_not_declare_the_energy_allowance_and_an_energy_does_not_declare_tools():
    """The `_ATTACH` kind footprint is the UNION of two legs that never both fire; splitting them
    per-option is what lets an Energy and a Tool sit in one block."""
    from common.option_equivalence import AREA_BENCH, AREA_HAND
    model = _triple_board()
    energy = ao.option_footprint(model, {"type": _ATTACH, "area": AREA_HAND, "index": 0,
                                         "inPlayArea": AREA_BENCH, "inPlayIndex": 0})
    tool = ao.option_footprint(model, {"type": _ATTACH, "area": AREA_HAND, "index": 2,
                                       "inPlayArea": AREA_BENCH, "inPlayIndex": 0})
    assert "allowance_energy_attached" in energy.writes
    assert "allowance_energy_attached" not in tool.writes and \
           "allowance_energy_attached" not in tool.reads
    assert "attached_energy" in energy.writes and "attached_energy" not in tool.writes
    assert "attached_tools" in tool.writes and "attached_tools" not in energy.writes
    # The union is still what the KIND declares — the narrowing is per-option, not a table change.
    assert energy.writes | tool.writes >= ao.footprint(_ATTACH).writes


# ── refusal is a RESULT, not an exception and not a no-op ─────────────────────────────────────────


@pytest.mark.req("REQ-APPLY-0005")
def test_an_unmodellable_kind_returns_a_REFUSAL_not_a_silent_no_op():
    """A no-op prices the option at 0.0 delta, which at ordering time is "never explored" rather
    than "undervalued". `KIND_SCOPE` is documented as no longer emitted rather than deleted."""
    r = ao.apply_option(object(), {"type": _SKILL})
    assert isinstance(r, ao.Refusal)
    assert r.kind == _SKILL and r.scope == ao.NONDETERMINISM_SCOPE and r.reason.strip()
    assert ao.coverage(_SKILL) == ao.REFUSED         # the TABLE still says the kind is unmodellable


@pytest.mark.req("REQ-APPLY-0005")
def test_a_kind_the_engine_grows_later_refuses_rather_than_raising():
    """`src/cg/api.py` says new members may be appended DURING the competition, and on the 1-ply
    hot path a raise is a forfeited grader match over an option we merely could not price."""
    r = ao.apply_option(object(), {"type": 999})
    assert isinstance(r, ao.Refusal) and r.scope == ao.UNDECLARED_SCOPE
    assert ao.coverage(999) == ao.UNDECLARED
    assert ao.transition_kind({"type": 999}) == 999      # never raises


@pytest.mark.req("REQ-APPLY-0005")
def test_a_refusal_means_ALWAYS_EXPAND_and_that_policy_has_one_home():
    """An option with no PRICE is not an option with no value — it has no ESTIMATE, and expanding is
    how the beam finds out. A named function, so no caller re-derives it from `isinstance`."""
    assert ao.must_expand(ao.apply_option(object(), {"type": _ABILITY})) is True
    assert ao.must_expand(ao.Expectation()) is False
    assert ao.must_expand(object()) is False


@pytest.mark.req("REQ-APPLY-0005")
def test_a_refusal_inside_a_modelled_kind_is_expressible_per_option():
    """A Trainer's EFFECT is per-card, so refusal cannot be a property of the KIND alone."""
    r = ao.refuse({"type": _PLAY}, "no compendium entry for this Trainer's effect")
    assert r.scope == ao.OPTION_SCOPE and r.kind == _PLAY
    assert ao.coverage(_PLAY) == ao.MODELLED          # the KIND is untouched
    with pytest.raises(ValueError):
        ao.refuse({"type": _PLAY}, "   ")             # a refusal must say why — telemetry reads it


@pytest.mark.req("REQ-APPLY-0005")
def test_a_caller_that_requires_a_model_raises_on_a_refusal():
    """The parity lane is the ONE caller allowed to turn a refusal back into an exception; the
    ordering path is explicitly not it (ADR-0098)."""
    with pytest.raises(ao.UnsupportedTransition):
        ao.require_model(ao.apply_option(object(), {"type": _ABILITY}))
    sentinel = ao.Expectation(classes=(ao.OutcomeClass(1.0),))
    assert ao.require_model(sentinel) is sentinel


@pytest.mark.req("REQ-APPLY-0001")
def test_applying_a_terminal_option_is_an_error_not_an_unchanged_model():
    """RAISES rather than refusing: an API misuse, not a modelling gap — the caller was told to
    test `is_terminal` first."""
    with pytest.raises(ValueError):
        ao.apply_option(object(), {"type": _ATTACK})


@pytest.mark.req("REQ-APPLY-0002")
def test_a_transition_that_cannot_be_computed_refuses_rather_than_returning_the_model_unchanged():
    """Fed a model it cannot transition from, the seam must not hand back something that differences
    to ZERO — 0.0 is a real, plausible answer and would read as "nothing is worth doing"."""
    for kind in sorted(ao.TRANSITION_KINDS):
        r = ao.apply_option(object(), {"type": kind})
        assert isinstance(r, ao.Refusal), kind
        assert r.kind == kind and r.scope == ao.OPTION_SCOPE and r.reason.strip(), kind
        assert ao.must_expand(r) is True, kind


# ── the EXPECTATION shape ─────────────────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-APPLY-0003")
def test_a_complete_expectation_sums_to_one_and_a_capped_one_reports_its_truncation():
    """The probability GAP is the truncation, so a capped enumeration cannot read as a complete one
    and make an under-explored line look confidently valued."""
    complete = ao.Expectation(classes=(ao.OutcomeClass(0.25), ao.OutcomeClass(0.75)))
    assert complete.total_probability == pytest.approx(1.0)
    assert complete.truncated == 0

    capped = ao.Expectation(classes=(ao.OutcomeClass(0.6),), truncated=3)
    assert capped.total_probability == pytest.approx(0.6)
    assert capped.truncated == 3


@pytest.mark.req("REQ-APPLY-0006")
def test_an_expectation_yields_one_comparable_number_at_1_ply():
    """A draw Supporter must be ORDERABLE, not merely expandable: the composer ranks it against a
    Tool attach on the same scale before deciding to expand anything."""
    e = ao.Expectation(classes=(ao.OutcomeClass(0.25, model="a"), ao.OutcomeClass(0.75, model="b")))
    assert e.expected({"a": 4.0, "b": 8.0}.__getitem__) == pytest.approx(7.0)


@pytest.mark.req("REQ-APPLY-0006")
def test_the_number_that_ORDERS_is_the_MAX_and_expected_is_the_reported_lower_bound():
    """Both producers emit a CHOICE node, and the value of a choice is the value of the BEST branch
    (Issue #385 §S3). The fixture makes the max the UNLIKELIEST branch, so a modal read shows."""
    e = ao.Expectation(classes=(ao.OutcomeClass(0.75, model="a"), ao.OutcomeClass(0.25, model="b")))
    score = {"a": 4.0, "b": 8.0}.__getitem__
    assert e.best(score) == pytest.approx(8.0)
    assert e.expected(score) == pytest.approx(5.0)
    assert e.best(score) > e.expected(score)


@pytest.mark.req("REQ-APPLY-0006")
def test_the_max_IGNORES_the_probabilities_because_the_chooser_picks():
    """Averaging over a set the chooser PICKS from prices the choice as if it were made for them.
    Asserted by moving the weights only and requiring the answer not to move."""
    score = {"a": 4.0, "b": 8.0}.__getitem__
    flat = ao.Expectation(classes=(ao.OutcomeClass(0.5, model="a"), ao.OutcomeClass(0.5, model="b")))
    skewed = ao.Expectation(classes=(ao.OutcomeClass(0.99, model="a"),
                                     ao.OutcomeClass(0.01, model="b")))
    assert flat.best(score) == skewed.best(score) == pytest.approx(8.0)
    assert flat.expected(score) != pytest.approx(skewed.expected(score))


@pytest.mark.req("REQ-APPLY-0006")
def test_the_max_of_an_unenumerated_expectation_raises_rather_than_returning_zero():
    """Both bounds must fail the SAME way, or a caller switching between them changes its failure
    mode by accident."""
    with pytest.raises(ValueError):
        ao.Expectation().best(lambda m: 1.0)


@pytest.mark.req("REQ-APPLY-0006")
def test_a_truncated_expectation_orders_on_the_mass_it_enumerated():
    """Renormalised over the SURVIVING mass: letting truncated mass contribute 0 biases against the
    widest enumerations, which are the draw and search effects this exists to stop pruning."""
    e = ao.Expectation(classes=(ao.OutcomeClass(0.25, model="x"), ao.OutcomeClass(0.25, model="y")),
                       truncated=2)
    assert e.total_probability == pytest.approx(0.5)      # the gap stays visible
    assert e.expected(lambda m: 6.0) == pytest.approx(6.0)


@pytest.mark.req("REQ-APPLY-0006")
def test_ordering_an_unenumerated_expectation_raises_rather_than_returning_zero():
    """0.0 is a real score, so returning it prices an UN-enumerated effect as a worthless one."""
    with pytest.raises(ValueError):
        ao.Expectation().expected(lambda m: 1.0)


@pytest.mark.req("REQ-APPLY-0003")
def test_an_outcome_class_carries_its_option_equivalence_fingerprint():
    """Enumerated by Option-Equivalence identity (ADR-0091), not card identity: two indistinguishable
    reveals are ONE outcome."""
    oc = ao.OutcomeClass(0.5, fingerprint=(7, 0, (("hand", 1121),)))
    assert oc.fingerprint == (7, 0, (("hand", 1121),))
    assert oc.model is None                       # filled by T4


@pytest.mark.req("REQ-APPLY-0003")
def test_an_expectation_defaults_to_empty_rather_than_to_a_certain_outcome():
    """A default of one class at probability 1.0 would read as a DETERMINISTIC transition."""
    assert ao.Expectation().classes == ()
    assert ao.Expectation().total_probability == 0.0


# ── the quarantine registry ───────────────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-APPLY-0004")
def test_nothing_is_quarantined_before_the_parity_lane_exists():
    """Deliberately EMPTY until the parity lane is wired (ADR-0098 decision 4). It lives beside the
    seam because the SEAM is what diverges, and several consumers must read one answer."""
    assert ao.quarantined_kinds() == frozenset()


@pytest.mark.req("REQ-APPLY-0004")
def test_a_quarantined_kind_refuses_through_the_same_path_as_any_other_gap(monkeypatch):
    """ONE answer, so the planner never consults two registries and has to agree with itself."""
    monkeypatch.setattr(ao, "quarantined_kinds", lambda: frozenset({_ATTACH}))
    assert ao.coverage(_ATTACH) == ao.REFUSED
    r = ao.apply_option(object(), {"type": _ATTACH})
    assert isinstance(r, ao.Refusal) and r.scope == ao.QUARANTINE_SCOPE
    assert ao.must_expand(r) is True


# ── the seam stays engine-free ────────────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-APPLY-0002")
def test_the_module_never_reaches_for_an_engine():
    """The whole argument for this seam is that the engine is NOT on the runtime path — and a stray
    import maps the native library into a suite that must run DLL-free."""
    import inspect
    src = inspect.getsource(ao)
    for forbidden in ("from cg import", "import cg.api", "import cgpy", "search_begin("):
        assert forbidden not in src, forbidden


@pytest.mark.req("REQ-APPLY-0002")
def test_the_seam_records_that_it_cannot_price_information_ordering():
    """A later track assuming the planner discovers information-first sequencing would ship an agent
    that commits before it digs, so the limitation is written where an implementer reads it."""
    doc = ao.__doc__ or ""
    assert "cannot capture information value" in doc
    assert "same end state" in doc.lower()


@pytest.mark.req("REQ-APPLY-0007")
def test_the_seam_states_that_transitions_are_lazy_rather_than_deep_copies():
    """1-ply ordering runs this once per candidate per decision, so an eager deep copy per branch is
    a cost the grader's 2 vCPUs will not absorb (ADR-0068)."""
    doc = (ao.__doc__ or "") + (ao.apply_option.__doc__ or "")
    assert "lazy" in doc.lower() and "ADR-0068" in doc
    assert "deep copy" in doc.lower()
