"""The two deterministic merge gates for a mid-build decider swap (ADR-0071, #167).

#136 directive 6 used to gate a swap on a paired A/B win-rate test. Phase 1b measured what that
costs: −1.17 pp, 95% CI [−4.59, +2.25] over 2400 games — a run that demonstrated neither a
regression nor a non-regression, and which no affordable n could settle. Merit therefore moved to two
instruments that answer EXACTLY rather than statistically, both per-frame, both pure:

  * the **Decision Gate**    — the phase's decider sweep: zero unruled REGRESSION frames.
  * the **Discrimination Gate** — a Leaf Lab capture diffed before/after: zero unruled OK->MISS flips.

Everything here is dict-in/value-out with no engine, no cgpy, no DLL and no Pilot, which is what lets
the gates run in the offline cross-platform suite. Prior art for the style: `tests/sim/test_paired_ab.py`
(hand-built aggregates -> a verdict) and `tests/sim/test_score_diff.py` (hand-built records -> a diff).
"""
import pytest

from train.gates import (EVOLVE_LANE, OWNER_RE, AxisClaim, DecisionClaim, EndorsementClaim,
                         decision_gate_verdict, discrimination_gate_verdict, evaluate_axis_claim,
                         evaluate_decision_claim, evaluate_endorsement_claim, held_out_owner,
                         lane_slots, leaf_lab_diff, option_slot, parse_claims)

# ── slot resolution — the shared basis both sweeps and Axis Claims compare on ─────────────────────


@pytest.mark.req("REQ-TRAIN-0040")
def test_option_slot_distinguishes_two_options_that_differ_only_by_body():
    """The reason comparison is by resolved BODY SLOT and never by raw option index: two
    Dreepy->Drakloak evolves differ ONLY in which body they evolve, and the index says nothing about
    which. (`evolve_decider_sweep.py` header, ADR-0069 §8.)"""
    bench_1 = {"type": 9, "area": 5, "index": 0, "inPlayArea": 2, "inPlayIndex": 1}
    bench_2 = {"type": 9, "area": 5, "index": 1, "inPlayArea": 2, "inPlayIndex": 2}
    assert option_slot(bench_1) == (2, 1)
    assert option_slot(bench_2) == (2, 2)
    assert option_slot(bench_1) != option_slot(bench_2)


@pytest.mark.req("REQ-TRAIN-0040")
def test_option_slot_falls_back_to_area_index_for_non_in_play_options():
    """An ATTACH_FROM card names its slot as (area, index) rather than (inPlayArea, inPlayIndex) —
    the attach sweep's second lane member. One resolver serves both shapes."""
    assert option_slot({"type": 3, "area": 4, "index": 2}) == (4, 2)
    assert option_slot({"type": 14}) is None                  # END targets no slot


@pytest.mark.req("REQ-TRAIN-0040")
def test_lane_slots_filters_to_the_lane_and_honours_a_context_qualified_member():
    """A Lane is (option_type, required_select_context|None) members, so the attach sweep's rule —
    ATTACH always, CARD only under the ATTACH_FROM context — is DATA, not a special case at a call
    site. An evolve lane is the simple single-member case."""
    options = [{"type": 9, "inPlayArea": 2, "inPlayIndex": 0},    # 0 evolve
               {"type": 3, "area": 4, "index": 1},                 # 1 card
               {"type": 14}]                                       # 2 end
    assert lane_slots([0, 1, 2], options, lane=EVOLVE_LANE) == {(2, 0)}

    attach_lane = ((8, None), (3, 21))
    assert lane_slots([0, 1, 2], options, lane=attach_lane, select_context=21) == {(4, 1)}
    assert lane_slots([0, 1, 2], options, lane=attach_lane, select_context=0) == set()


# ── claims — what a corpus fixture asserts (ADR-0071 decision 3) ──────────────────────────────────


@pytest.mark.req("REQ-TRAIN-0041")
def test_a_fixture_with_no_claims_block_still_asserts_its_correct_option():
    """Back-compat is the whole reason back-fill can be incremental: all ~130 existing fixtures carry
    no `claims` block and must keep their present meaning with no edit — a Decision Claim over
    `correct`."""
    claims = parse_claims({"correct": [2], "chosen": [0]})
    assert claims.decision == DecisionClaim(correct=[2], owner=None)
    assert claims.axis == []
    assert evaluate_decision_claim(claims.decision, chosen=[2]) is True
    assert evaluate_decision_claim(claims.decision, chosen=[1]) is False


