"""A Correction whose ``rationale`` CONTRADICTS its own ``correct`` field (Issue #417).

Distinct from `test_unstatable_decline_records.py`'s failure: that guards a record that failed to
STATE anything (an OPTIONAL select where "take none" has no encoding); this guards a record that
stated TWO incompatible things — machine-readable fields naming one option, prose naming another.

**`chosen == correct` was NOT the defect.** On a MANDATORY select this repo deliberately reads that
shape as *the pick was right*, so ADR-0015's *"`correct` must differ from `chosen`"* cannot be cited
to invalidate a record on its own. What it did was make a conflicting rationale SHARPER.

One record carried the conflict and it is now RESOLVED; this module keeps the guard the other way
round — that the record STAYS coherent — because a gate grades fields against fields and never reads
the prose. Detecting the general case is a human judgement, so no corpus-wide sweep is claimed.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src"), str(REPO / "tests")]

RESOLVED = ("82224509", 31)


def _record(episode, frame):
    """THE Corpus Reader, via the shared test helper (ADR-0087 / ADR-0089). Never a raw JSONL walk: 23
    records default their `scope` only inside `Correction.from_dict`, so a raw walk mis-scopes them."""
    from corpus_helpers import corpus_record
    return corpus_record(episode, frame)


@pytest.mark.req("REQ-GATE-0009")
def test_the_re_ruled_record_agrees_with_its_own_rationale():
    """`82224509-31`, re-ruled 2026-08-06. The three facts that identified `correct` (not `chosen`) as
    the stale field are asserted too, because a later edit "tidying" `chosen` would invert the record."""
    rec = _record(*RESOLVED)
    assert rec.decision["select_context"] == "AttachFrom"
    assert rec.chosen == [0]
    assert rec.correct == [1], "82224509-31 was re-ruled to [1]; a revert re-opens the conflict"
    assert "without any energy" in (rec.rationale or "")
    assert (rec.live_trace or {}).get("chosen") == [0]

    current = rec.decision["current"]
    bench = current["players"][current["yourIndex"]]["bench"]
    assert [len(b["energies"]) for b in bench] == [3, 0]   # index 1 is the body with no Energy


@pytest.mark.req("REQ-GATE-0009")
def test_the_mandatory_chosen_equals_correct_population_is_measured_not_assumed():
    """The census that stops this framing drifting into "every `chosen == correct` record is broken",
    which the shipped mandatory-select ruling forbids. The SPLIT is asserted rather than the total."""
    from corpus_helpers import committed_keyed_corrections
    recs = committed_keyed_corrections()
    same = [(k, c) for k, c in recs
            if c.chosen is not None and c.correct is not None
            and sorted(c.chosen) == sorted(c.correct)]
    mandatory = [(k, c) for k, c in same if c.obs
                 and int(((c.obs.get("select") or {}).get("minCount") or 0)) >= 1]
    assert len(same) == 16
    assert len(mandatory) == 13
    assert RESOLVED[0] not in {k.split("|")[0] for k, _c in same}
    # POSITIVE CONTROL. Every count above is of a shape that must be FOUND; a broken reader, a
    # renamed field or an empty corpus would read 0 for all of them and look like a clean corpus.
    assert len(recs) == 384
    assert sum(1 for _k, c in recs if c.correct) == 373
