"""`gates.records_a_decline_it_cannot_state` — the record-shape exclusion (Issue #197, ADR-0089).

At `decision` scope `build_correction` requires a non-empty `correct`, so "take none" — the
answer an OPTIONAL select exists to allow — has no encoding, and grading against such a record
turns a CORRECT decline into a REGRESSION. At `turn` scope `correct: []` IS encodable, which is
why the scope guard exists. Issue #251 ruled the predicate REPORTS and never excludes
(ADR-0112); the second half of this module guards that from both directions."""
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from train.gates import records_a_decline_it_cannot_state as unstatable  # noqa: E402


@dataclass
class _Rec:
    """The duck type the predicate reads — a `Correction` in production."""
    chosen: list | None = None
    correct: list | None = None
    scope: str = "decision"


def _obs(min_count):
    return {"select": {"minCount": min_count, "maxCount": 1, "option": [{"type": 3}]}}


@pytest.mark.req("REQ-GATE-0009")
def test_an_optional_select_asserting_the_agents_own_pick_is_excluded():
    """The f3 shape: `minCount 0`, and the record names exactly what the agent already did."""
    assert unstatable(_Rec(chosen=[0], correct=[0]), _obs(0)) is True


@pytest.mark.req("REQ-GATE-0009")
def test_a_mandatory_select_is_never_excluded_even_when_chosen_equals_correct():
    """The narrowness that makes this safe: on a select I MUST answer, `chosen == correct` is a ruling."""
    assert unstatable(_Rec(chosen=[0], correct=[0]), _obs(1)) is False


@pytest.mark.req("REQ-GATE-0009")
def test_an_optional_select_that_DOES_state_a_preference_still_gates():
    """`minCount 0` alone is not the trigger. Where the human named a DIFFERENT option, the record
    states a real preference despite the optional select, and the frame keeps gating."""
    assert unstatable(_Rec(chosen=[0], correct=[1]), _obs(0)) is False


@pytest.mark.req("REQ-GATE-0009")
def test_ordering_does_not_defeat_the_comparison():
    """A multi-pick record is compared as a SET — `[1, 0]` and `[0, 1]` are the same answer, and an
    exclusion rule that missed that would leak an unstatable frame back into the gate."""
    assert unstatable(_Rec(chosen=[1, 0], correct=[0, 1]), _obs(0)) is True


@pytest.mark.req("REQ-GATE-0009")
def test_a_turn_scope_decline_is_statable_and_must_not_be_swallowed():
    """THE guard the lift added: at `turn` scope `correct: []` is an ENCODABLE decline and a real
    ruling. `[] == []` makes the bare comparison true, so without the scope test it is dropped."""
    assert unstatable(_Rec(chosen=[], correct=[], scope="turn"), _obs(0)) is False


@pytest.mark.req("REQ-GATE-0009")
@pytest.mark.parametrize("rec", [
    _Rec(chosen=[], correct=[]),            # both absent
    _Rec(chosen=None, correct=None),        # both null
    _Rec(),                                 # neither set
])
def test_missing_fields_do_not_crash_the_gate(rec):
    """Fail direction: a malformed record must not take a gate down mid-run. It reads as
    unstatable, which only ever REMOVES a frame from grading — it can never fabricate a FIX."""
    assert unstatable(rec, _obs(0)) is True


@pytest.mark.req("REQ-GATE-0009")
def test_a_missing_obs_does_not_crash_the_gate():
    """Same fail direction on the other argument — an unreplayable record carries no `obs`."""
    assert unstatable(_Rec(chosen=[0], correct=[0]), None) is True


@pytest.mark.req("REQ-GATE-0009")
def test_the_real_f3_record_is_the_case_this_exists_for():
    """Anchored on the committed corpus, not a hand-built shape: if the record is ever repaired so a
    decline becomes statable, this fails and the exclusion should be reconsidered."""
    import json
    fx = json.loads((REPO / "tests" / "fixtures" / "corrections"
                     / "setup_bench_decline_f3.json").read_text(encoding="utf-8"))
    select = fx["obs"]["select"]
    assert select["minCount"] == 0 and len(select["option"]) == 1


