"""`gates.shape_the_constructor_would_refuse` / `gates.refused_shapes` — the **Refused Shape** audit
(Issue #256, ADR-TEMP-256 decision 4).

`build_correction` validates at *write* time. `Correction.from_dict` — THE loader, and so what the
**Corpus Reader** inherits — validates nothing. That asymmetry is deliberate and stays: validating on
load would reject committed records at read time and take *both* gates down over a record that has
been sitting green for weeks. But unvalidated must not mean unobserved, and until this audit nothing
re-applied the writer's rules to what was already on disk — which is how `85709280|1|match|`
(`match` scope carrying `correct: [0]`, hand-edited past the constructor on 2026-07-29) got in, and
stayed, *grading in both gates*.

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

from train.gates import (REFUSED_SHAPES, refused_shapes,  # noqa: E402
                         shape_the_constructor_would_refuse as refuses)

#: The one committed record the audit exists for.
THE_RECORD = "85709280|1|match|"


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
def test_a_match_scope_correct_is_caught():
    """THE committed shape, as a synthetic record: `match` scope may name no `correct`, because no
    single select carries a whole-match verdict."""
    assert refuses(_Rec(scope="match", correct=[0], chosen=[2])) == ["match_names_a_correct"]


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
    """`REFUSED_SHAPES` is the one source both the predicate and the readout read, so a slug with no
    sentence would print as a bare identifier in an operator's report."""
    emitted = {"unknown_source", "unknown_scope", "match_names_a_correct", "correct_off_the_menu",
               "turn_correct_equals_chosen", "unprovable_decline"}
    assert emitted == set(REFUSED_SHAPES)
    assert all(REFUSED_SHAPES[s] and isinstance(REFUSED_SHAPES[s], str) for s in emitted)


