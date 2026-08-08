"""THE apply-seam parity gate: the closed-form transition must agree with the RECORDED NATIVE ENGINE
(ADR-0098 decision 4). `tools/train/apply_parity.py` replays the committed native traces one step at
a time and diffs the resulting `StateModel` against the next recorded frame, over
`snapshot_coverage`'s HOMED zones. DLL-free — the trace IS the native side.

**Budget-tagged.** A session replays the FIRST N traces in sorted order (not a sample, so a failure
names a reproducible set); ``APPLY_PARITY_FULL=1`` runs the full sweep.

**A divergence is a ruled seam bug, never an accepted approximation.** The remedy is
`apply_option.QUARANTINED_KINDS`, and the planner then degrades to always-expand VISIBLY.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from common import apply_option as ao                     # noqa: E402
from common import board_delta as bd                      # noqa: E402
from train import apply_parity as lane                    # noqa: E402

#: Traces replayed in an ordinary session: 40 covers all four modelled kinds in a few seconds,
#: where the full sweep is minutes.
CI_TRACES = 40

FULL = os.environ.get("APPLY_PARITY_FULL") == "1"


@pytest.fixture(scope="module")
def report():
    return lane.sweep(limit=None if FULL else CI_TRACES)


@pytest.mark.req("REQ-APPLY-0004")
def test_the_seam_agrees_with_the_recorded_engine_on_every_modelled_step(report):
    """The seam may differ from the observation on anything no equation reads, and on nothing that
    one does."""
    assert report.clean, f"\n{report}"


@pytest.mark.req("REQ-APPLY-0004")
def test_the_lane_actually_replays_all_four_modelled_kinds(report):
    """Each declared kind must have VERIFIED steps, not only refused ones: a lane that refused
    everything would be green and vacuous."""
    assert set(report.by_kind) == set(ao.TRANSITION_KINDS), sorted(report.by_kind)
    for kind, tally in report.by_kind.items():
        assert tally["verified"] > 0, (kind, tally)


@pytest.mark.req("REQ-APPLY-0004")
def test_the_diff_BITES_when_a_transition_is_wrong():
    """The positive control: *"the seam agrees"* and *"the instrument is blind"* produce the same
    green. Kept apart from its sibling — a union of zones would stay green if one half broke."""
    paths = sorted(lane.TRACES.glob("*.trace.json.gz"))[:4]
    combat = lane.offline_combat()
    assert lane.sweep(combat=combat, traces=paths).clean          # the same subset, honest

    original = bd.TRANSITIONS[bd._RETREAT]

    def _forgets_the_allowance(obs, option, *, seat_index, combat):
        delta = original(obs, option, seat_index=seat_index, combat=combat)
        delta.obs["current"]["retreated"] = False
        return delta

    bd.TRANSITIONS[bd._RETREAT] = _forgets_the_allowance
    try:
        broken = lane.sweep(combat=combat, traces=paths)
    finally:
        bd.TRANSITIONS[bd._RETREAT] = original
    assert not broken.clean
    assert {d.zone for d in broken.divergences} == {"allowance_retreat_used"}


@pytest.mark.req("REQ-APPLY-0004")
def test_a_deploy_that_forgets_the_NEW_IN_PLAY_bit_now_bites():
    """The bit is cleared on the LAST bench entry and by REPLACING the dict, never mutating it: a
    forked bench list shares its body dicts with the source observation the lane diffs against."""
    paths = sorted(lane.TRACES.glob("*.trace.json.gz"))[:4]
    combat = lane.offline_combat()
    assert lane.sweep(combat=combat, traces=paths).clean          # the same subset, honest

    original = bd.TRANSITIONS[bd._PLAY]

    def _forgets_the_bit(obs, option, *, seat_index, combat):
        delta = original(obs, option, seat_index=seat_index, combat=combat)
        players = ((delta.obs.get("current") or {}).get("players")) or []
        bench = (players[seat_index] or {}).get("bench") or []
        if bench and (bench[-1] or {}).get("appearThisTurn"):
            bench[-1] = {**bench[-1], "appearThisTurn": False}
        return delta

    bd.TRANSITIONS[bd._PLAY] = _forgets_the_bit
    try:
        broken = lane.sweep(combat=combat, traces=paths)
    finally:
        bd.TRANSITIONS[bd._PLAY] = original
    assert not broken.clean, "the deploy defect is invisible again — the zone has stopped comparing"
    assert {d.zone for d in broken.divergences} == {"new_in_play"}
    assert {d.kind for d in broken.divergences} == {bd._PLAY}


@pytest.mark.req("REQ-APPLY-0004")
def test_a_refusal_is_reported_as_a_backlog_line_and_not_as_a_divergence(report):
    """The seam declaring itself blind is the contract's always-expand answer, not a defect, so
    refusals are counted apart — and that grouping IS the modelling backlog."""
    assert report.refused > 0
    assert report.refusal_reasons
    assert sum(report.refusal_reasons.values()) == report.refused


@pytest.mark.req("REQ-APPLY-0004")
def test_nothing_is_quarantined_and_that_is_the_MEASUREMENT_not_an_omission(report):
    """The two facts are asserted TOGETHER so they cannot drift: a divergence found without the
    registry updated leaves this red."""
    assert ao.quarantined_kinds() == report.diverging_kinds()


@pytest.mark.req("REQ-APPLY-0004")
def test_the_committed_trace_corpus_has_not_shrunk():
    """The same guard `test_replay_fixtures.py` keeps over the same corpus: this lane's authority is
    the breadth of what it replays."""
    assert len(list(lane.TRACES.glob("*.trace.json.gz"))) >= 300
