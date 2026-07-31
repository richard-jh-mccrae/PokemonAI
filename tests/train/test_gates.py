"""The two deterministic merge gates for a mid-build decider swap (ADR-0072, #167).

#136 directive 6 used to gate a swap on a paired A/B win-rate test. Phase 1b measured what that
costs: −1.17 pp, 95% CI [−4.59, +2.25] over 2400 games — a run that demonstrated neither a
regression nor a non-regression, and which no affordable n could settle. Merit therefore moved to two
instruments that answer EXACTLY rather than statistically, both per-frame, both pure:

  * the **Decision Gate**    — a Decider Lab capture diffed against a committed baseline: zero
    unruled REGRESSION frames. (It was "the phase's decider sweep" until ADR-0085 Amendment I; that
    arm scored an emptied rung pile, so it could only ever report FIX.)
  * the **Discrimination Gate** — a Leaf Lab capture diffed before/after: zero unruled OK->MISS flips.

Everything here is dict-in/value-out with no engine, no cgpy, no DLL and no Pilot, which is what lets
the gates run in the offline cross-platform suite. Prior art for the style: `tests/sim/test_paired_ab.py`
(hand-built aggregates -> a verdict) and `tests/sim/test_score_diff.py` (hand-built records -> a diff).
"""
import json
from pathlib import Path

import pytest

# The corpus's on-disk shape lives in ONE place, because a second test file needed a `tmp_path`
# corpus (Issue #250) and would otherwise re-encode it — the same second-idea-of-a-record defect
# ADR-0087 is about, one layer down. Aliased to the original private names, so the 18 call sites
# below read unchanged.
from corrections_helpers import correction_record as _rec
from corrections_helpers import corrections_store as _store

#: Spelled from ordinals so this file can never itself be normalised into asserting nothing — the
#: literal it looks for is exactly the byte pair a Windows `write_text` would introduce.
CRLF = bytes((13, 10))

from train import gates
from train.gates import (EVOLVE_LANE, OWNER_RE, RULED_RE, AxisClaim, DecisionClaim, EndorsementClaim,
                         decision_gate_verdict, discrimination_gate_verdict, evaluate_axis_claim,
                         evaluate_decision_claim, evaluate_endorsement_claim, held_out_owner,
                         lane_slots, leaf_lab_diff, option_slot, parse_claims,
                         decider_lab_diff, decision_gate_verdict, satisfies_human)

# ── slot resolution — the shared basis both sweeps and Axis Claims compare on ─────────────────────


@pytest.mark.req("REQ-TRAIN-0040")
def test_lane_constants_match_the_engine_enums():
    """CLAUDE.md: engine vocabulary (option types, select contexts) comes from `src/cg/api.py`, never
    from memory. But importing `cg.api` MAPS THE NATIVE LIBRARY (`libcg` shows up in /proc/self/maps
    on a bare import), and `train.gates` must stay loadable with no DLL — the same reason
    `planner.py` keeps its engine import lazy. So the lane constants are written literally there and
    PINNED here: this test is what makes them sourced rather than remembered, and it fails the moment
    one drifts."""
    from cg.api import AreaType, OptionType, SelectContext
    assert gates.OPTION_TYPE_EVOLVE == int(OptionType.EVOLVE)
    assert gates.OPTION_TYPE_ATTACH == int(OptionType.ATTACH)
    assert gates.OPTION_TYPE_CARD == int(OptionType.CARD)
    assert gates.SELECT_CONTEXT_ATTACH_FROM == int(SelectContext.ATTACH_FROM)
    assert EVOLVE_LANE == ((int(OptionType.EVOLVE), None),)
    assert gates.ATTACH_LANE == ((int(OptionType.ATTACH), None),
                                 (int(OptionType.CARD), int(SelectContext.ATTACH_FROM)))
    assert gates.SELECT_CONTEXT_SWITCH == int(SelectContext.SWITCH)
    assert gates.SELECT_CONTEXT_TO_ACTIVE == int(SelectContext.TO_ACTIVE)
    assert gates.PROMOTE_LANE == ((int(OptionType.CARD), int(SelectContext.SWITCH)),
                                  (int(OptionType.CARD), int(SelectContext.TO_ACTIVE)))
    assert gates.OPTION_TYPE_PLAY == int(OptionType.PLAY)
    assert gates.SELECT_CONTEXT_SETUP_BENCH == int(SelectContext.SETUP_BENCH_POKEMON)
    assert gates.SELECT_CONTEXT_TO_BENCH == int(SelectContext.TO_BENCH)
    assert gates.AREA_HAND == int(AreaType.HAND)
    assert gates.DEPLOY_LANE == ((int(OptionType.PLAY), None),
                                 (int(OptionType.CARD), int(SelectContext.SETUP_BENCH_POKEMON)),
                                 (int(OptionType.CARD), int(SelectContext.TO_BENCH)))


# ── deploy option IDENTITY (ADR-0086, Issue #197) ────────────────────────────────────────────────


@pytest.mark.req("REQ-TRAIN-0041")
def test_option_slot_resolves_a_hand_play_to_its_card_id():
    """The case that forced the extension: a mid-game bench play is `OptionType.PLAY` with a BARE
    hand index and NO `area` (`strategy/context.py`: "play card from hand (bare hand `index`, no
    `area`)"), so the positional resolver returns None for exactly the options the Deploy Marginal
    ranks. Given the frame it resolves to the CARD, because "play Solrock" is one decision however
    the engine happens to order the menu."""
    frame = {"current": {"yourIndex": 0,
                         "players": [{"hand": [{"id": 1227}, {"id": 1121}, {"id": 676}]}, {}]}}
    assert option_slot({"type": 7, "index": 2}, frame) == ("card", 676)
    assert option_slot({"type": 7, "index": 0}, frame) == ("card", 1227)


@pytest.mark.req("REQ-TRAIN-0041")
def test_option_slot_resolves_a_setup_bench_hand_card_to_the_same_identity():
    """The pregame Bench places with `OptionType.CARD` + `area = HAND` rather than PLAY
    (`setup_bench_decline_f3`), and `_TO_BENCH` fetches straight onto the Bench. All three deploy
    entry points must resolve to the SAME identity or the lane compares apples to oranges."""
    frame = {"current": {"yourIndex": 0, "players": [{"hand": [{"id": 1071}]}, {}]}}
    assert option_slot({"type": 3, "area": 2, "index": 0}, frame) == ("card", 1071)


@pytest.mark.req("REQ-TRAIN-0041")
def test_option_slot_is_byte_identical_without_a_frame():
    """Back-compat is what lets the three existing sweeps keep their meaning with no edit: with no
    frame the resolver is exactly the positional one it has always been, so a hand option falls back
    to `(area, index)` and a bare PLAY stays None."""
    assert option_slot({"type": 7, "index": 2}) is None
    assert option_slot({"type": 3, "area": 2, "index": 0}) == (2, 0)
    assert option_slot({"type": 14}) is None


@pytest.mark.req("REQ-TRAIN-0041")
def test_option_slot_prefers_the_board_slot_over_card_identity():
    """A BODY option keeps resolving to its board slot even when a frame is available — evolve,
    attach-from and promote all compare bodies, and re-pointing them at a card id would silently
    re-base three shipped sweeps and every committed Axis Claim (all of which name `(4, n)` /
    `(5, n)` board slots)."""
    frame = {"current": {"yourIndex": 0, "players": [{"hand": [{"id": 676}],
                                                      "bench": [{"id": 678}]}, {}]}}
    assert option_slot({"type": 9, "area": 5, "index": 0,
                        "inPlayArea": 5, "inPlayIndex": 0}, frame) == (5, 0)
    assert option_slot({"type": 3, "area": 4, "index": 2}, frame) == (4, 2)


@pytest.mark.req("REQ-TRAIN-0041")
def test_option_slot_falls_back_when_the_frame_cannot_resolve_the_card():
    """Fail-soft, never crash: an out-of-range index, a face-down (None) hand entry, or a frame
    without the asked seat leaves the positional answer rather than raising — a probe reads whatever
    the corpus recorded, including truncated frames."""
    frame = {"current": {"yourIndex": 0, "players": [{"hand": [None]}, {}]}}
    assert option_slot({"type": 7, "index": 9}, frame) is None       # out of range
    assert option_slot({"type": 7, "index": 0}, frame) is None       # face-down entry
    assert option_slot({"type": 3, "area": 2, "index": 9}, frame) == (2, 9)
    assert option_slot({"type": 7, "index": 0}, {"current": {}}) is None


@pytest.mark.req("REQ-TRAIN-0041")
def test_option_slot_reads_the_option_owner_not_always_the_asked_seat():
    """`playerIndex` names whose zone the option indexes. A deploy is always our own, but the
    resolver must not hardcode the asked seat or it would mis-resolve an opponent-owned card option
    the moment one enters a lane."""
    frame = {"current": {"yourIndex": 0,
                         "players": [{"hand": [{"id": 1}]}, {"hand": [{"id": 2}]}]}}
    assert option_slot({"type": 3, "area": 2, "index": 0, "playerIndex": 1}, frame) == ("card", 2)


