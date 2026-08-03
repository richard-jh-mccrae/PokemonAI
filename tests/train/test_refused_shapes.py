"""`gates.shape_the_constructor_would_refuse` / `gates.refused_shapes` — the **Refused Shape** audit
(Issue #256, ADR-0113 decision 4).

`build_correction` validates at *write* time. `Correction.from_dict` — THE loader, and so what the
**Corpus Reader** inherits — validates nothing. That asymmetry is deliberate and stays: validating on
load would reject committed records at read time and take *both* gates down over a record that has
been sitting green for weeks. But unvalidated must not mean unobserved, and until this audit nothing
re-applied the writer's rules to what was already on disk — which is how `85709280|1|match|`
(`match` scope carrying `correct: [0]`, hand-edited past the constructor on 2026-07-29) got in, and
stayed, *grading in both gates*, until the developer reviewed the finding and repaired it (ADR-0113
Amendment A): re-scoped to `decision`/subject 51, where `correct: [0]` is a legal shape. The corpus
is clean today — the census below asserts that, not "exactly one" — and the repaired record's key,
`85709280|1|decision|51`, is what `THE_RECORD` now names.

The census here is worthless without the controls, and this repo has a named failure mode for exactly
that (`CLAUDE.md`): an instrument that finds nothing and a broken instrument return the same empty
output. So every "exactly one" assertion below is paired with a synthetic record of the shape it
claims is absent, and — the strongest control — with a differential test that drives the REAL
`build_correction` with the same shape and asserts it raises. The audit claims to re-apply the
constructor's rules; a test that only exercised a paraphrase could not tell a faithful re-application
from a plausible one.
"""
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from train.gates import (REFUSED_SHAPE_RULES, refused_shapes,  # noqa: E402
                         shape_the_constructor_would_refuse as refuses)

#: The record this whole audit was built to find, and its two keys. It shipped `match` scope
#: carrying a `correct` the constructor forbids (hand-edited past it on 2026-07-29) until the
#: developer reviewed the wave-3 packet and ruled: the rationale was always about ONE select, never
#: a whole-match note, so re-scoping to `decision`/subject 51 invents nothing and costs nothing — the
#: record's `span` (a genuine turn-by-turn Game Plan trace, ADR-0045) survives untouched (ADR-0113
#: Amendment A). `THE_RECORD_WAS` no longer resolves; kept so a test can assert exactly that.
THE_RECORD = "85709280|1|decision|51"
THE_RECORD_WAS = "85709280|1|match|"


@dataclass
class _Rec:
    """The duck type the predicate reads — a `Correction` in production."""
    correct: list | None = None
    chosen: list = field(default_factory=list)
    scope: str = "decision"
    source: str = "own"
    decision: dict = field(default_factory=lambda: {"options": [{}, {}, {}, {}]})
    obs: dict | None = field(default_factory=lambda: {"select": {"minCount": 1}})
    id: str = "synthetic"


def _decision(n_options=4, chosen=(1,)):
    """A real `Decision` the REAL constructor accepts — the differential tests' input."""
    from train.blunder.decisions import Decision
    return Decision(episode_id=99999999, frame=7, seat=0, turn=3,
                    select_context="Main", select_type="Main",
                    options=[{"type": 7, "index": i} for i in range(n_options)],
                    chosen=list(chosen), current={}, obs={"select": {"minCount": 1}})


def _build(**kw):
    from train.blunder.correction import build_correction
    base = dict(source="own", agent="mega_lucario", category="missed_win", rationale="r")
    return build_correction(_decision(), **{**base, **kw})


# ---------------------------------------------------------------------------
# Per-shape POSITIVE CONTROLS — the audit finds each shape, and the constructor
# really does refuse the same shape. (Acceptance criterion 4.)
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-GATE-0009")
def test_a_record_the_constructor_would_accept_is_clean():
    """The baseline the whole census rests on. If this ever returned a violation, every "exactly
    one" assertion below would be measuring noise."""
    assert refuses(_Rec(correct=[2], chosen=[1])) == []


@pytest.mark.req("REQ-GATE-0009")
def test_a_match_scope_record_is_caught_as_unknown_scope():
    """Issue #353: `match` is retired, so a hand-edited match record is an unknown scope."""
    assert refuses(_Rec(scope="match", correct=[0], chosen=[2])) == ["unknown_scope"]


