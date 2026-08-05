"""THE resolution-parity gate: a CHOICE node's synthesized board must agree with the RECORDED NATIVE
ENGINE at the frame the option's whole resolution SETTLES to (POC-T4/5, Issue #392; ADR-TEMP-392
decision 7).

`test_apply_seam_parity.py` beside this one diffs against the **next** recorded frame, which is the
right reference for a point transition. It cannot reach a Deferred-Target Option: the engine answers a
`_RETREAT` by setting ``current.retreated`` and posing the rest as separate selects
(`_DISCARD_ENERGY` ctx 30, then `_SWITCH` ctx 3), so the board `common.board_choice` predicts is two
or three frames further on. `tools/train/choice_parity.py` walks there; this is its gate.

DLL-free by construction, exactly like its sibling — the trace IS the native side and cgpy's committed
tables supply the card facts.

**Budget-tagged**, same convention as the sibling: a session replays the first N traces in sorted
order (reproducible without a seed), and the full 377-trace sweep runs on demand
(``CHOICE_PARITY_FULL=1 python -m pytest tests/parity/test_choice_seam_parity.py``, or
``python tools/train/choice_parity.py``).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from common import board_choice as bc                     # noqa: E402
from train import choice_parity as lane                   # noqa: E402

#: Traces replayed in an ordinary session. 40 is the sibling lane's own figure and buys the same
#: thing here: four figures of frames and, measured, ~500 choice steps in a few seconds.
CI_TRACES = 40

FULL = os.environ.get("CHOICE_PARITY_FULL") == "1"


@pytest.fixture(scope="module")
def report():
    return lane.sweep(limit=None if FULL else CI_TRACES)


@pytest.mark.req("REQ-APPLY-0004")
def test_the_choice_node_agrees_with_the_recorded_engine_at_the_settled_frame(report):
    """The gate. For every retreat the trace records, the board `board_choice` synthesizes for the
    instance actually TAKEN must equal the recorded settled board on every homed zone."""
    assert report.clean, f"\n{report}"


@pytest.mark.req("REQ-APPLY-0004")
def test_the_taken_target_is_always_INSIDE_the_enumerated_space(report):
    """The enumeration half, asserted apart from the arithmetic half because they are different bugs.

    Only the taken branch is observable — the counterfactuals are unrecorded by construction — so this
    cannot prove the space is complete. What it does prove is that no *systematic* enumeration error
    survives: an off-by-one in the Bench indices, a discard set the product never forms, a body class
    the resolver excludes would each make some taken instance unfindable, and none does over the
    corpus."""
    assert not report.unenumerated, "\n".join(report.unenumerated[:20])


@pytest.mark.req("REQ-APPLY-0004")
def test_the_lane_is_not_vacuous(report):
    """A green gate means nothing if the sweep never reached the code — and here the failure mode is
    specific rather than hypothetical: every one of the lane's own exits (``refused``, ``unsettled``,
    ``unenumerated``) skips the diff, so a lane that refused EVERY step would report `clean` and prove
    nothing at all.

    So: the population is non-empty, most of it is verified, and the kinds walked are exactly the ones
    `board_choice` declares — a kind added to `CHOICE_KINDS` with no `TAKEN` reader would fail here
    rather than go quietly unchecked."""
    assert report.choice_steps > 0
    assert report.verified > report.choice_steps * 0.9, str(report)
    assert set(lane.TAKEN) == set(bc.CHOICE_KINDS)


@pytest.mark.req("REQ-APPLY-0004")
def test_the_relaxed_discard_ORDER_is_the_only_relaxation_and_it_is_COUNTED(report):
    """The lane relaxes exactly one comparison — `my_discard_contents` as a multiset — and that must
    stay visible and stay small.

    The relaxation is real and measured: over the full corpus 10 of 2254 steps take it, every one a
    two-card discard whose pair the engine appended in the opposite order, because it appends in the
    order the ctx-30 selects were ANSWERED and that order is a property of the policy that recorded
    the trace rather than of the rules (`docs/rulebook.txt` L142 assigns none). Asserting the COUNT
    beside the zone is what stops it widening into "the lane stopped comparing the discard": a wrong
    CARD still changes the multiset and still fails."""
    assert lane._ORDER_INSENSITIVE == {"my_discard_contents"}
    assert report.order_only <= report.verified * 0.05, str(report)


@pytest.mark.req("REQ-APPLY-0004")
def test_the_diff_BITES_when_the_synthesis_puts_the_retreating_body_in_the_WRONG_BENCH_SLOT():
    """**The positive control**, and it is not optional: *"the synthesis agrees"* and *"the instrument
    is blind"* produce the identical green.

    The defect injected is the one the traces were read to settle in the first place — the engine
    swaps A into exactly the Bench index the promoted body vacated, and this appends it at the END
    instead. On a one-body Bench the two are the same board, which is why the control runs over traces
    holding real benches and asserts a measured count rather than merely *not clean*.

    **82 divergences over 6 traces, in three zones**, and the three are the finding rather than noise:
    `bodies_in_play` (the Bench list itself), plus `damage_counters` and `new_in_play`, which are
    homed PER BODY across the Bench (`snapshot_coverage.homes()`), so reordering the list moves them
    too. `attached_energy` is deliberately absent from that set — it is homed on the ACTIVE alone, so
    a benched body's Energy reaches this lane through `bodies_in_play`'s own `BodyView` projection and
    not through its own zone. Asserting the set EXACTLY is what makes that legible instead of
    something a later reader has to rediscover."""
    paths = sorted(lane.TRACES.glob("*.trace.json.gz"))[:6]
    combat = lane.offline_combat()
    assert lane.sweep(combat=combat, traces=paths).clean           # the same subset, honest

    original = bc._APPLIERS[bc._RETREAT][0]

    def _appends_instead_of_swapping(model, candidate, *, seat_index):
        obs, writes = original(model, candidate, seat_index=seat_index)
        _discard, promote_idx = candidate
        me = ((obs.get("current") or {}).get("players"))[seat_index]
        bench = list(me.get("bench") or ())
        if len(bench) > 1:
            me["bench"] = [b for i, b in enumerate(bench) if i != promote_idx] + [bench[promote_idx]]
        return obs, writes

    bc._APPLIERS[bc._RETREAT] = (_appends_instead_of_swapping, bc._APPLIERS[bc._RETREAT][1])
    try:
        broken = lane.sweep(combat=combat, traces=paths)
    finally:
        bc._APPLIERS[bc._RETREAT] = (original, bc._APPLIERS[bc._RETREAT][1])
    assert not broken.clean
    assert {d.zone for d in broken.divergences} == {"bodies_in_play", "damage_counters",
                                                    "new_in_play"}


@pytest.mark.req("REQ-APPLY-0004")
def test_the_diff_BITES_when_the_DISCARDED_ENERGY_never_reaches_the_discard_pile():
    """**The second control, on the other dimension** — and the one that proves the ORDER relaxation
    did not quietly turn into "the lane stopped comparing the discard".

    Kept apart from the first deliberately: a single test asserting a union of zones would stay green
    if either half stopped working. That one proves the lane sees where a body LANDED; this proves it
    sees the Energy-discard leg, which is the dimension ADR-0100 §8's `build_after` is demoted to a
    ranker over (ADR-TEMP-392 decision 5) and therefore the one this issue newly enumerates.

    The defect leaves the discard pile untouched while the retreat still strips the Energy off the
    body. **372 divergences over 6 traces, in three zones**: `my_discard_contents` directly, plus
    `deck_odds` and `my_deck_count`, because `MySide` derives the deck from *decklist − visible −
    prizes* and the discard is part of *visible* — the same threading dividend the sibling lane
    measured for itself.

    That `my_discard_contents` is in the set is the load-bearing assertion: `_ORDER_INSENSITIVE`
    relaxes that zone to a multiset comparison, and a MISSING card changes the multiset."""
    paths = sorted(lane.TRACES.glob("*.trace.json.gz"))[:6]
    combat = lane.offline_combat()
    assert lane.sweep(combat=combat, traces=paths).clean           # the same subset, honest

    original = bc._APPLIERS[bc._RETREAT][0]

    def _never_discards(model, candidate, *, seat_index):
        obs, writes = original(model, candidate, seat_index=seat_index)
        me = ((obs.get("current") or {}).get("players"))[seat_index]
        pre = ((model.source_obs.get("current") or {}).get("players"))[seat_index]
        me["discard"] = list(pre.get("discard") or ())
        return obs, writes

    bc._APPLIERS[bc._RETREAT] = (_never_discards, bc._APPLIERS[bc._RETREAT][1])
    try:
        broken = lane.sweep(combat=combat, traces=paths)
    finally:
        bc._APPLIERS[bc._RETREAT] = (original, bc._APPLIERS[bc._RETREAT][1])
    assert not broken.clean
    assert {d.zone for d in broken.divergences} == {"my_discard_contents", "deck_odds",
                                                    "my_deck_count"}
