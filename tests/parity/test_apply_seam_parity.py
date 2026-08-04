"""THE apply-seam parity gate: the closed-form transition must agree with the RECORDED NATIVE ENGINE
(POC-T4/1, Issue #382; ADR-0098 decision 4, Issue #263 § *Parity + retirement*).

`common.apply_option` predicts the board after one option without stepping an engine. That claim is
worth exactly what checks it, and the check is here: `tools/train/apply_parity.py` replays the
committed native traces one step at a time through the seam and diffs the resulting `StateModel`
against the model built from the next recorded frame, on the facts the value layer reads
(`snapshot_coverage`'s HOMED zone registry).

DLL-free by construction — the trace IS the native side and cgpy's committed tables supply the card
facts — so this runs on any platform, exactly like `test_replay_fixtures.py` beside it.

**Budget-tagged.** A test session replays a subset; the full 377-trace sweep runs on demand
(``APPLY_PARITY_FULL=1 python -m pytest tests/parity/test_apply_seam_parity.py``, or
``python tools/train/apply_parity.py``). The subset is the FIRST N traces in sorted order rather than
a sample, so the set a failure names is reproducible without a seed.

**A divergence is a ruled seam bug, never an accepted approximation.** The remedy is
`apply_option.QUARANTINED_KINDS`, which is a ruling record: a kind lands there only with its
divergence filed, and the planner then degrades to always-expand visibly rather than mis-playing the
kind in silence.
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

#: Traces replayed in an ordinary session. Measured rather than guessed: 40 traces cover all four
#: modelled kinds with four figures of steps and run in a few seconds, while the full sweep is
#: minutes. The full run is one environment variable away and is what a wave measurement uses.
CI_TRACES = 40

FULL = os.environ.get("APPLY_PARITY_FULL") == "1"


@pytest.fixture(scope="module")
def report():
    return lane.sweep(limit=None if FULL else CI_TRACES)


@pytest.mark.req("REQ-APPLY-0004")
def test_the_seam_agrees_with_the_recorded_engine_on_every_modelled_step(report):
    """The gate. Every step the seam produced a board for must match the engine's next frame on every
    homed zone — the seam is allowed to differ from the observation on anything no equation reads,
    and on nothing that one does."""
    assert report.clean, f"\n{report}"


@pytest.mark.req("REQ-APPLY-0004")
def test_the_lane_actually_replays_all_four_modelled_kinds(report):
    """A green gate means nothing if the sweep never reached the code. The four kinds
    `TRANSITION_KINDS` declares must each appear, and each must have VERIFIED steps rather than only
    refused ones — a lane that refused everything would be green and vacuous."""
    assert set(report.by_kind) == set(ao.TRANSITION_KINDS), sorted(report.by_kind)
    for kind, tally in report.by_kind.items():
        assert tally["verified"] > 0, (kind, tally)


@pytest.mark.req("REQ-APPLY-0004")
def test_the_diff_BITES_when_a_transition_is_wrong():
    """**The positive control**, and it is not optional here: *"the seam agrees"* and *"the instrument
    is blind"* produce the identical green. So one transition is deliberately broken — the retreat
    forgets to spend the allowance, the smallest write in the whole module — and the lane must go
    red on it. If this passes while the gate above also passes, the gate is evidence.

    ⚠️ **The control found a real blind spot, and it is filed rather than papered over.** Four defects
    were injected while building this lane; three went red (the energy allowance, 551 divergences;
    carried damage across an evolution, 2; a retreat modelling the whole maneuver, 471). The fourth —
    a deploy that forgets `appearThisTurn` — went **green**, because that bit is enumerated in no
    `snapshot_coverage` zone and so has no snapshot home for this projection to read. **Issue #391**
    owns it, and its acceptance is that this test grows a second control that bites."""
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
def test_a_refusal_is_reported_as_a_backlog_line_and_not_as_a_divergence(report):
    """The seam declaring itself blind is the contract's own always-expand answer, not a defect — so
    refusals are counted apart and grouped by reason, and that grouping IS the modelling backlog
    POC-T4/2 (Issue #383) works from. Non-empty because the corpus contains draw and fetch Trainers,
    which are Expectation nodes rather than point transitions."""
    assert report.refused > 0
    assert report.refusal_reasons
    assert sum(report.refusal_reasons.values()) == report.refused


@pytest.mark.req("REQ-APPLY-0004")
def test_nothing_is_quarantined_and_that_is_the_MEASUREMENT_not_an_omission(report):
    """`QUARANTINED_KINDS` is empty because the lane is clean, and the two facts are asserted
    together so they cannot drift apart: a divergence found without the registry updated leaves this
    red, which is the direction that matters."""
    assert ao.quarantined_kinds() == report.diverging_kinds()


@pytest.mark.req("REQ-APPLY-0004")
def test_the_committed_trace_corpus_has_not_shrunk():
    """The same guard `test_replay_fixtures.py` keeps over the same corpus: this lane's authority is
    the breadth of what it replays."""
    assert len(list(lane.TRACES.glob("*.trace.json.gz"))) >= 300
