"""Guards on the POC-T4/5 flip table (`poc_t4_flips.py`) — so an xfail list cannot rot into cover.

`strict` only catches a frame that starts agreeing again. A renamed fixture, a drifted index or a
diagnosis that stopped being true would all leave the table looking like a considered ruling.
"""
import json
from pathlib import Path

import pytest

from poc_t4_flips import (CORPUS_RECORD_FLIPS, FLIPS, REFUSALS, RETIRED_BY_THE_TIE_DEFER,
                          VALUATIONS, marks, reason, record_reason)

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures" / "corrections"


@pytest.mark.req("REQ-CORPUS-0001")
def test_every_flip_names_a_fixture_that_exists():
    """A renamed or deleted fixture would leave a row asserting nothing about anything."""
    missing = [n for n in FLIPS if not (FIXTURES / f"{n}.json").exists()]
    assert missing == [], f"flip table names fixtures that do not exist: {missing}"


@pytest.mark.req("REQ-CORPUS-0001")
def test_every_flip_records_the_ruling_the_fixture_actually_carries():
    """If a frame is re-ruled upstream the row becomes a claim about a decision nobody made, and the
    xfail excuses the agent from a ruling that no longer exists."""
    wrong = []
    for name, (_kind, ruled, _got, _note) in FLIPS.items():
        fx = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
        if list(fx.get("correct") or []) != list(ruled):
            wrong.append((name, ruled, fx.get("correct")))
    assert wrong == [], f"flip rows disagree with the fixtures' own rulings: {wrong}"


@pytest.mark.req("REQ-CORPUS-0001")
def test_the_two_diagnoses_partition_the_table_and_both_are_populated():
    """A REFUSAL is seam coverage and a VALUATION is a human ruling, so collapsing to one bucket
    sends every frame to the wrong queue; all-of-one-kind means the diagnosis stopped being measured."""
    assert REFUSALS | VALUATIONS == set(FLIPS)
    assert not (REFUSALS & VALUATIONS)
    assert REFUSALS and VALUATIONS


@pytest.mark.req("REQ-CORPUS-0001")
def test_a_row_the_tie_defer_retired_never_quietly_returns():
    """Re-listing a retired frame in `FLIPS` would xfail one the agent now gets RIGHT, and `strict`
    cannot see it if the row lands at the same moment the behaviour regresses."""
    overlap = sorted(set(RETIRED_BY_THE_TIE_DEFER) & set(FLIPS))
    assert overlap == [], (
        f"{overlap} were retired from the flip table by the tie-defer and are listed again. If the "
        "behaviour genuinely regressed, say so in the row's note and delete it from "
        "`RETIRED_BY_THE_TIE_DEFER` — do not carry both claims at once")


@pytest.mark.req("REQ-CORPUS-0001")
def test_the_reason_string_leads_with_the_diagnosis():
    """`pytest -rx` prints reasons and nothing else. A reader skimming them has to be able to sort
    coverage ceilings from valuation calls without opening a file."""
    for name in FLIPS:
        r = reason(name)
        assert "Issue #386" in r
        assert ("REFUSAL" in r) or ("VALUATION" in r)


@pytest.mark.req("REQ-CORPUS-0001")
def test_marks_are_strict_and_only_apply_to_listed_frames():
    """The positive control. `marks()` returning nothing for everything would make the whole table
    inert while every guard above still passed — so assert it discriminates, in both directions."""
    assert marks(next(iter(FLIPS))), "a listed flip earned no mark"
    assert marks("no_such_fixture_at_all") == (), "an unlisted frame was marked xfail"
    assert marks(RETIRED_BY_THE_TIE_DEFER[0]) == (), (
        "a frame the tie-defer fixed is still being marked xfail — the table and the retirement "
        "list disagree, and the xfail would excuse the agent from a decision it now gets right")
    mark = marks(next(iter(FLIPS)))[0]
    assert mark.kwargs.get("strict") is True, "a non-strict xfail never reports a frame that recovered"