@pytest.mark.req("REQ-GATE-0009")
def test_a_turn_scope_correct_equal_to_chosen_is_caught():
    """ADR-0049's *first divergent Decision* assertion, enforced. A turn-scope `correct` repeating
    `chosen` asserts nothing — and it is the rule **decision D2** rests on, so if it ever stopped
    being enforced, D2's claim that Anchor grading is deliberate would quietly become false."""
    assert refuses(_Rec(scope="turn", correct=[1], chosen=[1])) == ["turn_correct_equals_chosen"]
    # Compared as SETS, exactly as the constructor compares them — order is not a second ruling.
    assert refuses(_Rec(scope="turn", correct=[1, 0], chosen=[0, 1])) == \
        ["turn_correct_equals_chosen"]
    # ... and a turn-scope record that DOES diverge is clean, which is what makes the rule a rule.
    assert refuses(_Rec(scope="turn", correct=[2], chosen=[1])) == []


@pytest.mark.req("REQ-GATE-0009")
def test_a_correct_off_the_menu_is_caught():
    """`correct` indexes the **Anchor**'s own options; 4 is off a 4-option menu."""
    assert refuses(_Rec(correct=[4], chosen=[1])) == ["correct_off_the_menu"]
    assert refuses(_Rec(correct=[-1], chosen=[1])) == ["correct_off_the_menu"]
    assert refuses(_Rec(correct=["1"], chosen=[1])) == ["correct_off_the_menu"]


@pytest.mark.req("REQ-GATE-0009")
def test_an_unprovable_decision_scope_decline_is_caught():
    """Issue #229's relaxation is STRICT: an empty `correct` is a **Decline**, admissible at
    `decision` scope only where the record's own `obs` proves the select optional. On a mandatory
    select — or where `minCount` cannot be read at all — the writer refuses, so the audit does too."""
    assert refuses(_Rec(correct=[], chosen=[1])) == ["unprovable_decline"]          # minCount 1
    assert refuses(_Rec(correct=[], chosen=[1], obs=None)) == ["unprovable_decline"]  # unknown
    # PROVED optional -> a legal Decline, and clean. Without this the rule would read as
    # "decision scope may never decline", which is the pre-Issue-#229 world.
    assert refuses(_Rec(correct=[], chosen=[], obs={"select": {"minCount": 0}})) == []
    # An absent `correct` is read as "no option named", the way the constructor's own truthiness
    # test reads it.
    assert refuses(_Rec(correct=None, chosen=[1])) == ["unprovable_decline"]


@pytest.mark.req("REQ-GATE-0009")
def test_the_closed_vocabularies_are_caught_and_an_unknown_scope_stops_the_dispatch():
    """`source` and `scope` are two-and-three-element tuples fixed in `correction.py`. An
    unrecognised `scope` returns alone: every `correct` rule dispatches on scope, so classifying
    further would be guessing."""
    assert refuses(_Rec(correct=[2], chosen=[1], source="enemy")) == ["unknown_source"]
    assert refuses(_Rec(correct=[9], chosen=[1], scope="episode")) == ["unknown_scope"]
    assert refuses(_Rec(correct=[9], chosen=[1], scope="episode", source="enemy")) == \
        ["unknown_source", "unknown_scope"]


@pytest.mark.req("REQ-GATE-0009")
def test_the_category_vocabulary_is_deliberately_NOT_re_applied():
    """The line the audit draws, asserted so a later session does not quietly cross it. `category`'s
    vocabulary lives in `categories.py` and is documented as *extensible*; refusing a committed
    record because a category was later renamed would report a **vocabulary edit as a corpus
    defect** — a different question, needing a ruling rather than a predicate.

    Positive control on the claim itself: the constructor DOES refuse the same value, so this is a
    deliberate omission from the audit rather than a rule that never existed."""
    from train.blunder.categories import is_valid_category
    assert is_valid_category("missed_lethal") is False              # renamed away
    with pytest.raises(ValueError):
        _build(correct=[2], category="missed_lethal")
    # ... and the audit stays quiet about it.
    rec = _Rec(correct=[2], chosen=[1])
    rec.category = "missed_lethal"
    assert refuses(rec) == []