@pytest.mark.req("REQ-TRAIN-0041")
def test_an_axis_claim_asserts_ordering_within_one_lane_not_a_score():
    """Ordering, never scores. 1a rewrote f29 FROM a score claim TO a decision claim because raw
    scores are not comparable across a currency re-banding; an Axis Claim generalises that lesson —
    ordering WITHIN a lane survives re-banding, cross-lane scores do not."""
    claim = AxisClaim(lane=EVOLVE_LANE, prefer=(2, 1), over=[(2, 0)], owner=None)
    options = [{"type": 9, "inPlayArea": 2, "inPlayIndex": 0},
               {"type": 9, "inPlayArea": 2, "inPlayIndex": 1}]

    # the preferred body outranks its named rival -> pass, at ANY scale
    assert evaluate_axis_claim(claim, options=options, scores=[15.0, 20.0]) is True
    assert evaluate_axis_claim(claim, options=options, scores=[1500.0, 2000.0]) is True
    # the rival outranks the preferred body -> fail
    assert evaluate_axis_claim(claim, options=options, scores=[20.0, 15.0]) is False
    # a tie is NOT an ordering (the argmax breaks by option order, not by the claim)
    assert evaluate_axis_claim(claim, options=options, scores=[20.0, 20.0]) is False


@pytest.mark.req("REQ-TRAIN-0041")
def test_an_axis_claim_ignores_options_outside_its_lane():
    """The point of the axis: a non-evolve option scoring higher is IRRELEVANT to an evolve-lane
    claim. This is exactly f35 — the evolve axis is right and the frame is decided elsewhere."""
    claim = AxisClaim(lane=EVOLVE_LANE, prefer=(2, 1), over=[(2, 0)], owner=None)
    options = [{"type": 9, "inPlayArea": 2, "inPlayIndex": 0},
               {"type": 9, "inPlayArea": 2, "inPlayIndex": 1},
               {"type": 10, "area": 2, "index": 0}]              # an ABILITY, another lane entirely
    assert evaluate_axis_claim(claim, options=options, scores=[0.0, 8.75, 999.0]) is True


@pytest.mark.req("REQ-TRAIN-0041")
def test_an_endorsement_claim_asserts_a_lane_option_is_or_is_not_taken_at_all():
    """The single-option-lane case, which ordering cannot reach. f35 has exactly ONE evolve option,
    so "prefer X over Y" is inexpressible — yet the swap's real fix there is that the premature evolve
    went 45.0 -> 0.0 with no rule firing. An Endorsement Claim states that: does the option clear the
    endorsement floor (`score > 0`, `_finish_turn_last`'s gate) at all?

    Zero is a STRUCTURAL boundary — where the agent decides whether to act — not a tuned magnitude,
    so this survives a currency re-banding exactly as ordering does. It is NOT the score claim 1a's
    f29 rewrite rejected: no magnitude is compared."""
    options = [{"type": 9, "inPlayArea": 4, "inPlayIndex": 0}]
    declined = EndorsementClaim(lane=EVOLVE_LANE, slot=(4, 0), endorsed=False, owner=None)

    assert evaluate_endorsement_claim(declined, options=options, scores=[0.0]) is True
    assert evaluate_endorsement_claim(declined, options=options, scores=[-4.0]) is True
    assert evaluate_endorsement_claim(declined, options=options, scores=[45.0]) is False   # incumbent
    # re-banding-proof: an endorsed option stays endorsed at any scale
    endorsed = EndorsementClaim(lane=EVOLVE_LANE, slot=(4, 0), endorsed=True, owner=None)
    assert evaluate_endorsement_claim(endorsed, options=options, scores=[8.75]) is True
    assert evaluate_endorsement_claim(endorsed, options=options, scores=[8750.0]) is True
    assert evaluate_endorsement_claim(endorsed, options=options, scores=[0.0]) is False


@pytest.mark.req("REQ-TRAIN-0041")
def test_an_endorsement_claim_for_an_absent_slot_is_unprovable_not_vacuously_true():
    """A claim whose slot is not on the menu must never read as satisfied — a vacuous pass is how a
    stale claim survives the board changing underneath it."""
    claim = EndorsementClaim(lane=EVOLVE_LANE, slot=(2, 9), endorsed=False, owner=None)
    assert evaluate_endorsement_claim(claim, options=[{"type": 9, "inPlayArea": 4, "inPlayIndex": 0}],
                                      scores=[0.0]) is None


@pytest.mark.req("REQ-TRAIN-0041")
def test_held_out_status_is_per_claim_not_per_fixture():
    """f35's shape: its Decision Claim is owned by #165 (a non-evolve lane decides the frame) while
    its Axis Claim still GATES. A per-fixture flag could not express that, and would either hide a
    live claim or gate a deferred one."""
    claims = parse_claims({
        "correct": [2],
        "claims": {"decision": {"correct": [2], "owner": "#165", "why": "cross-lane"},
                   "axis": [{"lane": 9, "prefer": [2, 1], "over": [[2, 0]]}]},
    })
    assert held_out_owner(claims.decision) == "#165"
    assert held_out_owner(claims.axis[0]) is None


# ── the Leaf Lab diff — the Discrimination Gate's instrument ──────────────────────────────────────


def _row(key, verdict, *, tie=1):
    return {"key": key, "correct_is_top": verdict == "OK", "unscorable": False, "top_tie": tie}


def _report(rows):
    return {"rows": rows, "scorable": len(rows)}