@pytest.mark.req("REQ-TRAIN-0041")
def test_lane_slots_forwards_the_frame_so_a_deploy_lane_compares_cards():
    """`lane_slots` is what the sweeps and Axis Claims actually call, so the frame has to reach the
    resolver through it — otherwise the deploy lane would compare menu positions and two identical
    Solrock plays at different indices would read as different decisions."""
    options = [{"type": 7, "index": 0},                       # play Lillie's
               {"type": 7, "index": 2},                       # play Solrock
               {"type": 14}]                                  # end
    frame = {"current": {"yourIndex": 0,
                         "players": [{"hand": [{"id": 1227}, {"id": 1121}, {"id": 676}]}, {}]}}
    assert lane_slots([1], options, lane=gates.DEPLOY_LANE, select_context=0,
                      frame=frame) == {("card", 676)}
    assert lane_slots([0, 2], options, lane=gates.DEPLOY_LANE, select_context=0,
                      frame=frame) == {("card", 1227)}       # END is outside the lane


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


# ── claims — what a corpus fixture asserts (ADR-0072 decision 3) ──────────────────────────────────


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
    """The Held-out Ledger in one assertion (ADR-0072 decision 4): a re-ruling is a STATE the gate
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
    and belongs on the phase checklist (ADR-0072 decision 4)."""
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
                assert c.ruled, f"{p.name}: a held-out claim must record WHEN it was ruled"
                assert RULED_RE.match(c.ruled), f"{p.name}: ruled {c.ruled!r} is not YYYY-MM-DD"
                assert c.why, f"{p.name}: a held-out claim must record WHY"
        if fx.get("frame_key"):
            assert fx["frame_key"].count("|") == 3, f"{p.name}: frame_key is not an identity_key"


@pytest.mark.req("REQ-TRAIN-0044")
def test_the_held_out_ledger_is_populated_and_every_entry_names_a_live_owner():
    """The Ledger must not be inert. #167's Problem Statement names the exact defect it fixes —
    "nothing in code knows f32/f82 were re-ruled, and the sweep reads '0 REGRESSION' while the loss
    goes uncharged" — so a ruling that exists in prose but produces no Ledger entry has not been
    encoded. Each entry's frame_key was verified by an EXACT `select`-payload match to its source
    Correction."""
    ledger = gates.held_out_frames()
    assert ledger, "the Held-out Ledger is empty — re-rulings have not been encoded as data"
    assert "85046350|0|decision|32" in ledger and ledger["85046350|0|decision|32"] == "#165"   # f32
    assert "85785609|0|turn|8" in ledger and ledger["85785609|0|turn|8"] == "#165"             # f82
    assert "86091728|0|decision|2" in ledger and ledger["86091728|0|decision|2"] == "#161"     # f2
    for key, owner in ledger.items():
        assert key.count("|") == 3 and OWNER_RE.match(owner)


@pytest.mark.req("REQ-TRAIN-0043")
def test_decision_gate_fails_on_unruled_regression_frames_only():
    """The Decision Gate is ADR-0069 §8's sweep protocol promoted from convention to a gate. FIX and
    DIVERGENT verdicts do not block — only a REGRESSION the human has not ruled."""
    assert decision_gate_verdict([{"key": "a", "verdict": "FIX"}], held_out={}) is True
    assert decision_gate_verdict([{"key": "a", "verdict": "REGRESSION"}], held_out={}) is False
    assert decision_gate_verdict([{"key": "a", "verdict": "REGRESSION"}],
                                 held_out={"a": "#165"}) is True

# ── Claim Agreement — a fixture's ruling must match its Correction's (ADR-0082) ────────────────────
#
# ADR-0072 made a re-ruling a STATE the instruments read, but only for the fixtures that adopted its
# `claims` block. The two generations were measured (ADR-0082) as perfectly disjoint: 34 fixtures
# carried a loose `episode`+`frame` pair and ZERO `claims`; 8 carried a `frame_key` and ALL 8 had
# `claims`. Every re-ruling captured in a `claims` block survived; the two that were lost were in the
# generation with nowhere to record one. This gate is the invariant that makes losing one loud.

#: Fixtures that carry an ``episode``+``frame`` pair but deliberately assert **no pick**, so there is
#: nothing for Claim Agreement to compare. Both are REFUTED Corrections (reviewed.json, human ack
#: 2026-07-09): their `agent_choice`/`human_wanted` field names are not an older schema for
#: `chosen`/`correct` — they INVERT it. `test_blunder_20260709` asserts the agent matches
#: `agent_choice` and differs from `human_wanted`, so renaming the latter to `correct` would assert
#: that a refuted pick is right. ADR-0082's build-shape note to normalise them was withdrawn on
#: reading the consumer.
ASSERTS_NO_PICK = {"ms0705_bosss_over_harlequin_f78.json", "ms0705_gust_cinderace_only_ko_f79.json"}


def _corpus_fixtures():
    """The committed corpus fixture directory — the real one the gate defaults to."""
    from pathlib import Path
    return Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "corrections"