@pytest.mark.req("REQ-GATE-0009")
def test_the_corpus_shape_census_is_what_the_scope_guard_was_sized_against():
    """The measurement that produced the guard, asserted so it cannot rot silently."""
    from corpus_helpers import committed_keyed_corrections
    hits = [(k, c) for k, c in committed_keyed_corrections()
            if c.obs and int(((c.obs.get("select") or {}).get("minCount") or 0)) == 0
            and sorted(c.chosen or []) == sorted(c.correct or [])]
    assert len(hits) == 3, [k for k, _c in hits]
    excluded = [k for k, c in hits if unstatable(c, c.obs)]
    assert sorted(excluded) == ["83661652|0|decision|3", "85785609|0|decision|4"]
    assert [k for k, _c in hits if k not in excluded] == ["86088989|0|turn|0"]


@pytest.mark.req("REQ-GATE-0009")
def test_the_decline_census_the_writer_relaxation_was_sized_against():
    """Issue #229's measurement. Read through the Corpus Reader, never raw JSONL: a record with no
    explicit `scope` key only defaults to `decision` inside `Correction.from_dict`."""
    from corpus_helpers import committed_keyed_corrections
    recs = committed_keyed_corrections()
    assert len(recs) == 384

    declines = [(k, c) for k, c in recs if c.correct == []]
    assert len(declines) == 11
    assert {c.scope for _k, c in declines} == {"turn"}

    optional = [(k, c) for k, c in recs if c.scope == "decision" and c.obs
                and int(((c.obs.get("select") or {}).get("minCount") or 0)) == 0]
    assert len(optional) == 28
    assert sorted(k for k, c in optional if unstatable(c, c.obs)) == [
        "83661652|0|decision|3", "85785609|0|decision|4"]

    # POSITIVE CONTROL. Every assertion above is a shape that must NOT be found; an empty corpus, a
    # broken reader or a mis-typed field would satisfy all of them at once.
    assert sum(1 for _k, c in recs if c.correct) == 373


# Issue #251 — the predicate REPORTS. It must never come to excuse or exclude.

def _row(key, *, chosen=None, correct=None, **extra):
    return {"key": key, "chosen": chosen, "correct": correct, **extra}


def _rpt(rows):
    from train.decider_lab import gradeable_rows
    return {"rows": rows, "n": len(rows), "gradeable": len(gradeable_rows(rows))}


@pytest.mark.req("REQ-GATE-0009")
def test_the_readout_names_a_synthetic_exposed_frame_and_still_counts_it(capsys):
    """Driven by a SYNTHETIC record: neither live exposed frame's pick has moved off the baseline. The
    load-bearing assertion is the second — the frame is still counted in the gradeable population."""
    from train.decider_lab import gradeable_rows, print_unstatable_readout
    key = "99999999|0|decision|7"
    rows = [_row(key, chosen=[], correct=[0]), _row("other|0|decision|1", chosen=[1], correct=[1])]
    print_unstatable_readout([key], _rpt(rows))
    out = capsys.readouterr().out

    assert key in out, "the exposed frame must be NAMED, not silently handled"
    assert "unstatable (1)" in out
    assert "still GRADEABLE" in out
    assert "correct: []" in out and "Issue #229" in out, "the line must say what to DO about it"
    # Still in the gradeable population — the exclusion this issue ruled against would drop it.
    assert key in {r["key"] for r in gradeable_rows(rows)}
    assert _rpt(rows)["gradeable"] == 2


@pytest.mark.req("REQ-GATE-0009")
def test_the_readout_is_silent_when_nothing_is_exposed(capsys):
    """A clean corpus prints a clean report. The section is always visible when it fires and absent
    when it does not — the shape `print_gate_report`'s HELD OUT / VOIDED sections already have."""
    from train.decider_lab import print_unstatable_readout
    print_unstatable_readout([], _rpt([_row("k", chosen=[0], correct=[0])]))
    assert capsys.readouterr().out == ""