# ---------------------------------------------------------------------------
# DIFFERENTIAL — the audit re-applies the REAL constructor's rules, not a paraphrase.
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-GATE-0009")
@pytest.mark.parametrize("kw,slug", [
    (dict(scope="match", correct=[0]), "match_names_a_correct"),
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
def test_the_committed_corpus_holds_exactly_one_refused_shape():
    """**The census.** Measured through the Corpus Reader, never raw JSONL: 23 records carry no
    explicit `scope` key and only default to `decision` inside `Correction.from_dict`, and every rule
    here dispatches on scope.

    It goes red when a SECOND bad shape lands — which is the property the store lacked entirely, and
    the whole deliverable of Issue #256. It also goes red when this one is repaired, which is the
    moment a human is looking (decision D3, packet).
    """
    found = refused_shapes(REPO / "data" / "corrections")
    assert [f["key"] for f in found] == [THE_RECORD]
    assert found[0]["id"] == "ee3191f7c3d6"
    assert found[0]["scope"] == "match"
    assert found[0]["violations"] == ["match_names_a_correct"]


@pytest.mark.req("REQ-GATE-0009")
def test_the_census_positive_control_the_reader_and_the_predicate_both_work():
    """**The control the census is worthless without.** An empty corpus, a broken reader or a
    mis-typed field would all satisfy the assertion above while proving nothing. So: the reader finds
    all 372 records, 371 of them are clean, and the audit's own rules DO fire when a bad record is
    put in front of them."""
    from train.gates import keyed_corrections
    recs = keyed_corrections(REPO / "data" / "corrections")
    assert len(recs) == 372
    assert sum(1 for _k, c in recs if not refuses(c)) == 371
    # The predicate is not a function that only ever returns [] — proved against a real committed
    # record, not only a synthetic one.
    the_record = next(c for k, c in recs if k == THE_RECORD)
    assert refuses(the_record) == ["match_names_a_correct"]
    assert the_record.scope == "match" and the_record.correct == [0]


@pytest.mark.req("REQ-GATE-0009")
def test_the_one_match_scope_record_is_the_only_one_and_is_still_grading():
    """Why the finding matters, stated as the two facts a reader needs.

    It is the ONLY `match`-scope record repo-wide (353 decision / 18 turn / 1 match), so **decision
    D1** — *a match-scope Correction should not grade at its Anchor* — is a ruling about exactly this
    record today. And it is not inert: it sits in the committed Decision Gate baseline, labelled on
    both sides, inside the gradeable denominator.

    ⚠️ **The gate grades the PILOT's fresh replay pick, not the record's own `chosen` field.** The
    record's historical `chosen` is `[2]`; the baseline row's `chosen` is `[0]` — what the Pilot
    picks on replay — against a recorded `correct: [0]`, so the frame reads **AGREE**. Confusing the
    two inverts D1's consequence, and the spec for this issue did exactly that."""
    import json
    from collections import Counter

    from train.decider_lab import gradeable_rows
    from train.gates import keyed_corrections, satisfies_human
    recs = keyed_corrections(REPO / "data" / "corrections")
    assert Counter(c.scope for _k, c in recs) == {"decision": 353, "turn": 18, "match": 1}

    rec = next(c for k, c in recs if k == THE_RECORD)
    baseline = json.loads((REPO / "data" / "decider_lab" / "baseline.json")
                          .read_text(encoding="utf-8"))
    row = next(r for r in baseline["rows"] if r["key"] == THE_RECORD)
    assert rec.chosen == [2], "the record's historical pick"
    assert row["chosen"] == [0] and row["correct"] == [0], "the gate's replay pick vs the ruling"
    assert satisfies_human(row["chosen"], row["correct"]) is True, "it grades as an AGREE"
    assert THE_RECORD in {r["key"] for r in gradeable_rows(baseline["rows"])}


@pytest.mark.req("REQ-GATE-0009")
def test_a_refused_shape_gets_no_excuse_from_either_gate():
    """**The report-only ruling, asserted behaviourally rather than by reading source.** The audit
    reaches no verdict, in either direction: a REGRESSION or an `OK -> MISS` on a record with a
    refused shape must fail exactly as any other unruled flip does. Wiring an exclusion is the change
    this pins against — the same ruling Issue #251 made for the **Unstatable Decline**."""
    from train.gates import decision_gate_verdict, discrimination_gate_verdict
    assert decision_gate_verdict([{"key": THE_RECORD, "verdict": "REGRESSION"}],
                                 held_out={}) is False
    assert discrimination_gate_verdict({"ok_to_miss": [{"key": THE_RECORD}]}, held_out={}) is False
    # POSITIVE CONTROL: both CAN return True, so the Falses above are verdicts rather than functions
    # that only ever refuse.
    assert decision_gate_verdict([{"key": THE_RECORD, "verdict": "FIX"}], held_out={}) is True
    assert discrimination_gate_verdict({"ok_to_miss": []}, held_out={}) is True


@pytest.mark.req("REQ-GATE-0009")
def test_from_dict_still_loads_the_refused_record_without_complaint():
    """**Decision D4, asserted directly.** The loader must NOT validate: it is what the Corpus Reader
    runs, so a validating `from_dict` would reject committed records at read time and take both gates
    down. The audit is the reporting half of that contract, and this is the half it must not become.

    Positive control that the two halves really disagree: the same payload through the *constructor*
    raises."""
    from train.blunder.correction import Correction
    from train.gates import keyed_corrections
    rec = next(c for k, c in keyed_corrections(REPO / "data" / "corrections") if k == THE_RECORD)
    assert Correction.from_dict(rec.to_dict()) == rec         # loads, silently, as it must
    assert refuses(rec) == ["match_names_a_correct"]          # and the audit says so out loud
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
    print_refused_shape_readout([_finding(key, "match_names_a_correct")], _rpt(rows))
    out = capsys.readouterr().out

    assert key in out, "the refused record must be NAMED"
    assert "refused shape (1)" in out
    assert "match_names_a_correct" in out and "whole-match verdict" in out, "name the SHAPE violated"
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
    print_refused_shape_readout([_finding(key, "match_names_a_correct")], _rpt([]))
    out = capsys.readouterr().out
    assert key in out and "GRADING anyway" not in out
    assert "not in this capture's gradeable population" in out


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