@pytest.mark.req("REQ-GATE-0009")
def test_every_slug_the_predicate_can_emit_has_a_printable_sentence():
    """`REFUSED_SHAPE_RULES` is the one source both the predicate and the readout read, so a slug with no
    sentence would print as a bare identifier in an operator's report."""
    emitted = {"unknown_source", "unknown_scope", "correct_off_the_menu",
               "turn_correct_equals_chosen", "unprovable_decline"}
    assert emitted == set(REFUSED_SHAPE_RULES)
    assert all(REFUSED_SHAPE_RULES[s] and isinstance(REFUSED_SHAPE_RULES[s], str) for s in emitted)


# ---------------------------------------------------------------------------
# DIFFERENTIAL — the audit re-applies the REAL constructor's rules, not a paraphrase.
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-GATE-0009")
@pytest.mark.parametrize("kw,slug", [
    (dict(scope="match", correct=[0]), "unknown_scope"),
    (dict(scope="turn", correct=[1]), "turn_correct_equals_chosen"),   # `_decision` chose [1]
    (dict(correct=[9]), "correct_off_the_menu"),
    (dict(correct=[]), "unprovable_decline"),                          # minCount 1
    (dict(source="enemy", correct=[2]), "unknown_source"),
    (dict(scope="episode", correct=[2]), "unknown_scope"),
])
def test_the_constructor_really_refuses_each_shape_the_audit_names(kw, slug):
    """**The control that makes "would refuse" an honest claim.** Each shape is fed to the REAL
    `build_correction`, which must raise, and to the audit, which must name it. A paraphrase that had
    drifted from the constructor would pass the synthetic tests above and fail here."""
    with pytest.raises(ValueError):
        _build(**kw)
    rec = _Rec(chosen=[1], **{k: v for k, v in kw.items() if k != "agent"})
    assert slug in refuses(rec)


@pytest.mark.req("REQ-GATE-0009")
def test_the_constructor_accepts_the_shape_the_audit_calls_clean():
    """The other direction, and the one that catches an audit gone paranoid: a record the audit
    passes must be one the writer would actually write. Without it, a predicate returning a
    violation for everything would satisfy every `raises` test above."""
    corr = _build(correct=[2])
    assert corr.correct == [2] and corr.scope == "decision"
    assert refuses(corr) == []


# ---------------------------------------------------------------------------
# The committed corpus — the census, and the reason the audit exists.
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-GATE-0009")
def test_the_committed_corpus_holds_no_refused_shapes():
    """**The census.** Measured through the Corpus Reader, never raw JSONL: 23 records carry no
    explicit `scope` key and only default to `decision` inside `Correction.from_dict`, and every rule
    here dispatches on scope.

    Was ``== [THE_RECORD_WAS]`` — the corpus held exactly the one violation this audit was built to
    find, `85709280|1|match|`. The developer reviewed it (the wave-3 packet this issue produced) and
    repaired it rather than excluding it: re-scoped to `decision`/subject 51, where a non-empty
    `correct` is legal (ADR-0113 Amendment A). This assertion is the record of that repair landing —
    it goes red again the moment a SECOND bad shape appears, which is the property the store lacked
    entirely and the whole deliverable of Issue #256."""
    found = refused_shapes(REPO / "data" / "corrections")
    assert found == []


@pytest.mark.req("REQ-GATE-0009")
def test_the_census_positive_control_the_reader_and_the_predicate_both_work():
    """**The control the census is worthless without.** An empty corpus, a broken reader, or a
    predicate that only ever returns ``[]`` would all satisfy "0 refused shapes" while proving
    nothing. So: the reader finds all 372 records, every one is clean — including the repaired
    record, checked by name — and the synthetic + differential tests above already established the
    predicate really does fire (`test_a_match_scope_correct_is_caught`,
    `test_the_constructor_really_refuses_each_shape_the_audit_names`), so "0 here" reads as "clean",
    not as "broken"."""
    from train.gates import keyed_corrections
    recs = keyed_corrections(REPO / "data" / "corrections")
    assert len(recs) == 372
    assert sum(1 for _k, c in recs if not refuses(c)) == 372
    the_record = next(c for k, c in recs if k == THE_RECORD)
    assert refuses(the_record) == []
    assert the_record.scope == "decision" and the_record.correct == [0]
    assert not any(k == THE_RECORD_WAS for k, _c in recs), "the old key must no longer resolve"