# ── the diagnosis itself, re-measured rather than trusted ────────────────────────────────────────
def _isolated_verdict(pilot, model, option):
    """REFUSED or PRICED for ONE option, composed ALONE: a refusal is a per-option property, so a
    one-option menu answers it with nothing to key and nothing to match."""
    from common import composer as cp
    res = cp.compose(model, [option], shed=pilot.cost_shed_indices)
    return "REFUSED" if list(res.gaps) else "PRICED"


@pytest.mark.req("REQ-CORPUS-0001")
@pytest.mark.parametrize("name", sorted(FLIPS))
def test_the_recorded_diagnosis_is_what_the_seam_still_says(name):
    """Each row's REFUSAL/VALUATION is a claim about the composer's seam, re-asked rather than
    trusted: a drifted row sends its frame to the wrong queue, silently."""
    import sys
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    from common import composer as cp                              # noqa: F401 (import check)

    agent = ("dragapult_ex" if name.startswith(("dragapult", "dp_", "pr_"))
             else "mega_lucario" if name.startswith("ml") else "mega_starmie")
    fx = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    obs, sel = fx["obs"], fx["obs"]["select"]
    ruled = fx["correct"][0]
    pilot = _build_pilot(agent)[0]
    pilot._board(obs, sel)
    model = pilot._leaf_state_model(obs, int((obs.get("current") or {}).get("yourIndex") or 0))
    verdict = _isolated_verdict(pilot, model, sel["option"][ruled])
    recorded = FLIPS[name][0]
    assert verdict == ("REFUSED" if recorded == "REFUSAL" else "PRICED"), (
        f"{name} is recorded as {recorded} but the seam now says {verdict} — re-diagnose the row "
        f"and move it to the other queue rather than editing this assertion")


# ── the CORPUS RECORD half of the table ──────────────────────────────────────────────────────────
@pytest.mark.req("REQ-CORPUS-0001")
def test_the_two_tables_do_not_overlap_and_the_record_one_is_populated():
    """`FLIPS` is keyed by fixture FILE, `CORPUS_RECORD_FLIPS` by (episode, frame) — two places one
    frame could be recorded. Compared by episode, the only thing the two spellings share."""
    assert CORPUS_RECORD_FLIPS, "the record table is empty — it is either unused or stopped loading"
    eps = {ep for ep, _fr in CORPUS_RECORD_FLIPS}
    clashes = sorted(n for n in FLIPS if any(ep in n for ep in eps))
    assert clashes == [], f"fixture rows whose name contains a record-flip episode: {clashes}"


@pytest.mark.req("REQ-CORPUS-0001")
@pytest.mark.parametrize("key", sorted(CORPUS_RECORD_FLIPS))
def test_the_record_flip_still_describes_a_real_frame_and_a_real_flip(key):
    """The record rows get the same treatment as the fixture ones: the frame must load, the ruling
    must be the corpus's own, and the recorded diagnosis must be what the seam still says."""
    import sys
    sys.path.insert(0, str(REPO / "tools"))
    from common import composer as cp
    from corpus_helpers import corpus_record
    from train.tune import _build_pilot

    ep, fr = key
    kind, ruled, _got, _note = CORPUS_RECORD_FLIPS[key]
    rec = corpus_record(ep, fr)
    obs = rec.obs
    sel = obs["select"]
    assert ruled in range(len(sel["option"])), (
        f"ep{ep} f{fr}: the recorded ruling {ruled} is not an index on this menu")
    pilot = _build_pilot("mega_starmie")[0]
    pilot._planning = False
    pilot._board(obs, sel)
    model = pilot._leaf_state_model(obs, int((obs.get("current") or {}).get("yourIndex") or 0))
    gaps = list(cp.compose(model, [sel["option"][ruled]], shed=pilot.cost_shed_indices).gaps)
    verdict = "REFUSED" if gaps else "PRICED"
    assert verdict == ("REFUSED" if kind == "REFUSAL" else "PRICED"), (
        f"ep{ep} f{fr} is recorded as {kind} but the seam now says {verdict}")


@pytest.mark.req("REQ-CORPUS-0001")
def test_the_record_reason_leads_with_the_diagnosis():
    for key in CORPUS_RECORD_FLIPS:
        r = record_reason(*key)
        assert "Issue #386" in r and (("REFUSAL" in r) or ("VALUATION" in r))