@pytest.mark.req("REQ-TRAIN-0042")
def test_identical_reports_diff_clean():
    rows = [_row("1|0|decision|3", "OK"), _row("2|0|decision|7", "MISS")]
    d = leaf_lab_diff(_report(rows), _report(rows))
    assert d["ok_to_miss"] == [] and d["miss_to_ok"] == []


@pytest.mark.req("REQ-TRAIN-0042")
def test_an_ok_to_miss_flip_is_reported_and_a_miss_to_ok_flip_is_reported_separately():
    """Phase 1b's real shape: 6 OK->MISS and 0 MISS->OK, strictly one-directional. Only the
    degradation direction gates; an improvement is reported so a swap gets credit for it."""
    before = _report([_row("a", "OK"), _row("b", "MISS")])
    after = _report([_row("a", "MISS"), _row("b", "OK")])
    d = leaf_lab_diff(before, after)
    assert [f["key"] for f in d["ok_to_miss"]] == ["a"]
    assert [f["key"] for f in d["miss_to_ok"]] == ["b"]


@pytest.mark.req("REQ-TRAIN-0042")
def test_repeated_episodes_do_not_collapse_when_keyed_by_identity():
    """The 276-vs-221 collapse, pinned. Keying rows by `episode_id` alone silently merged frames from
    the same episode and UNDER-REPORTED the diff — the exact failure the gate exists to prevent. Rows
    key on the Correction's `identity_key` (episode, seat, scope, subject) instead."""
    before = _report([_row("81905522|0|decision|5", "OK"), _row("81905522|0|decision|9", "OK")])
    after = _report([_row("81905522|0|decision|5", "OK"), _row("81905522|0|decision|9", "MISS")])
    d = leaf_lab_diff(before, after)
    assert [f["key"] for f in d["ok_to_miss"]] == ["81905522|0|decision|9"]


@pytest.mark.req("REQ-TRAIN-0042")
def test_a_row_present_on_only_one_side_is_reported_rather_than_ignored():
    """A capture taken against a different corpus shape must be visible, never silently tolerated —
    a diff that quietly skips frames reads as green for the wrong reason."""
    d = leaf_lab_diff(_report([_row("a", "OK")]), _report([_row("a", "OK"), _row("b", "OK")]))
    assert d["added"] == ["b"] and d["removed"] == []


# ── the gate verdicts ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-TRAIN-0043")
def test_discrimination_gate_fails_on_an_unruled_flip_and_passes_when_it_is_held_out():
    """The Held-out Ledger in one assertion (ADR-0071 decision 4): a re-ruling is a STATE the gate
    reads, not prose in a review doc. Deleting the owner returns the frame to gating."""
    diff = {"ok_to_miss": [{"key": "a"}], "miss_to_ok": [], "added": [], "removed": []}
    assert discrimination_gate_verdict(diff, held_out={}) is False
    assert discrimination_gate_verdict(diff, held_out={"a": "#165"}) is True
    assert discrimination_gate_verdict(diff, held_out={"b": "#165"}) is False   # wrong frame held out


@pytest.mark.req("REQ-TRAIN-0043")
def test_discrimination_gate_passes_on_improvements_alone():
    """A swap that only sharpens the leaf in the human's favour is not blocked by its own gains."""
    diff = {"ok_to_miss": [], "miss_to_ok": [{"key": "b"}], "added": [], "removed": []}
    assert discrimination_gate_verdict(diff, held_out={}) is True


@pytest.mark.req("REQ-TRAIN-0044")
def test_every_committed_fixture_parses_and_every_held_out_claim_names_an_issue():
    """The Held-out Ledger's shape check, over the real corpus. A malformed ruling must be caught
    offline — the suite has no network, so whether that issue is still OPEN is explicitly NOT checked
    and belongs on the phase checklist (ADR-0071 decision 4)."""
    import json
    from pathlib import Path
    fixtures = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "corrections"
    paths = sorted(fixtures.glob("*.json"))
    assert paths, "the corpus fixtures moved"
    for p in paths:
        fx = json.loads(p.read_text(encoding="utf-8"))
        claims = parse_claims(fx)                     # must never raise on a committed fixture
        for c in claims.all_claims():
            owner = held_out_owner(c)
            if owner is not None:
                assert OWNER_RE.match(owner), f"{p.name}: owner {owner!r} is not an issue reference"
        if fx.get("frame_key"):
            assert fx["frame_key"].count("|") == 3, f"{p.name}: frame_key is not an identity_key"


@pytest.mark.req("REQ-TRAIN-0043")
def test_decision_gate_fails_on_unruled_regression_frames_only():
    """The Decision Gate is ADR-0069 §8's sweep protocol promoted from convention to a gate. FIX and
    DIVERGENT verdicts do not block — only a REGRESSION the human has not ruled."""
    assert decision_gate_verdict([{"key": "a", "verdict": "FIX"}], held_out={}) is True
    assert decision_gate_verdict([{"key": "a", "verdict": "REGRESSION"}], held_out={}) is False
    assert decision_gate_verdict([{"key": "a", "verdict": "REGRESSION"}],
                                 held_out={"a": "#165"}) is True
