"""`gates.records_a_decline_it_cannot_state` — the record-shape exclusion (Issue #197, the
2026-07-30 f3 sitting; lifted to `gates.py` by Issue #243 / ADR-0089 decision on Q1).

It guards a change to a gate's own INSTRUMENT, so it gets its own tests: a rule that quietly widened
would stop a gate failing on real regressions, which is the one failure mode a gate cannot have.

The gap it covers: at `decision` scope `build_correction` requires `correct` to be non-empty and to
index a legal option, so "take none" — the answer an OPTIONAL select exists to allow — has no
encoding. A record on such a select that reads `chosen == correct` has not stated that taking the
option was right; it has failed to state anything, and grading a decider against it turns a CORRECT
decline into a REGRESSION (ep83661652 f3, whose rationale says the opposite of its fields).

The scope guard is the half that only a SHARED predicate needs, and the corpus proves why: at
`turn` scope `correct: []` is encodable and is a real DECLINE, which `satisfies_human` grades
exactly. Unguarded, this predicate would swallow `86088989|0|turn|0`.

**Issue #251 ruled what the predicate is FOR: it REPORTS, it never excludes** (ADR-0112). The
second half of this module guards that ruling from both directions — the Decision Gate readout must
NAME an exposed frame and keep counting it, and the gate verdict must give it no excuse.
"""
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
    """The narrowness that makes this safe. On a select I MUST answer, `chosen == correct` is a real
    ruling — the pick was right — and a decider that flips away from it is a genuine regression the
    gate must still fail on. Ten of the thirteen `chosen == correct` records repo-wide are this
    shape; excluding them would blind the gate for the sake of the three it is aimed at."""
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
    """THE guard the lift added, and the corpus is the reason. `86088989|0|turn|0` records
    `correct: []` on a `minCount 0` select — at turn scope that is an ENCODABLE decline and a real
    ruling, which `satisfies_human` grades exactly. `[] == []` makes the bare comparison true, so
    without the scope test this predicate would drop a live ruling out of grading. A guard that
    blinds a ruling is worse than the false REGRESSION it was written to prevent."""
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
    """The measurement that produced the guard, asserted so it cannot rot silently. Three committed
    records sit on an optional select asserting only the agent's own pick; exactly one is scoped
    (a real decline) and must survive, and exactly two are `decision` scope and must be excluded."""
    from train.gates import keyed_corrections
    hits = [(k, c) for k, c in keyed_corrections()
            if c.obs and int(((c.obs.get("select") or {}).get("minCount") or 0)) == 0
            and sorted(c.chosen or []) == sorted(c.correct or [])]
    assert len(hits) == 3, [k for k, _c in hits]
    excluded = [k for k, c in hits if unstatable(c, c.obs)]
    assert sorted(excluded) == ["83661652|0|decision|3", "85785609|0|decision|4"]
    assert [k for k, _c in hits if k not in excluded] == ["86088989|0|turn|0"]


@pytest.mark.req("REQ-GATE-0009")
def test_the_decline_census_the_writer_relaxation_was_sized_against():
    """Issue #229's measurement, asserted so the NEXT drift is loud rather than inferred.

    Measured through the Corpus Reader (`keyed_corrections`), never by walking raw JSONL: 23 records
    carry no explicit `scope` key and only default to `decision` in `Correction.from_dict`, so a raw
    walk mis-scopes them and under-counts. The issue body's own table said *three* degenerate records
    and it is **two** — the third is `86088989|0|turn|0`, a turn-scope decline that was always legal.

    What each number is load-bearing for:

    * **10 declines, every one `turn` scope** — the writer's refusal is why, not the humans' rulings.
      When a `decision`-scope decline is first recorded this fails, and that is the shape working.
    * **28 decision-scope optional selects, 2 exposed** — the other 26 name a `correct` that differs
      from `chosen`, i.e. state a real preference. The gap was never "every optional select".
    """
    from train.gates import keyed_corrections
    recs = keyed_corrections()
    assert len(recs) == 372

    declines = [(k, c) for k, c in recs if c.correct == []]
    assert len(declines) == 10
    assert {c.scope for _k, c in declines} == {"turn"}

    optional = [(k, c) for k, c in recs if c.scope == "decision" and c.obs
                and int(((c.obs.get("select") or {}).get("minCount") or 0)) == 0]
    assert len(optional) == 28
    assert sorted(k for k, c in optional if unstatable(c, c.obs)) == [
        "83661652|0|decision|3", "85785609|0|decision|4"]

    # POSITIVE CONTROL. Every assertion above is a shape that must NOT be found; an empty corpus, a
    # broken reader or a mis-typed field would satisfy all of them at once. A reader that finds no
    # ruling at all is a broken instrument, not a clean corpus.
    assert sum(1 for _k, c in recs if c.correct) == 362