@pytest.mark.req("REQ-GATE-0009")
def test_the_corpus_now_holds_no_match_scope_records_at_all():
    """Decision **D1** — *a match-scope Correction should not grade at its Anchor* — was written
    about a corpus that held exactly ONE `match`-scope record (353 decision / 18 turn / 1 match):
    this one. The developer reviewed the wave-3 packet and repaired it rather than ruling D1: the
    record's Anchor rationale was always about ONE select (never a whole-match note), so re-scoping
    to `decision`/subject 51 invents nothing (ADR-0113 Amendment A). D1 therefore has no live
    instance to apply to — `scope="match"` is theoretical vocabulary today, not dead code; a future
    tag can still use it.

    This is the corpus-composition half of that repair. `test_the_repaired_record_still_grades_the_
    same_way` below is the grading half — the fix must be a pure re-label, not a value change."""
    from collections import Counter

    from train.gates import keyed_corrections
    recs = keyed_corrections(REPO / "data" / "corrections")
    assert Counter(c.scope for _k, c in recs) == {"decision": 354, "turn": 18}


@pytest.mark.req("REQ-GATE-0009")
def test_the_repaired_record_still_grades_the_same_way():
    """The repair must be a re-label, not a re-ruling: `correct`/`chosen`/`span` are untouched, so
    whatever the gate concluded about this frame before must still hold after.

    ⚠️ **The gate grades the PILOT's fresh replay pick, not the record's own `chosen` field.** The
    record's historical `chosen` is `[2]`; the committed baseline row's `chosen` is `[0]` — what the
    Pilot picked on replay — against a recorded `correct: [0]`, so the frame reads **AGREE**.
    Confusing the two inverts the consequence, and the spec for Issue #256 did exactly that.

    The baseline row is still keyed `THE_RECORD_WAS` (captured before the repair, byte-identical
    since — neither gate baseline is ever re-captured without a developer act) — this is the OTHER
    face of "corpus shape moved: +1/-1" both gates now report."""
    import json

    from train.decider_lab import gradeable_rows
    from train.gates import keyed_corrections, satisfies_human
    recs = keyed_corrections(REPO / "data" / "corrections")
    rec = next(c for k, c in recs if k == THE_RECORD)
    assert rec.scope == "decision" and rec.subject == 51 and rec.span is not None

    baseline = json.loads((REPO / "data" / "decider_lab" / "baseline.json")
                          .read_text(encoding="utf-8"))
    row = next(r for r in baseline["rows"] if r["key"] == THE_RECORD_WAS)
    assert rec.chosen == [2], "the record's historical pick, unchanged by the repair"
    assert row["chosen"] == [0] and row["correct"] == [0], "the gate's replay pick vs the ruling"
    assert satisfies_human(row["chosen"], row["correct"]) is True, "still grades as an AGREE"
    assert THE_RECORD_WAS in {r["key"] for r in gradeable_rows(baseline["rows"])}


@pytest.mark.req("REQ-GATE-0009")
def test_a_refused_shape_gets_no_excuse_from_either_gate():
    """**The report-only ruling, asserted behaviourally rather than by reading source.** The audit
    reaches no verdict, in either direction: a REGRESSION or an `OK -> MISS` on a record with a
    refused shape must fail exactly as any other unruled flip does. Wiring an exclusion is the change
    this test refuses — the same ruling Issue #251 made for the **Unstatable Decline**."""
    from train.gates import decision_gate_verdict, discrimination_gate_verdict
    assert decision_gate_verdict([{"key": THE_RECORD, "verdict": "REGRESSION"}],
                                 held_out={}) is False
    assert discrimination_gate_verdict({"ok_to_miss": [{"key": THE_RECORD}]}, held_out={}) is False
    # POSITIVE CONTROL: both CAN return True, so the Falses above are verdicts rather than functions
    # that only ever refuse.
    assert decision_gate_verdict([{"key": THE_RECORD, "verdict": "FIX"}], held_out={}) is True
    assert discrimination_gate_verdict({"ok_to_miss": []}, held_out={}) is True


