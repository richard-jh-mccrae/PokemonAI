"""A Correction whose ``rationale`` CONTRADICTS its own ``correct`` field (Issue #417).

A different failure from `test_unstatable_decline_records.py`'s, and the difference is the whole
reason this module exists rather than an assertion bolted onto that one. That module guards a record
that has **failed to state anything** — an OPTIONAL select where "take none" has no encoding, so
`chosen == correct` is a writer limitation. This one guards a record that states **two incompatible
things**: machine-readable fields naming one option, and a human sentence naming another.

**`chosen == correct` is NOT the defect, and asserting that it were would break a shipped ruling.**
On a MANDATORY select this repo deliberately reads that shape as *the pick was right* — see
`test_unstatable_decline_records.py::test_a_mandatory_select_is_never_excluded_even_when_chosen_
equals_correct`, whose own docstring says excluding those records "would blind the gate", and 14 of
them are committed today. So ADR-0015's *"`correct` must … differ from `chosen`"* is a writer-side
validation that the corpus knowingly does not enforce on mandatory selects, and it cannot be cited to
invalidate a record on its own. What it does is make a conflicting rationale SHARPER: the fields
endorse what the agent did, and the prose condemns it.

There is exactly one such record, found while building Issue #417's ctx-21 regression coverage. It is
NOT auto-detectable in general — reading a free-text rationale against an option index is a human
judgement — so this module does not claim a corpus-wide sweep. It asserts the one frame, with the
three independent facts that identify which field is stale, so the finding survives in the suite
rather than in an issue comment nobody re-reads.

The assertion is written to FAIL when the record is re-ruled. That is the point: the moment a human
fixes it, `tests/strategy/test_attach_decider.py`'s `_CORPUS` is owed the frame as a real ranking
test, and a green suite would let it be forgotten instead.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src"), str(REPO / "tests")]

CONFLICTED = ("82224509", 31)


def _record(episode, frame):
    """THE Corpus Reader, via the shared test helper (ADR-0087 / ADR-0089). Never a raw JSONL walk:
    23 records carry no explicit `scope` and only default to `decision` in `Correction.from_dict`,
    so a raw walk mis-scopes them and a duplicate double-counts."""
    from corpus_helpers import corpus_record
    return corpus_record(episode, frame)


@pytest.mark.req("REQ-GATE-0009")
def test_the_one_record_whose_rationale_names_the_other_option():
    """`82224509-31`. Its rationale argues for the bench body carrying NO Energy; its `correct`
    names the one already carrying three.

    Three independent facts say `correct` is the stale field and `chosen` is real — asserted rather
    than argued, because the re-ruling turns on which one to trust:

    1. the embedded ``live_trace`` — the shipped agent's own telemetry at this exact decision, a
       different artefact from either field — records ``chosen: [0]``;
    2. the rationale's *"the other benched mon without any energy"* resolves unambiguously to bench
       index 1, the only body with an empty ``energies`` list;
    3. `correct == chosen`, so `correct` carries no information the agent's own pick did not.

    Fact 3 is corroboration, NOT the finding (see the module docstring): the same shape is a valid
    endorsement on 13 other mandatory-select records, and only the rationale conflict makes it
    evidence here."""
    rec = _record(*CONFLICTED)
    assert rec.decision["select_context"] == "AttachFrom"
    assert rec.correct == rec.chosen == [0], (
        "82224509-31 has been re-ruled — move it into test_attach_decider.py's _CORPUS as a real "
        "ranking test and delete this module's assertion")
    assert "without any energy" in (rec.rationale or "")

    current = rec.decision["current"]
    bench = current["players"][current["yourIndex"]]["bench"]
    assert [len(b["energies"]) for b in bench] == [3, 0]        # the rationale names index 1
    assert (rec.live_trace or {}).get("chosen") == [0]          # ... and `chosen` is the real pick


@pytest.mark.req("REQ-GATE-0009")
def test_the_mandatory_chosen_equals_correct_population_is_measured_not_assumed():
    """The census that stops this module's framing drifting into "every `chosen == correct` record
    is broken", which is the reading the shipped mandatory-select ruling forbids.

    Measured 2026-08-06 through `keyed_corrections` over 375 records: **17** carry
    `chosen == correct`, **14** of them on a MANDATORY select (`minCount >= 1`) where the shape is a
    legitimate endorsement, and 3 on an optional one — the population
    `test_unstatable_decline_records.py` already owns. Only ONE of the 14 has a rationale that
    contradicts it. `test_unstatable_decline_records.py`'s own docstring still says "ten of the
    thirteen"; that count predates Issue #409's three ctx-17 rulings and one later record, and is
    prose there rather than an assertion — re-measured here so the two do not silently disagree."""
    from train.gates import keyed_corrections
    recs = keyed_corrections()
    same = [(k, c) for k, c in recs
            if c.chosen is not None and c.correct is not None
            and sorted(c.chosen) == sorted(c.correct)]
    mandatory = [(k, c) for k, c in same if c.obs
                 and int(((c.obs.get("select") or {}).get("minCount") or 0)) >= 1]
    assert len(same) == 17
    assert len(mandatory) == 14
    # POSITIVE CONTROL. Every count above is of a shape that must be FOUND; a broken reader, a
    # renamed field or an empty corpus would read 0 for all of them and look like a clean corpus.
    assert len(recs) == 375
    assert sum(1 for _k, c in recs if c.correct) == 365