def _corr(tmp_path, *, episode=1, seat=0, frame=5, correct=(1,), obs=None, scope="decision"):
    """One committed Correction on disk, minimal but real enough for `Correction.from_dict`."""
    import json
    rec = {"id": f"c{episode}{frame}", "source": "own", "episode_id": episode, "seat": seat,
           "agent": "mega_starmie", "submission_id": None, "agent_version": None,
           "episode_time": None, "tagged_at": "2026-01-01T00:00:00+00:00",
           "decision": {"frame": frame, "turn": 3}, "chosen": [0], "chosen_label": "x",
           "correct": list(correct), "correct_label": "y", "category": "wasted_resource",
           "attribution": None, "rationale": "r", "scope": scope,
           "obs": obs if obs is not None else {"current": {"turn": 3}}}
    store = tmp_path / "corrections" / "agent_20260101_abc"
    store.mkdir(parents=True, exist_ok=True)
    with (store / "corrections.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    return tmp_path / "corrections"


def _fixture_file(tmp_path, name, payload):
    """One committed-looking fixture on disk. Returns the directory, so several may share it."""
    import json
    d = tmp_path / "fixtures"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")
    return d


@pytest.mark.req("REQ-TRAIN-0045")
def test_a_fixture_agreeing_with_its_correction_raises_nothing(tmp_path):
    """The green case. Same `correct`, same obs — nothing to report."""
    store = _corr(tmp_path, correct=(1,))
    fx = _fixture_file(tmp_path, "ok", {"frame_key": "1|0|decision|5",
                                        "claims": {"decision": {"correct": [1]}},
                                        "obs": {"current": {"turn": 3}}})
    assert gates.claim_agreement(fixtures_dir=fx, store=store) == []


@pytest.mark.req("REQ-TRAIN-0045")
def test_an_undeclared_disagreement_is_reported(tmp_path):
    """The defect the gate exists for: the fixture asserts one pick, the corpus records another, and
    nothing on the fixture says why. This is `ms_doom_relax_bare_terapagos_f29` in miniature."""
    store = _corr(tmp_path, correct=(10,))
    fx = _fixture_file(tmp_path, "stale", {"frame_key": "1|0|decision|5",
                                           "claims": {"decision": {"correct": [2]}},
                                           "obs": {"current": {"turn": 3}}})
    found = gates.claim_agreement(fixtures_dir=fx, store=store)
    assert [f["kind"] for f in found] == ["disagreement"]
    assert found[0]["claim"] == [2] and found[0]["record"] == [10]
    assert found[0]["fixture"] == "stale.json"


@pytest.mark.req("REQ-TRAIN-0045")
def test_an_owner_declares_the_divergence_and_clears_it(tmp_path):
    """Escape 1 — a **Held-out Frame**. `dragapult_hammer_over_develop_f32` is the live instance: its
    Decision Claim is `[3]` against a recorded `[1]`, ruled onto Issue #165 on 2026-07-25. Deleting the
    owner returns it to gating, exactly as ADR-0072 decision 4 specifies."""
    store = _corr(tmp_path, correct=(1,))
    payload = {"frame_key": "1|0|decision|5", "obs": {"current": {"turn": 3}},
               "claims": {"decision": {"correct": [3], "owner": "#165", "ruled": "2026-07-25",
                                       "why": "re-ruled to the Turn Planner"}}}
    fx = _fixture_file(tmp_path, "heldout", payload)
    assert gates.claim_agreement(fixtures_dir=fx, store=store) == []

    del payload["claims"]["decision"]["owner"]                     # ... but `ruled`+`why` remain
    fx = _fixture_file(tmp_path, "heldout", payload)
    assert gates.claim_agreement(fixtures_dir=fx, store=store) == []   # escape 2 still covers it

    payload["claims"]["decision"] = {"correct": [3]}               # strip BOTH declarations
    fx = _fixture_file(tmp_path, "heldout", payload)
    assert [f["kind"] for f in gates.claim_agreement(fixtures_dir=fx, store=store)] == ["disagreement"]


@pytest.mark.req("REQ-TRAIN-0045")
def test_a_dated_why_declares_a_re_ruling_recorded_on_the_fixture(tmp_path):
    """Escape 2 — a re-ruling the fixture records itself, with a date and a reason but no owner (it is
    not held out of anything; it simply departs). `dp_hold_evolve_until_typed_ready_f35` is the shape."""
    store = _corr(tmp_path, correct=(1,))
    fx = _fixture_file(tmp_path, "reruled", {"frame_key": "1|0|decision|5", "obs": {"current": {"turn": 3}},
                                             "claims": {"decision": {"correct": [3], "ruled": "2026-07-26",
                                                                     "why": "RE-RULED: Poke Pad first"}}})
    assert gates.claim_agreement(fixtures_dir=fx, store=store) == []


@pytest.mark.req("REQ-TRAIN-0045")
@pytest.mark.parametrize("ruled", [None, "soon", "2026-7-26", "26-07-2026", "", True, 20260726])
def test_an_undated_or_malformed_why_does_not_clear_a_disagreement(tmp_path, ruled):
    """The escape must be auditable against the record ON A DATE, so `ruled` owes `RULED_RE`'s
    ``YYYY-MM-DD`` — the same shape a held-out claim already owes. Without this, `"ruled": "soon"`
    silently disarms the gate for that fixture forever, which is the failure mode the gate exists to
    prevent wearing a different hat.

    `True` and a bare number are in here because a hand-edited fixture is exactly where that typo
    appears, and they must be REJECTED rather than raise — a gate that crashes on malformed input is a
    gate that gets skipped rather than fixed."""
    store = _corr(tmp_path, correct=(1,))
    dec = {"correct": [3], "why": "departs, but unauditably"}
    if ruled is not None:
        dec["ruled"] = ruled
    fx = _fixture_file(tmp_path, "undated", {"frame_key": "1|0|decision|5",
                                             "obs": {"current": {"turn": 3}},
                                             "claims": {"decision": dec}})
    assert [f["kind"] for f in gates.claim_agreement(fixtures_dir=fx, store=store)] == ["disagreement"]


@pytest.mark.req("REQ-TRAIN-0045")
def test_a_frame_key_naming_no_committed_correction_is_reported(tmp_path):
    """A dangling join — a typo'd key, or a record that left the corpus. Silent here would defeat the
    whole gate: an unresolvable key reads exactly like a fixture with nothing to disagree with."""
    store = _corr(tmp_path, episode=1, frame=5)
    fx = _fixture_file(tmp_path, "dangling", {"frame_key": "1|0|decision|999",
                                              "claims": {"decision": {"correct": [1]}},
                                              "obs": {"current": {"turn": 3}}})
    assert [f["kind"] for f in gates.claim_agreement(fixtures_dir=fx, store=store)] == ["no_record"]


@pytest.mark.req("REQ-TRAIN-0045")
def test_the_adr_0050_reseeding_keys_are_not_an_obs_mismatch(tmp_path):
    """Five committed fixtures carry `own_prizes` + `search_begin_input` their Correction's snapshot
    does not — the ADR-0050 seeding that lets the offline sim replay them (reviewed.json's 2026-07-13
    entry for 84071010-15 says why: "so the tracker anchors and deck_definitely_has(Air Balloon)=True").
    That changes HOW a fixture replays, never WHAT the human ruled, so a byte-compare would report five
    phantom divergences."""
    store = _corr(tmp_path, obs={"current": {"turn": 3}})
    fx = _fixture_file(tmp_path, "seeded", {"frame_key": "1|0|decision|5",
                                            "claims": {"decision": {"correct": [1]}},
                                            "obs": {"current": {"turn": 3}, "own_prizes": 4,
                                                    "search_begin_input": {"seed": 7}}})
    assert gates.claim_agreement(fixtures_dir=fx, store=store) == []


@pytest.mark.req("REQ-TRAIN-0045")
def test_an_obs_mismatch_beyond_the_seeding_keys_is_reported_because_indices_stop_comparing(tmp_path):
    """`correct` is a list of positional option indices, so comparing it across two different boards is
    meaningless. A fixture whose board has moved must be reported rather than compared — and reported
    even when it declares an escape, because a declared re-ruling excuses a different RULING, never an
    unsound JOIN."""
    store = _corr(tmp_path, obs={"current": {"turn": 3}})
    fx = _fixture_file(tmp_path, "drifted", {"frame_key": "1|0|decision|5",
                                             "claims": {"decision": {"correct": [1]}},
                                             "obs": {"current": {"turn": 9}}})
    assert [f["kind"] for f in gates.claim_agreement(fixtures_dir=fx, store=store)] == ["obs_mismatch"]

    fx = _fixture_file(tmp_path, "drifted", {"frame_key": "1|0|decision|5",
                                             "obs": {"current": {"turn": 9}},
                                             "claims": {"decision": {"correct": [1], "owner": "#165",
                                                                     "ruled": "2026-07-25",
                                                                     "why": "held out"}}})
    assert [f["kind"] for f in gates.claim_agreement(fixtures_dir=fx, store=store)] == ["obs_mismatch"]


@pytest.mark.req("REQ-TRAIN-0045")
def test_two_fixtures_on_one_frame_key_are_judged_independently(tmp_path):
    """Legal and load-bearing (ADR-0082): `86091435-35` and `85164605-41` each carry TWO fixtures —
    a doom shadow beside a re-ruled pick, a planner commitment beside a held-out indifference. So the
    gate must not assume one fixture per frame, and one bad sibling must not exonerate the other."""
    store = _corr(tmp_path, correct=(1,))
    d = _fixture_file(tmp_path, "sibling_ok", {"frame_key": "1|0|decision|5",
                                               "claims": {"decision": {"correct": [1]}},
                                               "obs": {"current": {"turn": 3}}})
    _fixture_file(tmp_path, "sibling_stale", {"frame_key": "1|0|decision|5",
                                              "claims": {"decision": {"correct": [7]}},
                                              "obs": {"current": {"turn": 3}}})
    found = gates.claim_agreement(fixtures_dir=d, store=store)
    assert [(f["fixture"], f["kind"]) for f in found] == [("sibling_stale.json", "disagreement")]


@pytest.mark.req("REQ-TRAIN-0045")
def test_a_fixture_without_a_frame_key_is_skipped_so_the_back_fill_stays_incremental(tmp_path):
    """`parse_claims`'s back-compat promise, upheld at the gate: declaring a `frame_key` is what opts a
    fixture in. Without it there is no join, and inventing one from a loose `episode`+`frame` pair
    would be guessing at ADR-0049's identity."""
    store = _corr(tmp_path, correct=(1,))
    fx = _fixture_file(tmp_path, "unkeyed", {"episode": 1, "frame": 5, "correct": [2],
                                             "obs": {"current": {"turn": 3}}})
    assert gates.claim_agreement(fixtures_dir=fx, store=store) == []


@pytest.mark.req("REQ-TRAIN-0045")
def test_both_corpus_readers_share_one_walk(tmp_path):
    """`iter_keyed_fixtures` is THE corpus walk, for the reason `frame_key_of` is the single place the
    key shape is built: a second glob that drifted by a field would silently stop seeing frames. Both
    readers must go through it, so a fixture invisible to one is invisible to the other."""
    d = _fixture_file(tmp_path, "keyed", {"frame_key": "1|0|decision|5",
                                          "claims": {"decision": {"correct": [1], "owner": "#165",
                                                                  "ruled": "2026-07-25", "why": "w"}},
                                          "obs": {"current": {"turn": 3}}})
    _fixture_file(tmp_path, "unkeyed", {"episode": 1, "frame": 5, "correct": [1],
                                        "obs": {"current": {"turn": 3}}})
    walked = [p.name for p, _fx, _k, _c in gates.iter_keyed_fixtures(d)]
    assert walked == ["keyed.json"]
    assert gates.held_out_frames(fixtures_dir=d) == {"1|0|decision|5": "#165"}


@pytest.mark.req("REQ-TRAIN-0045")
def test_the_committed_corpus_has_no_undeclared_disagreement():
    """The live invariant, over the real corpus — the reason the gate exists rather than the proof it
    parses. Any fixture that departs from its Correction must SAY SO, with an owner or a dated why."""
    found = gates.claim_agreement()
    assert found == [], "undeclared fixture/record disagreements: " + "; ".join(
        f"{f['fixture']} {f['kind']} claim={f.get('claim')} record={f.get('record')}" for f in found)


@pytest.mark.req("REQ-TRAIN-0045")
def test_a_fixtures_top_level_correct_agrees_with_its_explicit_decision_claim():
    """The loophole the ADR-0082 back-fill would otherwise open. `parse_claims` PREFERS an explicit
    `claims` block, but 33 test modules still read `fx["correct"]` directly — so a fixture carrying
    both must keep them identical, or the gate would check one value while the tests assert the other.
    Keeping both in sync (rather than deleting `correct`) is what makes the back-fill non-breaking;
    this is the invariant that makes it safe."""
    import json
    for p in sorted(_corpus_fixtures().glob("*.json")):
        fx = json.loads(p.read_text(encoding="utf-8"))
        dec = (fx.get("claims") or {}).get("decision")
        if dec is None or fx.get("correct") is None:
            continue
        claimed = dec if isinstance(dec, list) else dec.get("correct")
        if claimed is None:
            continue
        assert sorted(claimed) == sorted(fx["correct"]), (
            f"{p.name}: claims.decision.correct {claimed} != top-level correct {fx['correct']}")


@pytest.mark.req("REQ-TRAIN-0045")
def test_every_record_backed_fixture_declares_a_frame_key():
    """ADR-0082 decision 1's completeness invariant. `claim_agreement` opts in on `frame_key`, so a
    fixture that has a joinable identity and omits one is silently ungated — which is exactly how the
    two lost re-rulings stayed lost. A NEW fixture added the old way fails here rather than quietly
    reducing coverage."""
    import json
    loose = []
    for p in sorted(_corpus_fixtures().glob("*.json")):
        fx = json.loads(p.read_text(encoding="utf-8"))
        if fx.get("frame_key") or p.name in ASSERTS_NO_PICK:
            continue
        if fx.get("episode") is not None and fx.get("frame") is not None:
            loose.append(p.name)
    assert loose == [], (
        "these fixtures can be joined to a Correction but declare no frame_key, so Claim Agreement "
        f"skips them: {loose}")


@pytest.mark.req("REQ-TRAIN-0045")
def test_the_two_pick_less_fixtures_really_do_assert_no_pick():
    """The exclusion above must stay honest: if either fixture ever gains a `correct`, it becomes
    gateable and the exemption is stale. Asserts the inversion too — `human_wanted` is the REFUTED
    ask, never the ruling."""
    import json
    for name in sorted(ASSERTS_NO_PICK):
        fx = json.loads((_corpus_fixtures() / name).read_text(encoding="utf-8"))
        assert fx.get("correct") is None, f"{name} gained a `correct` — it is gateable now"
        assert "agent_choice" in fx and "human_wanted" in fx, f"{name} lost the refutation shape"
        assert parse_claims(fx).decision is None, f"{name} must synthesise no Decision Claim"


# ───────────────────────────────────────────── the Decision Gate's recorded baseline (ADR-0085 I)

def _drow(key, chosen, correct, context=15, agent="mega_starmie"):
    return {"key": key, "chosen": chosen, "correct": correct, "context": context, "agent": agent}


def _dcap(rows):
    return {"git_rev": "test", "rows": rows}


def test_decider_lab_diff_reports_nothing_when_the_build_is_unchanged():
    """The self-diff. A gate whose reference is a recorded capture must be silent against itself, or
    every run manufactures work."""
    rows = [_drow("a", [0], [0]), _drow("b", [1], [2])]
    assert decider_lab_diff(_dcap(rows), _dcap(rows))["rows"] == []


def test_decider_lab_diff_CAN_report_a_regression():
    """**The property Amendment I exists to restore**, asserted directly.

    The sweeps this replaces compared against a live kill-switch-OFF arm. Once each phase deleted its
    rung pile, OFF became an empty scorer and the comparison could only ever produce FIX — measured
    on the real corpus: `evolve_decider_sweep` reported `4 FIX, 0 REGRESSION` and
    `snipe_decider_sweep` `12 FIX, 0 REGRESSION`, with no regression detectable by construction.
    Asserting the four verdict directions here is what stops that from recurring silently."""
    before = _dcap([_drow("regress", [0], [0]), _drow("fix", [9], [1]),
                    _drow("neutral", [7], [1]), _drow("unlabelled", [0], None)])
    after = _dcap([_drow("regress", [3], [0]), _drow("fix", [1], [1]),
                   _drow("neutral", [8], [1]), _drow("unlabelled", [4], None)])
    got = {r["key"]: r["verdict"] for r in decider_lab_diff(before, after)["rows"]}
    assert got == {"regress": "REGRESSION", "fix": "FIX",
                   "neutral": "NEUTRAL", "unlabelled": "UNLABELLED"}


def test_decider_lab_regression_gates_unless_it_is_ruled():
    """The Held-out Ledger reaches this gate too — one ruling must hold a frame out of BOTH gates,
    which is why the key is built by `frame_key_of` on either side."""
    before, after = _dcap([_drow("k", [0], [0])]), _dcap([_drow("k", [1], [0])])
    rows = decider_lab_diff(before, after)["rows"]
    assert decision_gate_verdict(rows, held_out={}) is False
    assert decision_gate_verdict(rows, held_out={"k": "#165"}) is True


def test_decider_lab_diff_surfaces_a_moved_corpus_rather_than_shrinking_the_gated_set():
    """A baseline captured against a different corpus shape must be VISIBLE. Silently comparing only
    the intersection is how a gate quietly stops covering what it claims to."""
    d = decider_lab_diff(_dcap([_drow("a", [0], [0]), _drow("gone", [0], [0])]),
                         _dcap([_drow("a", [0], [0]), _drow("new", [0], [0])]))
    assert d["added"] == ["new"] and d["removed"] == ["gone"] and d["compared"] == 1


def test_decider_lab_diff_compares_a_multi_pick_as_a_set_not_a_sequence():
    """A reordered multi-pick is NOT a regression.

    `DISCARD` (SelectContext 8) asks for N cards and the agent returns all of them; the engine
    applies the set, so their order carries no decision. Comparing sequences would report
    `[0, 2] -> [2, 0]` as a REGRESSION — a false positive in the one direction a gate must never
    produce, since it is the direction that blocks a merge.

    Found while writing the hand-off, by reading the captured `DISCARD` rows rather than trusting
    the aggregate: the agent picks `[2, 3]` where `correct` records `[2]`, because a Correction's
    `correct` names the card the RULING was about, not the whole legal answer. Amendment J rules that
    mismatch (`satisfies_human`, below); this test covers the movement half, which gates either way.
    """
    before = _dcap([_drow("k", [0, 2], [0, 2], context=8)])
    after = _dcap([_drow("k", [2, 0], [0, 2], context=8)])
    assert decider_lab_diff(before, after)["rows"] == [], "order is not a decision"
    # a genuine change to the SET is still caught
    moved = _dcap([_drow("k", [2, 4], [0, 2], context=8)])
    assert [r["verdict"] for r in decider_lab_diff(before, moved)["rows"]] == ["REGRESSION"]


# ── `satisfies_human` — a Correction's `correct` is a CONSTRAINT, not the answer (ADR-0085 J) ─────

def test_a_multi_pick_satisfies_a_ruling_it_is_a_superset_of():
    """**The Amendment J ruling.** `correct` names the card the ruling was ABOUT; a multi-pick select
    returns every index the engine demands. Equality across those two vocabularies mis-reports, and
    measurably did: `DISCARD` read **1/12** on the capture purely because the agent picks `[2, 3]`
    where the ruling says `[2]`. Under `⊆` the same corpus reads **10/12** — the ten were vocabulary
    artifacts, not defects, and the gate was defending them as if they were losses."""
    assert satisfies_human([2, 3], [2]) is True
    assert satisfies_human([3, 4], [2]) is False, "the ruled card was NOT discarded"
    assert satisfies_human([2], [2, 3]) is False, "a partial answer does not satisfy a two-card ruling"


def test_satisfaction_degenerates_to_equality_on_a_single_pick():
    """Why the 220 single-pick agreements are untouched by the ruling: with one index a side, `⊆`
    and `==` are the same test. The change buys the multi-pick contexts and costs nothing elsewhere."""
    assert satisfies_human([1], [1]) is True
    assert satisfies_human([0], [1]) is False


def test_an_empty_correct_is_a_DECLINE_ruling_and_needs_an_empty_pick():
    """The guard that makes `⊆` safe to use at all.

    The empty set is a subset of everything, so reading `correct: []` through `⊆` would make EVERY
    frame vacuously agree — a gate-shaped hole rather than a rounding error. But `correct: []` is not
    absent, it is a recorded **DECLINE** ("take none of these"), and eleven such frames sit in the
    corpus today with `86088989|0|decision|3` genuinely satisfying one. So it is exact, not subset:
    a DECLINE stays a labelled, gated ruling instead of being either discarded or auto-passed."""
    assert satisfies_human([], []) is True
    assert satisfies_human([0], []) is False, "picking something does not satisfy a DECLINE"


def test_an_absent_ruling_and_an_unreplayable_frame_satisfy_nothing():
    """`correct is None` claims no direction (callers report UNLABELLED); `chosen is None` is a frame
    this build could not replay at all. Neither may read as agreement — an unreplayable frame
    silently counting as agreement is how a shrinking gated set looks green."""
    assert satisfies_human([0], None) is False
    assert satisfies_human(None, [0]) is False
    assert satisfies_human(None, None) is False


def test_the_diff_judges_direction_through_the_same_predicate_as_the_agree_rate():
    """The gate and the readout must not hold two ideas of "matches the human".

    Under equality this frame is invisible: the baseline `[2, 3]` and the build `[3, 4]` both differ
    from `correct: [2]`, so the move classifies NEUTRAL and passes. Under satisfaction the baseline
    discarded the ruled card and the build stopped, which is precisely a REGRESSION — so the shared
    predicate makes the gate STRICTLY more sensitive on multi-pick contexts, never less."""
    before = _dcap([_drow("k", [2, 3], [2], context=8)])
    after = _dcap([_drow("k", [3, 4], [2], context=8)])
    assert [r["verdict"] for r in decider_lab_diff(before, after)["rows"]] == ["REGRESSION"]
    # ...and the reverse move is the FIX it looks like
    assert [r["verdict"] for r in decider_lab_diff(after, before)["rows"]] == ["FIX"]


def test_a_move_the_ruling_does_not_separate_is_NEUTRAL_in_both_directions():
    """NEUTRAL covers both-miss AND both-satisfy. `[2, 3] -> [2, 5]` against `correct: [2]` is a real
    change the corpus simply does not adjudicate — the ruled card is discarded either way, and the
    other slot is the engine's, never the human's. Calling that a REGRESSION would gate on a
    preference no one recorded."""
    before = _dcap([_drow("k", [2, 3], [2], context=8)])
    after = _dcap([_drow("k", [2, 5], [2], context=8)])
    assert [r["verdict"] for r in decider_lab_diff(before, after)["rows"]] == ["NEUTRAL"]


# ── the Corpus Reader — ONE reader, ONE key (ADR-0087, Issue #241) ────────────────────────────
#
# The defect these tests assert against, measured 2026-07-31 on the committed corpus:
#
#     raw records                                   372
#     the Decision Gate's private walk saw          332      (-40, every one recoverable)
#     keys it named CORRECTLY                       169      (45% — `seat` was ALWAYS 0)
#     Held-out Ledger rulings it could reach        7 of 11
#
# Two shortcuts caused all of it, and they are the same shortcut: a raw-JSONL walk is a second idea
# of what a record IS, and a hand-built key is a second idea of what a frame is CALLED. The second
# drifts undetectably, because both sides of a diff share the same wrong key — so a self-consistent
# diff over a wrong keyspace still reports flips and nothing ever goes red.





@pytest.mark.req("REQ-GATE-0007")
def test_the_corpus_reader_returns_the_stores_replayable_set(tmp_path):
    """`keyed_corrections` IS the corpus, and the expectation is derived independently — the raw file
    walked in the test itself through `Correction.from_dict`, never by calling the thing under test.

    Set equality, not a count. The issue's own acceptance proposed a count assertion; a count passes
    happily on 332 mis-keyed rows, so it would have caught only the smaller half of this bug."""
    from train.blunder.correction import Correction, identity_key
    recs = [_rec(1, 3), _rec(1, 9, seat=1), _rec(2, 4, scope="turn", subject=2),
            _rec(3, 5, obs=False)]
    root = _store(tmp_path, recs)

    got = {k for k, _c in gates.keyed_corrections(root, predicate=lambda c: c.obs and c.agent)}
    want = {gates.frame_key_of(*identity_key(Correction.from_dict(r)))
            for r in recs if r["obs"] and r["agent"]}
    assert got == want
    assert len(got) == 3                       # the obs-less record is the only one excluded


@pytest.mark.req("REQ-GATE-0007")
def test_a_record_with_an_empty_agent_and_a_build_stem_is_recovered(tmp_path):
    """**The reported bug, in one assertion.** 40 records carry ``agent: ""`` with a populated
    ``agent_build``; ``Correction.from_dict`` backfills the deck from the stem, but only for a reader
    that CONSTRUCTS a Correction. A raw walk sees a falsy ``agent`` and drops the record before a row
    exists — so it lands in neither capture and ``added``/``removed`` can never surface it.

    An empty ``agent`` is a RECOVERABLE field, not a missing one."""
    root = _store(tmp_path, [_rec(1, 3, agent="", agent_build="mega_starmie_20260627_93a70be")],
                  build="mega_starmie_20260627_93a70be")
    got = gates.keyed_corrections(root, predicate=lambda c: c.obs and c.agent)
    assert [c.agent for _k, c in got] == ["mega_starmie"]


@pytest.mark.req("REQ-GATE-0007")
def test_the_reader_keys_by_identity_not_by_the_anchor_frame(tmp_path):
    """``seat`` is top-level and the Scope's SUBJECT is the identity (ADR-0049) — not seat 0, and not
    the Anchor frame. The Decision Gate read ``decision.get("seat", 0)`` against a snapshot with no
    ``seat`` field, so every key it ever built said seat 0 over a corpus that is 201/171."""
    root = _store(tmp_path, [_rec(7, 51, seat=1), _rec(8, 82, seat=0, scope="turn", subject=8)])
    keys = {k for k, _c in gates.keyed_corrections(root)}
    assert keys == {"7|1|decision|51", "8|0|turn|8"}


@pytest.mark.req("REQ-GATE-0007")
def test_both_gates_key_a_frame_identically(tmp_path):
    """ADR-0072 decision 4 — *one ruling holds a frame out of BOTH gates* — as an executable
    assertion rather than a docstring claim.

    It was FALSE for 4 of 11 committed rulings: three seat-1 keys against a keyspace that was
    entirely seat-0, and one ``turn``-scope key the Decision Gate filed as ``decision``. A held-out
    frame that regressed would have failed `main` against a standing human ruling."""
    from train.leaf_lab import frame_key
    root = _store(tmp_path, [_rec(7, 51, seat=1), _rec(8, 82, seat=0, scope="turn", subject=8)])
    for key, c in gates.keyed_corrections(root):
        assert key == frame_key(c)


@pytest.mark.req("REQ-GATE-0007")
def test_two_corrections_sharing_a_key_both_survive_the_reader(tmp_path):
    """Pairs, not a dict — asserted against a future "simplification".

    A dict silently collapses two Corrections on one key. Today that is measurably zero, but
    ``load_corrections`` deliberately KEEPS conflicts (same identity, different ``correct``/
    ``category`` — what ``find_conflicts`` exists to surface), and a reader that drops one is
    committing this issue's own defect at the seam built to remove it."""
    root = _store(tmp_path, [_rec(1, 3, correct=[1], category="wasted_resource"),
                             _rec(1, 3, correct=[2], category="sequencing_error")])
    got = gates.keyed_corrections(root)
    assert [k for k, _c in got] == ["1|0|decision|3", "1|0|decision|3"]
    assert sorted(tuple(c.correct) for _k, c in got) == [(1,), (2,)]


@pytest.mark.req("REQ-GATE-0007")
def test_every_held_out_ruling_names_a_frame_the_committed_store_carries():
    """The detachment guard, over the REAL corpus. Deliberately NOT ``baseline keys == store keys``:
    corrections are tagged continuously and re-capture is a deliberate human act, so strict equality
    would redden `main` on every new tag and apply exactly the pressure toward auto-recapture that
    `decider-gate-main.yml` argues at length against."""
    keys = {k for k, _c in gates.keyed_corrections()}
    missing = sorted(k for k in gates.held_out_frames() if k not in keys)
    assert missing == []


# ── Ruling Moves — the channel for a corpus whose RULING moved (ADR-0087 decision 7) ──────────


@pytest.mark.req("REQ-GATE-0008")
def test_a_moved_ruling_is_reported_even_when_the_agents_pick_did_not_move():
    """**The blindness, asserted directly.** Both diffs emit a row only when the agent's pick moves, so a frame
    the agent plays identically whose ``correct`` was re-ruled produces NO row at all — while its
    verdict silently flips from unsatisfied to satisfied.

    Measured on the real corpus: ``85709280`` went ``[] -> [0]`` in ``b6d7483`` (ADR-0081 Amendment D)
    and moved the agree rate 230 -> 231 with no decision changed. ``added``/``removed`` cannot see it
    either, because the frame exists on both sides."""
    before = _dcap([_drow("k", [0], [])])
    after = _dcap([_drow("k", [0], [0])])
    d = decider_lab_diff(before, after)
    assert d["rows"] == []                                   # the pick did not move — no verdict row
    assert d["added"] == [] and d["removed"] == []           # and the frame is on both sides
    assert d["ruling_moves"] == [{"key": "k", "before": [], "after": [0]}]


@pytest.mark.req("REQ-GATE-0008")
def test_an_unmoved_ruling_is_not_reported_however_the_pick_moves():
    before = _dcap([_drow("a", [0], [0]), _drow("b", [1], [2])])
    after = _dcap([_drow("a", [3], [0]), _drow("b", [1], [2])])
    assert decider_lab_diff(before, after)["ruling_moves"] == []


@pytest.mark.req("REQ-GATE-0008")
def test_a_ruling_move_never_gates_either_gate():
    """A re-ruling is a deliberate human act, not an agent regression. It is reported beside
    ``added``/``removed`` and blocks nothing — the same treatment ``FIX`` gets."""
    before, after = _dcap([_drow("k", [0], [])]), _dcap([_drow("k", [0], [0])])
    d = decider_lab_diff(before, after)
    assert d["ruling_moves"] and decision_gate_verdict(d["rows"], held_out={}) is True

    lb = _report([{**_row("k", "OK"), "correct": [1]}])
    la = _report([{**_row("k", "OK"), "correct": [2]}])
    ld = leaf_lab_diff(lb, la)
    assert ld["ruling_moves"] and discrimination_gate_verdict(ld, held_out={}) is True


@pytest.mark.req("REQ-GATE-0008")
def test_the_leaf_diff_reports_a_moved_ruling_too():
    """``leaf_lab_diff`` compares ``correct_is_top``, which is computed FROM ``correct`` — so it
    carries the identical blindness. Shared implementation for ``frame_key_of``'s reason: a second
    one would drift."""
    before = _report([{**_row("k", "OK"), "correct": [1]}])
    after = _report([{**_row("k", "OK"), "correct": [1, 2]}])
    assert leaf_lab_diff(before, after)["ruling_moves"] == [{"key": "k", "before": [1],
                                                             "after": [1, 2]}]


@pytest.mark.req("REQ-GATE-0008")
def test_a_ruling_move_is_pick_set_normalised_not_order_sensitive():
    """``correct`` is a SET of option indices; re-ordering it is not a re-ruling. Same normalisation
    the verdict test uses, so the two cannot drift into different ideas of "the ruling changed"."""
    before, after = _dcap([_drow("k", [0], [2, 3])]), _dcap([_drow("k", [0], [3, 2])])
    assert decider_lab_diff(before, after)["ruling_moves"] == []


@pytest.mark.req("REQ-GATE-0008")
def test_a_frame_on_only_one_side_is_not_a_ruling_move():
    """``added``/``removed`` already own that case. Reporting it twice would double-count a
    corpus-shape change as a re-ruling — the widening this issue lands adds 40 frames, and every one
    of them has no ``before`` ruling to have moved from."""
    before, after = _dcap([_drow("a", [0], [0])]), _dcap([_drow("b", [0], [1])])
    d = decider_lab_diff(before, after)
    assert d["ruling_moves"] == [] and d["added"] == ["b"] and d["removed"] == ["a"]


@pytest.mark.req("REQ-GATE-0010")
def test_a_gate_artifact_is_written_LF_framed_not_the_platforms_newline(tmp_path):
    """Both committed baselines are LF, dev is Windows and the grader is Linux (CLAUDE.md).

    ``Path.write_text`` rewrites every newline to CRLF on Windows, which is how a 40-row re-capture
    became a 4835-line whole-file rewrite — burying the one thing a reviewer of a re-capture needs to
    see. Both labs wrote their captures that way; `write_json_artifact` is the single writer, so the
    framing is CHOSEN rather than inherited from whichever platform ran the capture."""
    out = tmp_path / "nested" / "artifact.json"
    doc = {"rows": [{"key": "1|0|decision|3"}]}
    gates.write_json_artifact(out, doc)
    raw = out.read_bytes()
    assert CRLF not in raw
    assert raw == json.dumps(doc, indent=2).encode("utf-8")     # exact framing, no trailing newline


@pytest.mark.req("REQ-GATE-0010")
def test_the_committed_baselines_are_LF_framed():
    """The artifacts themselves, asserted — a writer fixed in code but a file left CRLF on disk would
    still show every future re-capture as a whole-file diff, which is the harm."""
    root = Path(__file__).resolve().parents[2] / "data"
    for rel in ("decider_lab/baseline.json", "leaf_lab/baseline.json"):
        assert CRLF not in (root / rel).read_bytes(), rel


# ── the capture must be reproducible on any box ───────────────────────────────────────────────────


@pytest.mark.req("REQ-GATE-0011")
def test_an_unreplayable_frames_error_carries_no_machine_specific_path():
    """The baseline is a COMMITTED ruling record, so nothing it embeds may depend on who ran the
    capture. It was embedding an absolute path — ``/home/user/PokemonAI/...`` from the Linux capture
    and ``C:\\Users\\...`` from a Windows one — so the same build re-captured elsewhere produced a
    different artifact for a frame whose verdict had not moved. Dev is Windows and the grader is
    Linux (CLAUDE.md), so that is the normal case, not an edge one.

    The slash normalisation has to happen BEFORE the root is stripped: an exception's ``str`` carries
    the path already repr-escaped, so matching the raw root silently fails on Windows — the shape
    that let this survive."""
    from train.decider_lab import REPO, _portable_error
    try:
        raise FileNotFoundError(2, "No such file or directory",
                                str(REPO / "src" / "agents" / "SkiChu" / "strategy.py"))
    except OSError as exc:
        got = _portable_error(exc)
    assert str(REPO) not in got
    assert str(REPO).replace("\\", "/") not in got
    assert got.startswith("FileNotFoundError:")
    assert "src/agents/SkiChu/strategy.py" in got      # the diagnostic survives


@pytest.mark.req("REQ-GATE-0011")
def test_the_committed_capture_embeds_no_absolute_path():
    """The artifact itself. A normaliser in code cannot help a file captured before it existed."""
    root = Path(__file__).resolve().parents[2] / "data" / "decider_lab" / "baseline.json"
    text = root.read_text(encoding="utf-8")
    for probe in ("/home/", "C:/Users", "C:\\\\Users"):
        assert probe not in text, probe


@pytest.mark.req("REQ-GATE-0008")
def test_a_frame_gaining_or_losing_a_ruling_counts_as_a_moved_ruling():
    """``None -> [x]`` is a frame becoming gateable, and ``[x] -> None`` a frame ceasing to be. Both
    change what the corpus can adjudicate there, so both are reported — an `UNLABELLED` frame turning
    into a gated one is exactly as worth knowing as a ruling being rewritten, and neither shows up in
    `added`/`removed` because the frame is on both sides throughout."""
    gained = decider_lab_diff(_dcap([_drow("k", [0], None)]), _dcap([_drow("k", [0], [1])]))
    assert gained["ruling_moves"] == [{"key": "k", "before": None, "after": [1]}]
    lost = decider_lab_diff(_dcap([_drow("k", [0], [1])]), _dcap([_drow("k", [0], None)]))
    assert lost["ruling_moves"] == [{"key": "k", "before": [1], "after": None}]
    # ...and a frame that never carried a ruling on either side has not moved.
    never = decider_lab_diff(_dcap([_drow("k", [0], None)]), _dcap([_drow("k", [1], None)]))
    assert never["ruling_moves"] == []


@pytest.mark.req("REQ-GATE-0008")
def test_the_leaf_diffs_ruling_moves_and_compared_describe_ONE_population():
    """`leaf_lab_diff` compares only SCORABLE rows, so its `ruling_moves` must use the same filter.

    Drawn from all rows instead, it would name a frame the report's own `compared` count excludes —
    two numbers printed side by side describing different populations, which is the confusion this
    module keeps existing to remove. The Decision Gate has no such filter, so it passes none."""
    unscorable = {"key": "u", "correct_is_top": None, "unscorable": True, "correct": [1]}
    before = _report([_row("s", "OK"), {**unscorable, "correct": [1]}])
    after = _report([_row("s", "OK"), {**unscorable, "correct": [2]}])
    d = leaf_lab_diff(before, after)
    assert d["compared"] == 1                      # only the scorable frame is compared...
    assert d["ruling_moves"] == []                 # ...so the unscorable frame's move is not claimed


@pytest.mark.req("REQ-GATE-0007")
def test_the_corpus_reader_over_the_COMMITTED_store_is_the_gates_corpus():
    """The invariant over the real corpus, not a fixture: the Decision Gate replays exactly the
    store's replayable set. A capture that shrinks — the 40-record drop this issue fixes — breaks
    this, and it is the assertion the issue's own acceptance asked for.

    Set equality, not a count: a count assertion passes on a mis-keyed corpus, which was the larger
    half of the defect. Independent of `data/decider_lab/baseline.json` on purpose — corrections are
    tagged continuously and re-capture is a deliberate human act, so asserting against the committed
    capture would redden `main` on every new tag."""
    from train.blunder.store import DEFAULT_ROOT
    from train.decider_lab import _records
    want = {k for k, _c in gates.keyed_corrections(predicate=lambda c: c.obs and c.agent)}
    got = {k for k, _c in _records(DEFAULT_ROOT, None)}
    assert got == want
    assert len(got) == len(want) > 300              # a plausible corpus, not an empty walk


# ── the Ruling Index — one query over every store a ruling can live in (ADR-0088, Issue #239) ──


def _reviewed(tmp_path, entries):
    """A `reviewed.json` ledger on disk, keyed the way that store keys — by ADR-0049's Scope subject
    (`review_key`), NOT by Frame Key. The two keyspaces differing is the whole reason the index has to
    derive its join inside the corpus walk."""
    path = tmp_path / "reviewed.json"
    path.write_text(json.dumps({"_note": "a comment key, dropped by the loader", **entries}),
                    encoding="utf-8")
    return path


def _held_out_fixture(fixtures_dir, frame_key, owner="#165"):
    """One committed-corpus fixture shape that opts a frame into the Held-out Ledger."""
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    (fixtures_dir / "f.json").write_text(json.dumps(
        {"frame_key": frame_key,
         "claims": {"decision": {"correct": [1], "owner": owner, "ruled": "2026-07-25",
                                 "why": "ruled out of scope"}}}), encoding="utf-8")
    return fixtures_dir


@pytest.mark.req("REQ-GATE-0010")
def test_a_refuted_ruling_voids_the_label_and_a_covered_one_does_not(tmp_path):
    """**The issue, in one assertion.** A refutation says the ruling was wrong; ``covered`` says it
    stands and is already handled. Only the first can stop grading — voiding is not "anything that
    appears in the ledger", and reading the ledger as a skip-list would drop 112 ``covered`` frames
    out of the corpus."""
    root = _store(tmp_path / "corpus", [_rec(1, 3), _rec(2, 4)])
    led = _reviewed(tmp_path, {"1-3": {"disposition": "refuted", "reason": "forgoes a KO"},
                               "2-4": {"disposition": "covered", "reason": "already handled"}})
    index = gates.ruling_index(root, reviewed_path=led, fixtures_dir=tmp_path / "none")
    assert sorted(gates.voided_frames(index)) == ["1|0|decision|3"]
    assert index["2|0|decision|4"][0].disposition == "covered"


@pytest.mark.req("REQ-GATE-0010")
def test_a_transposition_voids_for_a_DIFFERENT_reason_than_a_refutation(tmp_path):
    """Both void; the readout must still say WHICH. ADR-0085 decision 4 cites `81905522-75`'s human
    pick to justify leg-scoped rather than whole-target guards, so recording that frame as ``refuted``
    would write into the ledger an assertion a shipped ADR contradicts. The distinction is why
    `voids_the_label` is derived instead of the disposition being compared at call sites."""
    root = _store(tmp_path / "corpus", [_rec(1, 3)])
    led = _reviewed(tmp_path, {"1-3": {"disposition": "transposition",
                                       "reason": "two identical Riolu"}})
    index = gates.ruling_index(root, reviewed_path=led, fixtures_dir=tmp_path / "none")
    ruling = gates.voided_frames(index)["1|0|decision|3"]
    assert gates.voids_the_label(ruling)
    assert ruling.disposition == "transposition"        # NOT laundered into "refuted"
    assert ruling.source == "reviewed"


@pytest.mark.req("REQ-GATE-0010")
def test_the_index_derives_its_join_rather_than_assuming_the_decision_keyspace(tmp_path):
    """The two stores key differently and NEITHER derives from the other: `reviewed.json` keys by
    Scope subject (``<ep>-t<turn>s<seat>`` for a turn Correction), the gates by Frame Key
    (``<ep>|<seat>|<scope>|<subject>``). A translation written anywhere but inside the corpus walk is
    the hand-built key ADR-0087 decision 2 forbids — and the seat-0 / scope-``decision`` assumption is
    exactly the one that cost the Decision Gate 203 of its 372 keys."""
    root = _store(tmp_path / "corpus", [_rec(7, 51, seat=1),
                                        _rec(8, 82, seat=1, scope="turn", subject=8)])
    led = _reviewed(tmp_path, {"7-51": {"disposition": "refuted", "reason": "x"},
                               "8-t8s1": {"disposition": "refuted", "reason": "y"}})
    index = gates.ruling_index(root, reviewed_path=led, fixtures_dir=tmp_path / "none")
    assert sorted(gates.voided_frames(index)) == ["7|1|decision|51", "8|1|turn|8"]


@pytest.mark.req("REQ-GATE-0010")
def test_a_voiding_source_wins_over_a_non_voiding_one_and_both_are_retained(tmp_path):
    """The precedence rule. A refutation is a strictly later, stronger act than a ``covered`` or a
    hold-out, so a merge letting the weaker disposition win would re-open the hole. Every ruling is
    kept regardless, so the readout can still name every store that ruled the frame — which is what
    makes this an index rather than a skip-list."""
    root = _store(tmp_path / "corpus", [_rec(1, 3)])
    led = _reviewed(tmp_path, {"1-3": {"disposition": "refuted", "reason": "bad label"}})
    fixtures = _held_out_fixture(tmp_path / "fixtures", "1|0|decision|3")
    rulings = gates.ruling_index(root, reviewed_path=led, fixtures_dir=fixtures)["1|0|decision|3"]
    assert gates.voiding_ruling(rulings).disposition == "refuted"
    assert {r.source for r in rulings} == {"reviewed", "held_out"}


@pytest.mark.req("REQ-GATE-0010")
def test_a_held_out_ruling_alone_never_voids(tmp_path):
    """Holding a frame out of a gate's SCOPE is not disowning the ruling. If it voided, the eleven
    Held-out Ledger frames would silently leave the agree rate too — a denominator change nobody
    ruled on."""
    root = _store(tmp_path / "corpus", [_rec(1, 3)])
    fixtures = _held_out_fixture(tmp_path / "fixtures", "1|0|decision|3")
    index = gates.ruling_index(root, reviewed_path=_reviewed(tmp_path, {}), fixtures_dir=fixtures)
    assert gates.voided_frames(index) == {}
    assert index["1|0|decision|3"][0].owner == "#165"


@pytest.mark.req("REQ-GATE-0010")
def test_an_unrecognised_disposition_is_non_voiding_and_reported_not_swallowed(tmp_path):
    """The loud path. An unknown word keeps grading (the safe direction) but must not be silent: a
    disposition nobody registered is a ruling nobody's grader is honouring, and the committed ledger
    already demonstrated that drift running unnoticed with ``fixed`` and ``deferred-multi-turn``."""
    root = _store(tmp_path / "corpus", [_rec(1, 3)])
    led = _reviewed(tmp_path, {"1-3": {"disposition": "probably-fine", "reason": "?"}})
    index = gates.ruling_index(root, reviewed_path=led, fixtures_dir=tmp_path / "none")
    assert gates.voided_frames(index) == {}
    assert [k for k, _r in gates.unrecognised_rulings(index)] == ["1|0|decision|3"]


@pytest.mark.req("REQ-GATE-0010")
def test_the_writers_vocabulary_and_the_graders_vocabulary_are_the_same_words():
    """A word `review_correction.py` accepts that the graders do not recognise is precisely the
    silence that let ``fixed`` sit in the ledger unregistered. Pinned rather than trusted."""
    from train.blunder.reviewed import DISPOSITIONS
    assert set(DISPOSITIONS) | {"held_out"} == set(gates.RECOGNISED_DISPOSITIONS)


@pytest.mark.req("REQ-GATE-0010")
def test_a_voided_regression_is_reported_and_does_NOT_fail_either_gate():
    """**The live hazard, closed.** 18 of 101 recorded disagreements carried a refuted label, so a
    build that corrected one of them failed `main` as a REGRESSION — a fix wearing a regression's
    label. The row must still EXIST (a vanishing frame is the shrinking-gated-set failure
    ``added``/``removed`` exist to prevent); only the verdict is excused."""
    before = _dcap([_drow("void", [0], [0]), _drow("real", [0], [0])])
    after = _dcap([_drow("void", [3], [0]), _drow("real", [3], [0])])
    rows = decider_lab_diff(before, after, voided={"void"})["rows"]
    assert {r["key"]: r["verdict"] for r in rows} == {"void": "REGRESSION", "real": "REGRESSION"}
    assert not decision_gate_verdict(rows, held_out={}, voided=set())
    assert not decision_gate_verdict(rows, held_out={}, voided={"void"})       # `real` still gates
    assert decision_gate_verdict(rows, held_out={"real": "#1"}, voided={"void"})

    lb = _report([_row("void", "OK"), _row("real", "OK")])
    la = _report([_row("void", "MISS"), _row("real", "MISS")])
    d = leaf_lab_diff(lb, la, voided={"void"})
    assert sorted(f["key"] for f in d["ok_to_miss"]) == ["real", "void"]
    assert not discrimination_gate_verdict(d, held_out={}, voided={"void"})
    assert discrimination_gate_verdict(d, held_out={"real": "#1"}, voided={"void"})


# ── the Agree Delta — the aggregate half of the Ruling Move fix (ADR-0088 decision 7) ─────────


@pytest.mark.req("REQ-GATE-0011")
def test_offsetting_moves_cannot_present_as_stillness():
    """**The measured failure, asserted directly.** Re-capturing the baseline moved three rows and
    printed ``230/331 -> 230/331``, because a re-ruling flipped one frame disagree->agree and exactly
    cancelled a regression's agree->disagree. The rate legitimately does not move; what must not
    happen is the report implying nothing did."""
    before = _dcap([_drow("regressed", [1], [1]), _drow("reruled", [0], [9])])
    after = _dcap([_drow("regressed", [4], [1]), _drow("reruled", [0], [0])])
    delta = decider_lab_diff(before, after)["agree_delta"]
    assert delta["before"] == delta["after"] == (1, 2)     # the rate is genuinely unchanged...
    assert (delta["moved"], delta["reruled"]) == (1, 1)    # ...and the report says two things moved


@pytest.mark.req("REQ-GATE-0011")
def test_the_delta_restates_BOTH_sides_against_todays_voided_set():
    """The rulings are one corpus, not a property of a capture. Restating the baseline is what makes
    ``230/331 -> 231/313`` legible instead of an unexplained denominator jump — applying the voided
    set to only the new side would print a rate change no agent caused."""
    rows = [_drow("kept", [1], [1]), _drow("void", [0], [1])]
    delta = decider_lab_diff(_dcap(rows), _dcap(rows), voided={"void"})["agree_delta"]
    assert delta["before"] == delta["after"] == (1, 1)     # 1/2 -> 1/1 on BOTH sides
    assert delta["voided"] == 1


@pytest.mark.req("REQ-GATE-0011")
def test_an_unlabelled_or_unreplayable_frame_is_outside_the_delta_entirely():
    """Neither agreement nor disagreement, and neither is a void: ``correct is None`` was never ruled,
    ``chosen is None`` could not be replayed. Counting either in the denominator would report the
    agent as wrong about a frame nobody asked it about."""
    rows = [_drow("ok", [1], [1]), _drow("unlabelled", [0], None), _drow("dead", None, [1])]
    delta = decider_lab_diff(_dcap(rows), _dcap(rows))["agree_delta"]
    assert delta["before"] == delta["after"] == (1, 1)


@pytest.mark.req("REQ-GATE-0011")
def test_the_leaf_delta_is_drawn_from_the_SAME_population_as_its_compared_count():
    """The trap `ruling_moves` already documents, re-checked one function along: a delta drawn from
    all rows would report a rate over frames the diff's own ``compared`` excludes, and two numbers in
    one report must describe one population."""
    unscorable = {"key": "u", "correct_is_top": None, "unscorable": True, "correct": [1]}
    rpt = _report([_row("s", "OK"), unscorable])
    d = leaf_lab_diff(rpt, rpt)
    assert d["compared"] == 1
    assert d["agree_delta"]["before"] == d["agree_delta"]["after"] == (1, 1)


# ── the committed corpus, read through the index ──────────────────────────────────────────────────


@pytest.mark.req("REQ-GATE-0010")
def test_every_disposition_in_the_committed_ledger_is_recognised_vocabulary():
    """Over the REAL ledger. This is the assertion whose absence let ``fixed`` and
    ``deferred-multi-turn`` sit unregistered — the file and the vocabulary drifting apart in silence
    is the defect, not either word."""
    assert gates.unrecognised_rulings(gates.ruling_index()) == []


@pytest.mark.req("REQ-GATE-0010")
def test_an_orphaned_ledger_entry_is_reported_rather_than_ruling_on_nothing(tmp_path):
    """A ledger key matching no committed Correction voids NOTHING, silently — `ruling_index` walks
    the CORPUS and looks each record up, so an unreachable entry never enters the index and nothing
    reports that it rules on nothing.

    Asserting it via the index is IMPOSSIBLE and the attempt is a trap: ``voided_frames(index)`` is a
    subset of ``keyed_corrections`` **by construction**, so a test written that way can never fail.
    The join has to be walked from the LEDGER's side, which is what `orphan_rulings` does — the same
    detachment guard `claim_agreement`'s ``no_record`` finding is one store over."""
    root = _store(tmp_path / "corpus", [_rec(1, 3)])
    led = _reviewed(tmp_path, {"1-3": {"disposition": "refuted", "reason": "real"},
                               "9-99": {"disposition": "refuted", "reason": "rules on nothing"}})
    index = gates.ruling_index(root, reviewed_path=led, fixtures_dir=tmp_path / "none")
    assert sorted(gates.voided_frames(index)) == ["1|0|decision|3"]      # the orphan voids nothing...
    assert [k for k, _e in gates.orphan_rulings(root, reviewed_path=led)] == ["9-99"]   # ...but is SEEN


@pytest.mark.req("REQ-GATE-0010")
def test_no_committed_ledger_entry_rules_on_nothing():
    """Over the REAL ledger, and the strongest form: **zero** entries rule on no committed
    Correction.

    This asserted the two known orphans by name while fixing them was still the user's call. Both are
    now repaired (Issue #250) — and neither was stale, which is why the assertion could be tightened
    rather than merely re-measured: `85046350-10` had the wrong EPISODE (the record is ep 85045840 f10, in the
    same store file) and `86091435-119` the wrong key SHAPE (the record is turn-scoped, so its
    `review_key` is `86091435-t14s0`; 119 is the Anchor frame the report used to print).

    Asserting empty rather than a count also makes this the reachability guard for the WHOLE ledger:
    it proves all ~145 committed entries resolve, including the ones nobody has re-checked. A new
    orphan — the third, from any source — turns it red on the commit that introduces it. The writer
    now refuses to create one (ADR-0090 decision 2), so this is the backstop for hand-edits."""
    assert [k for k, _e in gates.orphan_rulings()] == []


@pytest.mark.req("REQ-GATE-0010")
def test_the_excused_split_prefers_the_held_out_label_when_a_frame_is_both():
    """One precedence, shared by both gates. A HELD-OUT ruling STANDS and is merely out of this gate's
    scope; a voided one cannot grade at all — so when a frame carries both, HELD OUT is the more
    informative thing to print. Written once because both gates had the same three comprehensions,
    which is how the two would eventually disagree about what excuses a frame."""
    rows = [{"key": "both"}, {"key": "held"}, {"key": "void"}, {"key": "bare"}]
    gating, ruled, void_hits = gates.split_excused(
        rows, {"both": "#1", "held": "#1"}, {"both": object(), "void": object()})
    assert [r["key"] for r in gating] == ["bare"]
    assert [r["key"] for r in ruled] == ["both", "held"]
    assert [r["key"] for r in void_hits] == ["void"]


@pytest.mark.req("REQ-GATE-0010")
def test_the_transposition_frame_is_now_GRADED_and_SATISFIED_not_voided():
    """`81905522|0|decision|75` — the frame this whole vocabulary was invented for — is graded again
    (ADR-TEMP-247 decision 3, Issue #247).

    This test used to assert the frame was *recorded and voided*, i.e. it pinned the WORKAROUND. The
    oracle makes the ruling satisfiable on purpose: the agent picks index 1, the human ruled index 3,
    and the two are the same undamaged Riolu, so the pick agrees. Voiding it now would excuse a frame
    the gate can adjudicate — verbatim the complaint Issue #247's title makes.

    `82749168-38` still stands as the neighbouring `refuted`, and its SEAT is still the point: it is
    seat **1**, while the retired probe constant keyed it ``"82749168-38"`` with no seat at all, which
    is why that store could never join the gates' keyspace. The key here is derived by the index
    rather than written by hand, which is the property that catches it."""
    voided = gates.voided_frames(gates.ruling_index())
    assert "81905522|0|decision|75" not in voided, "the transposition entry is retired, not re-filed"
    assert voided["82749168|1|decision|38"].disposition == "refuted"

    equiv = gates.equivalence_index()["81905522|0|decision|75"]
    assert equiv[1] == equiv[3] and 1 in equiv[3], "the two Riolu are ONE decision"
    assert gates.satisfies_human([1], [3], equiv=equiv) is True
    assert gates.satisfies_human([1], [3]) is False, "and it took the oracle to see it"


def test_the_transposition_WORD_survives_with_no_corpus_entry_behind_it():
    """Decision 3 deletes the ENTRY and keeps the VOCABULARY. The oracle is sound only over what the
    snapshot reveals — a face-down DECK option can never be fingerprinted — so an equivalence turning
    on information outside `obs` would otherwise be unrecordable by a human."""
    assert "transposition" in gates.VOIDING_DISPOSITIONS
    assert "transposition" in gates.RECOGNISED_DISPOSITIONS


def test_the_SECOND_instance_nobody_ruled_is_graded_correctly():
    """`86091728|0|decision|19` sat in the corpus scored as a DISAGREEMENT the entire time — the same
    Energy card onto either of two identical id-119 basics (70/70, empty, no tools), agent on bench 0
    and the human on bench 1.

    It is the evidence that the class needed fixing rather than the instance: nobody had ruled it, so
    no ledger entry could ever have reached it, and only an oracle reading the board finds it."""
    equiv = gates.equivalence_index()["86091728|0|decision|19"]
    assert gates.satisfies_human([2], [3], equiv=equiv) is True
    assert gates.satisfies_human([2], [3]) is False


def test_a_ruling_is_NOT_satisfied_by_an_option_outside_its_class():
    """The negative half, on the same real frame: the class widens what satisfies a ruling, it does
    not make the ruling vacuous."""
    equiv = gates.equivalence_index()["86091728|0|decision|19"]
    assert gates.satisfies_human([1], [3], equiv=equiv) is False


# ── the no-DLL layering, asserted rather than asserted-in-prose ──────────────────────────────────

def test_importing_gates_never_maps_the_native_engine():
    """`train.gates` must stay loadable with **no DLL** — the offline cross-platform suite depends on
    it, and `cg.api` maps the native library on a bare import (`libcg` in /proc/self/maps).

    Until ADR-TEMP-247 that constraint was a COMMENT. Decision 7 has `gates` import shipped code
    (`common.option_equivalence`), which is exactly the kind of edge that turns a documented
    invariant into a broken one three refactors later — a shipped module gains an innocuous
    convenience import and the gates stop loading on a machine with no engine. So it is a test now.

    A subprocess, because this process has almost certainly imported `cg` already: the assertion is
    about what a FRESH interpreter loads, which an in-process check cannot see."""
    import subprocess
    import sys
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    code = ("import sys;"
            "sys.path[:0] = [r'%s', r'%s'];"
            "import train.gates;"
            "import common.option_equivalence;"
            "bad = sorted(m for m in sys.modules if m == 'cg' or m.startswith('cg.'));"
            "print(','.join(bad))" % (repo / "tools", repo / "src"))
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                          cwd=str(repo), encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "", (
        f"importing the gates pulled in the engine wrapper: {proc.stdout.strip()}")


# ── the Option Equivalence Class reaches the predicate (pure half) ───────────────────────────────

def test_no_equiv_map_is_byte_identical_to_the_old_predicate():
    """The default that protects three decider sweeps and every assertion above: a caller that does
    not ask for equivalence gets exactly the pre-#247 answer."""
    assert satisfies_human([1], [3]) is False
    assert satisfies_human([1], [3], equiv=None) is False
    assert satisfies_human([1], [3], equiv={}) is False


def test_a_sibling_pick_satisfies_a_ruling_naming_its_twin():
    equiv = {1: frozenset({1, 3}), 3: frozenset({1, 3})}
    assert satisfies_human([1], [3], equiv=equiv) is True
    assert satisfies_human([3], [1], equiv=equiv) is True


def test_an_unrelated_pick_still_fails_under_an_equiv_map():
    equiv = {1: frozenset({1, 3}), 3: frozenset({1, 3})}
    assert satisfies_human([2], [3], equiv=equiv) is False


def test_a_DECLINE_stays_exact_under_an_equiv_map():
    """The dangerous case. ``correct == []`` names no index, so there is no class to widen — and the
    empty set being a subset of everything is what would make every frame vacuously agree."""
    equiv = {0: frozenset({0, 1}), 1: frozenset({0, 1})}
    assert satisfies_human([], [], equiv=equiv) is True
    assert satisfies_human([0], [], equiv=equiv) is False


def test_a_multi_pick_ruling_still_needs_EVERY_ruled_card_matched():
    """A class widens what satisfies each ruled card; it never excuses a missing one."""
    equiv = {1: frozenset({1, 3}), 3: frozenset({1, 3})}
    assert satisfies_human([1, 5], [3, 5], equiv=equiv) is True
    assert satisfies_human([1], [3, 5], equiv=equiv) is False, "half an answer is not an answer"


def test_an_unreplayable_frame_satisfies_nothing_even_with_a_class():
    equiv = {1: frozenset({1, 3}), 3: frozenset({1, 3})}
    assert satisfies_human(None, [3], equiv=equiv) is False


def test_a_capture_row_records_WHICH_options_were_one_decision():
    """`classes_of` is the JSON-safe shape, and it must be stable so a re-capture diff is readable."""
    equiv = {3: frozenset({1, 3}), 1: frozenset({1, 3}), 4: frozenset({4, 0}), 0: frozenset({4, 0})}
    assert gates.classes_of(equiv) == [[0, 4], [1, 3]]
    assert gates.classes_of({}) == []
    assert gates.classes_of(None) == []
