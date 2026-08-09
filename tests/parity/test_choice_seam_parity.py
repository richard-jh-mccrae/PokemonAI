"""THE resolution-parity gate: a CHOICE node's synthesized board must agree with the RECORDED NATIVE
ENGINE at the frame the option's whole resolution SETTLES to (ADR-0121 decision 7).

`test_apply_seam_parity.py` diffs against the NEXT recorded frame, which cannot reach a
Deferred-Target Option: the engine answers a `_RETREAT` by setting ``current.retreated`` and posing
the rest as separate selects, so the predicted board is two or three frames further on.
`tools/train/choice_parity.py` walks there; this is its gate. DLL-free, like its sibling.

NOT budget-tagged: the lane includes every #455 synthesis and the full sweep is seconds, so it runs
COMPLETE. ``CHOICE_PARITY_TRACES`` shortens it locally.
"""
from __future__ import annotations

import dataclasses
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from common import board_choice as bc                     # noqa: E402
from train import choice_parity as lane                   # noqa: E402

#: Traces replayed per session — ALL of them: subsetting would trade the criterion's own
#: denominator for nothing. ``CHOICE_PARITY_TRACES`` shortens it for a local loop.
CI_TRACES = int(os.environ["CHOICE_PARITY_TRACES"]) if os.environ.get("CHOICE_PARITY_TRACES") else None

#: The full corpus's own numbers, so a subset run cannot quietly report as the gate the criterion
#: names. Measured at this commit: 369 traces / 37 418 frames / 2304 choice steps.
FULL_CHOICE_STEPS = 2304


def _swap_applier(fn):
    """`dataclasses.replace` rather than rebuilding the record: a reconstruction would silently drop
    a leg added later, and the injected-defect run would then differ for the wrong reason."""
    bc.CHOICE_REGISTRY[bc._RETREAT] = dataclasses.replace(
        bc.CHOICE_REGISTRY[bc._RETREAT], apply=fn)


@pytest.fixture(scope="module")
def report():
    return lane.sweep(limit=CI_TRACES)


@pytest.mark.req("REQ-APPLY-0004")
def test_the_choice_node_agrees_with_the_recorded_engine_at_the_settled_frame(report):
    """The gate. For every retreat the trace records, the board `board_choice` synthesizes for the
    instance actually TAKEN must equal the recorded settled board on every homed zone."""
    assert report.clean, f"\n{report}"


@pytest.mark.req("REQ-APPLY-0004")
def test_the_taken_target_is_always_INSIDE_the_enumerated_space(report):
    """Only the taken branch is observable, so this cannot prove the space COMPLETE — it proves no
    systematic enumeration error survives, since each would make some taken instance unfindable."""
    assert not report.unenumerated, "\n".join(report.unenumerated[:20])


@pytest.mark.req("REQ-APPLY-0004")
def test_the_lane_is_not_vacuous(report):
    """Every one of the lane's exits (``refused``, ``unsettled``, ``unenumerated``) skips the diff,
    so a lane that refused EVERY step would report `clean` and prove nothing at all."""
    assert report.choice_steps > 0
    assert report.verified > report.choice_steps * 0.9, str(report)
    assert set(lane.TAKEN) == set(lane.PARITY_KEYS)
    assert all(report.by_key[key]["verified"] > 0 for key in lane.PARITY_KEYS), str(report)
    # Assert the gate actually walked the full denominator rather than a subset that
    # happened to be green. Skipped only when a local run deliberately shortened the corpus.
    if CI_TRACES is None:
        assert report.choice_steps == FULL_CHOICE_STEPS, str(report)


@pytest.mark.req("REQ-APPLY-0004")
def test_the_relaxed_discard_ORDER_is_the_only_relaxation_and_it_is_COUNTED(report):
    """The engine appends a discard in the order the ctx-30 selects were ANSWERED, which the rules
    do not assign. Asserting the COUNT beside the zone stops the relaxation widening."""
    assert lane._ORDER_INSENSITIVE == {"my_discard_contents"}
    assert report.order_only <= report.verified * 0.05, str(report)


@pytest.mark.req("REQ-APPLY-0004")
def test_the_diff_BITES_when_the_synthesis_puts_the_retreating_body_in_the_WRONG_BENCH_SLOT():
    """The engine swaps the retreating body into exactly the Bench index the promoted one vacated;
    this control appends it at the END, which on a ONE-body Bench would be the same board."""
    paths = sorted(lane.TRACES.glob("*.trace.json.gz"))[:6]
    combat = lane.offline_combat()
    assert lane.sweep(combat=combat, traces=paths).clean           # the same subset, honest

    original = bc.CHOICE_REGISTRY[bc._RETREAT].apply

    def _appends_instead_of_swapping(model, candidate, *, seat_index):
        obs, writes = original(model, candidate, seat_index=seat_index)
        _discard, promote_idx = candidate
        me = ((obs.get("current") or {}).get("players"))[seat_index]
        bench = list(me.get("bench") or ())
        if len(bench) > 1:
            me["bench"] = [b for i, b in enumerate(bench) if i != promote_idx] + [bench[promote_idx]]
        return obs, writes

    _swap_applier(_appends_instead_of_swapping)
    try:
        broken = lane.sweep(combat=combat, traces=paths)
    finally:
        _swap_applier(original)
    assert not broken.clean
    assert {d.zone for d in broken.divergences} == {"bodies_in_play", "damage_counters",
                                                    "new_in_play"}


@pytest.mark.req("REQ-APPLY-0004")
def test_the_diff_BITES_when_the_DISCARDED_ENERGY_never_reaches_the_discard_pile():
    """Kept apart from the first control: a union of zones would stay green if either half broke.
    `my_discard_contents` in the set is load-bearing — a MISSING card still changes the multiset."""
    paths = sorted(lane.TRACES.glob("*.trace.json.gz"))[:6]
    combat = lane.offline_combat()
    assert lane.sweep(combat=combat, traces=paths).clean           # the same subset, honest

    original = bc.CHOICE_REGISTRY[bc._RETREAT].apply

    def _never_discards(model, candidate, *, seat_index):
        obs, writes = original(model, candidate, seat_index=seat_index)
        me = ((obs.get("current") or {}).get("players"))[seat_index]
        pre = ((model.source_obs.get("current") or {}).get("players"))[seat_index]
        me["discard"] = list(pre.get("discard") or ())
        return obs, writes

    _swap_applier(_never_discards)
    try:
        broken = lane.sweep(combat=combat, traces=paths)
    finally:
        _swap_applier(original)
    assert not broken.clean
    assert {d.zone for d in broken.divergences} == {"my_discard_contents", "deck_odds",
                                                    "my_deck_count"}