@pytest.mark.req("REQ-GATE-0009")
def test_the_readout_says_so_when_an_exposed_frame_is_NOT_gradeable(capsys):
    """The claim is computed, never asserted. A voided or unreplayable exposed frame is out of the
    denominator, and a readout that printed "still GRADEABLE" regardless would be decoration."""
    from train.decider_lab import print_unstatable_readout
    key = "99999999|0|decision|7"
    print_unstatable_readout([key], _rpt([_row(key, chosen=[], correct=[0], voided=True)]))
    out = capsys.readouterr().out
    assert key in out and "still GRADEABLE" not in out
    assert "not in this capture's gradeable population" in out


@pytest.mark.req("REQ-GATE-0009")
def test_an_exposed_frame_gets_no_excuse_from_either_gate():
    """Decision D1: the predicate reports, it never excuses. Asserted behaviourally, not from source."""
    from train.gates import decision_gate_verdict, discrimination_gate_verdict
    exposed = "85785609|0|decision|4"
    assert decision_gate_verdict([{"key": exposed, "verdict": "REGRESSION"}], held_out={}) is False
    assert discrimination_gate_verdict({"ok_to_miss": [{"key": exposed}]}, held_out={}) is False
    # POSITIVE CONTROL: both calls CAN return True, so the Falses above are verdicts rather than
    # functions that only ever refuse.
    assert decision_gate_verdict([{"key": exposed, "verdict": "FIX"}], held_out={}) is True
    assert discrimination_gate_verdict({"ok_to_miss": []}, held_out={}) is True


@pytest.mark.req("REQ-GATE-0009")
def test_the_live_exposure_is_named_and_still_carried_by_the_committed_baseline():
    """The baseline is never auto-recaptured, so this reds at the next deliberate re-capture rather
    than the instant someone excludes a frame. What it catches immediately is the exposure MOVING."""
    import json
    from train.decider_lab import gradeable_rows, unstatable_frames
    exposed = unstatable_frames(REPO / "data" / "corrections")
    assert sorted(exposed) == ["83661652|0|decision|3", "85785609|0|decision|4"]

    baseline = json.loads((REPO / "data" / "decider_lab" / "baseline.json")
                          .read_text(encoding="utf-8"))
    gradeable = {r["key"] for r in gradeable_rows(baseline["rows"])}
    assert set(exposed) <= gradeable, "an exposed frame must never leave the gradeable set"
    # POSITIVE CONTROL: `gradeable` is a real population, not an accidentally-everything set.
    assert 0 < len(gradeable) < len(baseline["rows"])


@pytest.mark.req("REQ-GATE-0009")
def test_neither_exposed_frame_is_a_leaf_frame_so_no_symmetric_fix_is_owed():
    """`is_leaf_frame` is a DISJUNCTION — a `turn_plan` record is a leaf frame at ANY context with an
    EMPTY `correct`, so "a repaired decline is not a leaf frame either" is false in general."""
    from corpus_helpers import committed_keyed_corrections
    from train.leaf_lab import is_leaf_frame
    recs = committed_keyed_corrections()
    hits = [(k, c) for k, c in recs if unstatable(c, c.obs)]
    assert len(hits) == 2
    for k, c in hits:
        assert ((c.obs or {}).get("select") or {}).get("context") == 2, k
        assert not getattr(c, "turn_plan", None), k
        assert is_leaf_frame(c) is False, k

    # THE DISJUNCTION: `86088989|0|turn|0` is context 2 with `correct: []` and IS a leaf frame,
    # purely on its `turn_plan`.
    turn_plan_decline = next(c for k, c in recs if k == "86088989|0|turn|0")
    assert turn_plan_decline.correct == [] and turn_plan_decline.turn_plan
    assert ((turn_plan_decline.obs or {}).get("select") or {}).get("context") == 2
    assert is_leaf_frame(turn_plan_decline) is True

    # POSITIVE CONTROL. `is_leaf_frame` returning False on everything would satisfy the loop above
    # while proving nothing; it must still recognise the frames it is for.
    assert sum(1 for _k, c in recs if is_leaf_frame(c)) == 286