# ---------------------------------------------------------------------------
# Issue #251 — the predicate REPORTS. It must never come to excuse or exclude.
# ---------------------------------------------------------------------------

def _row(key, *, chosen=None, correct=None, **extra):
    return {"key": key, "chosen": chosen, "correct": correct, **extra}


def _rpt(rows):
    from train.decider_lab import gradeable_rows
    return {"rows": rows, "n": len(rows), "gradeable": len(gradeable_rows(rows))}


@pytest.mark.req("REQ-GATE-0009")
def test_the_readout_names_a_synthetic_exposed_frame_and_still_counts_it(capsys):
    """**THE test Issue #251 exists to leave behind.** Driven by a SYNTHETIC record, not the corpus:
    neither live exposed frame's pick has moved off the baseline, so a test that only read the corpus
    could not prove the section survives a flip — and the failure this guards against is a future
    session "helpfully" excluding the frame to quieten the gate.

    Two assertions, and the second is the load-bearing one: the frame is NAMED, and it is still
    counted in the gradeable population. An exclusion would satisfy the first alone."""
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
    """**Decision D1**, asserted behaviourally rather than by reading source. The predicate reports;
    it never excuses. A REGRESSION (Decision Gate) or an `OK -> MISS` (Discrimination Gate) on an
    exposed frame must FAIL exactly as any other unruled flip does — wiring the exclusion is
    precisely what would stop that. Both verdicts are asserted because the ruling covers both, and
    an untested one is where the exclusion would land unnoticed."""
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
    """The corpus half. Both exposed frames must still be IN the committed capture and labelled on
    both sides — i.e. still gradeable.

    The baseline is a never-auto-recaptured ruling record, so this does not go red the *instant*
    someone excludes a frame; it goes red at the next deliberate re-capture, which is the moment a
    human is looking. What it does catch immediately is the exposure moving — a record repaired,
    added or re-ruled — which is the change that should never pass unnoticed."""
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
    """**Decision D4's measurement**, asserted so the next reader does not re-derive it — or worse,
    apply symmetry by default.

    Stated precisely, because the issue's own version was wrong: `is_leaf_frame` is a DISJUNCTION.
    *"It requires `select.context == 0`"* describes only its second arm — a `turn_plan` record is a
    leaf frame at ANY context with an EMPTY `correct`, which is why the corollary *"a repaired
    decline is not a leaf frame either"* is false in general. What holds for these two frames is
    narrower and is what this asserts: neither carries a `turn_plan` and both are context 2, so both
    fail both arms — before a repair and after one, since re-ruling adds no `turn_plan`."""
    from train.gates import keyed_corrections
    from train.leaf_lab import is_leaf_frame
    recs = keyed_corrections()
    hits = [(k, c) for k, c in recs if unstatable(c, c.obs)]
    assert len(hits) == 2
    for k, c in hits:
        assert ((c.obs or {}).get("select") or {}).get("context") == 2, k
        assert not getattr(c, "turn_plan", None), k
        assert is_leaf_frame(c) is False, k

    # THE DISJUNCTION, asserted directly on the corpus so the false reading cannot come back:
    # `86088989|0|turn|0` is context 2 with `correct: []` and IS a leaf frame, purely on its
    # `turn_plan`. It is also the record the scope guard above exists to protect.
    turn_plan_decline = next(c for k, c in recs if k == "86088989|0|turn|0")
    assert turn_plan_decline.correct == [] and turn_plan_decline.turn_plan
    assert ((turn_plan_decline.obs or {}).get("select") or {}).get("context") == 2
    assert is_leaf_frame(turn_plan_decline) is True

    # POSITIVE CONTROL. `is_leaf_frame` returning False on everything would satisfy the loop above
    # while proving nothing; it must still recognise the frames it is for.
    assert sum(1 for _k, c in recs if is_leaf_frame(c)) == 278
