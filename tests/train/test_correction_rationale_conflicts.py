"""A Correction whose ``rationale`` CONTRADICTS its own ``correct`` field (Issue #417).

A different failure from `test_unstatable_decline_records.py`'s, and the difference is the whole
reason this module exists rather than an assertion bolted onto that one. That module guards a record
that has **failed to state anything** — an OPTIONAL select where "take none" has no encoding, so
`chosen == correct` is a writer limitation. This one guards a record that stated **two incompatible
things**: machine-readable fields naming one option, and a human sentence naming another.

**`chosen == correct` was NOT the defect, and asserting that it were would break a shipped ruling.**
On a MANDATORY select this repo deliberately reads that shape as *the pick was right* — see
`test_unstatable_decline_records.py::test_a_mandatory_select_is_never_excluded_even_when_chosen_
equals_correct`, whose own docstring says excluding those records "would blind the gate", and 13 of
them are committed today. So ADR-0015's *"`correct` must … differ from `chosen`"* is a writer-side
validation the corpus knowingly does not enforce on mandatory selects, and it cannot be cited to
invalidate a record on its own. What it did was make a conflicting rationale SHARPER: the fields
endorsed what the agent did, and the prose condemned it.

**One record carried that conflict and it is now RESOLVED.** `82224509-31` was found while building
Issue #417's ctx-21 regression coverage and re-ruled by the developer on 2026-08-06: `correct` moved
`[0] -> [1]`, the body its own rationale names. This module keeps the guard the other way round —
that the record STAYS coherent — because the conflict was invisible to every instrument the repo has
(both ADR-0072 gates passed over it for six weeks, since a gate grades fields against fields and
never reads the prose).

Detecting the general case is not possible here: reading a free-text rationale against an option
index is a human judgement, so this module claims no corpus-wide sweep. It asserts the one known
frame plus the census the framing depends on.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src"), str(REPO / "tests")]

RESOLVED = ("82224509", 31)


def _record(episode, frame):
    """THE Corpus Reader, via the shared test helper (ADR-0087 / ADR-0089). Never a raw JSONL walk:
    23 records carry no explicit `scope` and only default to `decision` in `Correction.from_dict`,
    so a raw walk mis-scopes them and a duplicate double-counts. The first measurement behind this
    module used a raw walk and read 17 where the Reader reads 16."""
    from corpus_helpers import corpus_record
    return corpus_record(episode, frame)


@pytest.mark.req("REQ-GATE-0009")
def test_the_re_ruled_record_agrees_with_its_own_rationale():
    """`82224509-31`, re-ruled 2026-08-06 (Issue #417 B1).

    Its rationale — *"dont attach more energy on a pokemon than it needs. Mega Starmie already had 3
    basic energy, therefor should have attached on the other benched mon without any energy"* —
    resolves unambiguously to bench index 1: the only body on that bench with an empty ``energies``
    list. `correct` now names it.

    The three facts that identified `correct` (not `chosen`) as the stale field are asserted too,
    because they are what the ruling turned on and a later edit that "tidied" `chosen` instead would
    silently invert the record:

    1. the embedded ``live_trace`` — the shipped agent's own telemetry at this exact decision, a
       different artefact from either field — records ``chosen: [0]``, so `chosen` is real;
    2. the rationale's *"without any energy"* names the body at index 1;
    3. `correct != chosen`, so the record now states a real preference rather than an endorsement.

    The ranking itself is asserted where ranking assertions live —
    `tests/strategy/test_attach_decider.py`'s `_CORPUS`."""
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
    """The census that stops this module's framing drifting into "every `chosen == correct` record
    is broken", which is the reading the shipped mandatory-select ruling forbids.

    Measured 2026-08-06 through `keyed_corrections` over 375 records, AFTER the re-ruling above:
    **16** carry `chosen == correct`, **13** of them on a MANDATORY select (`minCount >= 1`) where
    the shape is a legitimate endorsement, and 3 on an optional one — the population
    `test_unstatable_decline_records.py` already owns. Every one of the 13 is untouched by Issue
    #417; only the one with a conflicting rationale moved.

    `test_unstatable_decline_records.py`'s own docstring says "ten of the thirteen". That count
    predates Issue #409's three ctx-17 rulings and is prose there rather than an assertion — it
    happens to coincide with the post-re-ruling total again, which is why the split (13 mandatory +
    3 optional = 16) is asserted here rather than the bare total."""
    from train.gates import keyed_corrections
    recs = keyed_corrections()
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
    assert len(recs) == 375
    assert sum(1 for _k, c in recs if c.correct) == 365
