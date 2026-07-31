"""The deploy sweep's record-shape exclusion (Issue #197, the 2026-07-30 f3 sitting).

`_records_a_decline_it_cannot_state` is a change to the Decision Gate's own INSTRUMENT, so it gets
its own guard: a rule that quietly widened would stop the gate failing on real regressions, which is
the one failure mode a gate cannot have.

The gap it covers: at `decision` scope `build_correction` requires `correct` to be non-empty and to
index a legal option, so "take none" — the answer an OPTIONAL select exists to allow — has no
encoding. A record on such a select that reads `chosen == correct` has not stated that taking the
option was right; it has failed to state anything, and grading a decider against it turns a CORRECT
decline into a REGRESSION (ep83661652 f3, whose rationale says the opposite of its fields).
"""
import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

_SWEEP = REPO / "tools" / "train" / "probes" / "deploy_decider_sweep.py"


@pytest.fixture(scope="module")
def unstatable():
    spec = importlib.util.spec_from_file_location("deploy_decider_sweep", _SWEEP)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._records_a_decline_it_cannot_state


def _obs(min_count):
    return {"select": {"minCount": min_count, "maxCount": 1, "option": [{"type": 3}]}}


def test_an_optional_select_asserting_the_agents_own_pick_is_excluded(unstatable):
    """The f3 shape: `minCount 0`, and the record names exactly what the agent already did."""
    assert unstatable({"chosen": [0], "correct": [0]}, _obs(0)) is True


def test_a_mandatory_select_is_never_excluded_even_when_chosen_equals_correct(unstatable):
    """The narrowness that makes this safe. On a select I MUST answer, `chosen == correct` is a real
    ruling — the pick was right — and a decider that flips away from it is a genuine regression the
    gate must still fail on. Ten of the thirteen `chosen == correct` records repo-wide are this
    shape; excluding them would blind the gate for the sake of the three it is aimed at."""
    assert unstatable({"chosen": [0], "correct": [0]}, _obs(1)) is False


def test_an_optional_select_that_DOES_state_a_preference_still_gates(unstatable):
    """`minCount 0` alone is not the trigger. Where the human named a DIFFERENT option, the record
    states a real preference despite the optional select, and the frame keeps gating."""
    assert unstatable({"chosen": [0], "correct": [1]}, _obs(0)) is False


def test_ordering_does_not_defeat_the_comparison(unstatable):
    """A multi-pick record is compared as a SET — `[1, 0]` and `[0, 1]` are the same answer, and an
    exclusion rule that missed that would leak an unstatable frame back into the gate."""
    assert unstatable({"chosen": [1, 0], "correct": [0, 1]}, _obs(0)) is True


@pytest.mark.parametrize("rec", [
    {"chosen": [], "correct": []},          # both absent
    {"chosen": None, "correct": None},      # both null
    {},                                     # neither key
])
def test_missing_fields_do_not_crash_the_gate(unstatable, rec):
    """Fail direction: a malformed record must not take the sweep down mid-run. It reads as
    unstatable, which only ever REMOVES a frame from grading — it can never fabricate a FIX."""
    assert unstatable(rec, _obs(0)) is True


def test_the_real_f3_record_is_the_case_this_exists_for():
    """Anchored on the committed corpus, not a hand-built shape: if the record is ever repaired so a
    decline becomes statable, this fails and the exclusion should be reconsidered."""
    import json
    fx = json.loads((REPO / "tests" / "fixtures" / "corrections"
                     / "setup_bench_decline_f3.json").read_text(encoding="utf-8"))
    select = fx["obs"]["select"]
    assert select["minCount"] == 0 and len(select["option"]) == 1