@pytest.mark.req("REQ-GATE-0009")
def test_from_dict_still_loads_a_refused_shape_without_complaint():
    """**Decision D4, asserted directly.** The loader must NOT validate: it is what the Corpus Reader
    runs, so a validating `from_dict` would reject committed records at read time and take both gates
    down. The audit is the reporting half of that contract, and this is the half it must not become.

    Was asserted against the real corpus's one refused shape (`85709280|1|match|`); repaired since
    (ADR-0113 Amendment A). Reproduced here the way the real one actually got in: a record the
    constructor accepted, hand-edited past it afterwards — every OTHER field stays whatever the
    constructor produced, so only `scope`/`correct` are the corruption under test. Positive control
    that the two halves really disagree: the same payload through the *constructor* raises."""
    from train.blunder.correction import Correction
    valid = _build(correct=[2])
    tampered = {**valid.to_dict(), "scope": "match", "correct": [0]}
    loaded = Correction.from_dict(tampered)
    assert loaded.scope == "match" and loaded.correct == [0]   # loads, silently, as it must
    assert refuses(loaded) == ["unknown_scope"]                # and the audit says so out loud
    with pytest.raises(ValueError):
        _build(scope="match", correct=[0])


# ---------------------------------------------------------------------------
# The readout (acceptance criterion 5).
# ---------------------------------------------------------------------------

def _row(key, *, chosen=None, correct=None, **extra):
    return {"key": key, "chosen": chosen, "correct": correct, **extra}


def _rpt(rows):
    from train.decider_lab import gradeable_rows
    return {"rows": rows, "n": len(rows), "gradeable": len(gradeable_rows(rows))}


def _finding(key, *violations, scope="match", id="synthetic"):
    return {"key": key, "id": id, "scope": scope, "violations": list(violations)}


@pytest.mark.req("REQ-GATE-0009")
def test_the_readout_names_a_synthetic_refused_record_and_says_it_is_still_grading(capsys):
    """Driven by a SYNTHETIC finding, not the corpus: the live one has never moved, so a test that
    only read the corpus could not prove the section survives a second record appearing — which is
    the whole property this audit adds."""
    from train.decider_lab import print_refused_shape_readout
    key = "99999999|0|match|"
    rows = [_row(key, chosen=[0], correct=[0]), _row("other|0|decision|1", chosen=[1], correct=[1])]
    print_refused_shape_readout([_finding(key, "unknown_scope")], _rpt(rows))
    out = capsys.readouterr().out

    assert key in out, "the refused record must be NAMED"
    assert "refused shape (1)" in out
    assert "unknown_scope" in out and "decision / turn" in out, "name the SHAPE violated"
    assert "GRADING anyway" in out
    assert "re-rule the record" in out, "the line must say what to DO about it"


@pytest.mark.req("REQ-GATE-0009")
def test_the_readout_is_silent_when_the_corpus_is_clean(capsys):
    """A clean corpus prints a clean report — the shape `print_unstatable_readout` and
    `print_gate_report`'s HELD OUT / VOIDED sections already have."""
    from train.decider_lab import print_refused_shape_readout
    print_refused_shape_readout([], _rpt([_row("k", chosen=[0], correct=[0])]))
    assert capsys.readouterr().out == ""


@pytest.mark.req("REQ-GATE-0009")
def test_the_readout_says_so_when_a_refused_record_is_in_no_capture(capsys):
    """The claim is COMPUTED, never asserted. The audit is corpus-wide, so it legitimately names
    records no capture holds — unreplayable ones, or ones an `--agent` filter dropped — and a readout
    that printed "GRADING anyway" regardless would be decoration."""
    from train.decider_lab import print_refused_shape_readout
    key = "99999999|0|match|"
    print_refused_shape_readout([_finding(key, "unknown_scope")], _rpt([]))
    out = capsys.readouterr().out
    assert key in out and "GRADING anyway" not in out
    assert "not in this capture's gradeable population" in out
    # ... and the row line is WITHHELD rather than printed as `correct None; picks None`, which
    # reads as data — the record's ruling being null — when it means the capture has no such row.
    assert "recorded correct" not in out


@pytest.mark.req("REQ-GATE-0009")
def test_the_readout_prints_every_violation_a_record_carries(capsys):
    """The constructor stops at its first raise; the audit reports all applicable rules, so the
    readout must not print only the first."""
    from train.decider_lab import print_refused_shape_readout
    key = "99999999|0|turn|4"
    print_refused_shape_readout(
        [_finding(key, "correct_off_the_menu", "turn_correct_equals_chosen", scope="turn")],
        _rpt([_row(key, chosen=[1], correct=[1])]))
    out = capsys.readouterr().out
    assert "correct_off_the_menu" in out and "turn_correct_equals_chosen" in out
