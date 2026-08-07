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
# corpus (#250) and would otherwise re-encode it. Aliased so the 18 call sites below read unchanged.
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
    """Importing `cg.api` MAPS THE NATIVE LIBRARY and `train.gates` must stay loadable with no DLL, so
    the lane constants are written literally there and PINNED here rather than remembered."""
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
    """A mid-game bench play is `OptionType.PLAY` with a BARE hand index and no `area`, so the
    positional resolver returns None. Given the frame it resolves to the CARD instead."""
    frame = {"current": {"yourIndex": 0,
                         "players": [{"hand": [{"id": 1227}, {"id": 1121}, {"id": 676}]}, {}]}}
    assert option_slot({"type": 7, "index": 2}, frame) == ("card", 676)
    assert option_slot({"type": 7, "index": 0}, frame) == ("card", 1227)


@pytest.mark.req("REQ-TRAIN-0041")
def test_option_slot_resolves_a_setup_bench_hand_card_to_the_same_identity():
    """The pregame Bench places with `OptionType.CARD` + `area = HAND`, and `_TO_BENCH` fetches straight
    onto the Bench. All three deploy entry points must resolve to the SAME identity."""
    frame = {"current": {"yourIndex": 0, "players": [{"hand": [{"id": 1071}]}, {}]}}
    assert option_slot({"type": 3, "area": 2, "index": 0}, frame) == ("card", 1071)


@pytest.mark.req("REQ-TRAIN-0041")
def test_option_slot_is_byte_identical_without_a_frame():
    """Back-compat: with no frame the resolver is exactly the positional one it has always been, so the
    three existing sweeps keep their meaning with no edit."""
    assert option_slot({"type": 7, "index": 2}) is None
    assert option_slot({"type": 3, "area": 2, "index": 0}) == (2, 0)
    assert option_slot({"type": 14}) is None


@pytest.mark.req("REQ-TRAIN-0041")
def test_option_slot_prefers_the_board_slot_over_card_identity():
    """A BODY option keeps resolving to its board slot even when a frame is available — re-pointing it
    at a card id would silently re-base three shipped sweeps and every committed Axis Claim."""
    frame = {"current": {"yourIndex": 0, "players": [{"hand": [{"id": 676}],
                                                      "bench": [{"id": 678}]}, {}]}}
    assert option_slot({"type": 9, "area": 5, "index": 0,
                        "inPlayArea": 5, "inPlayIndex": 0}, frame) == (5, 0)
    assert option_slot({"type": 3, "area": 4, "index": 2}, frame) == (4, 2)


@pytest.mark.req("REQ-TRAIN-0041")
def test_option_slot_falls_back_when_the_frame_cannot_resolve_the_card():
    """Fail-soft, never crash: an out-of-range index, a face-down (None) hand entry or a missing seat
    leaves the positional answer — a probe reads whatever the corpus recorded, truncations included."""
    frame = {"current": {"yourIndex": 0, "players": [{"hand": [None]}, {}]}}
    assert option_slot({"type": 7, "index": 9}, frame) is None       # out of range
    assert option_slot({"type": 7, "index": 0}, frame) is None       # face-down entry
    assert option_slot({"type": 3, "area": 2, "index": 9}, frame) == (2, 9)
    assert option_slot({"type": 7, "index": 0}, {"current": {}}) is None


@pytest.mark.req("REQ-TRAIN-0041")
def test_option_slot_reads_the_option_owner_not_always_the_asked_seat():
    """`playerIndex` names whose zone the option indexes, so the resolver must not hardcode the asked
    seat or it mis-resolves an opponent-owned card option the moment one enters a lane."""
    frame = {"current": {"yourIndex": 0,
                         "players": [{"hand": [{"id": 1}]}, {"hand": [{"id": 2}]}]}}
    assert option_slot({"type": 3, "area": 2, "index": 0, "playerIndex": 1}, frame) == ("card", 2)


@pytest.mark.req("REQ-TRAIN-0041")
def test_lane_slots_forwards_the_frame_so_a_deploy_lane_compares_cards():
    """`lane_slots` is what the sweeps and Axis Claims call, so the frame has to reach the resolver
    through it — otherwise two identical Solrock plays at different indices read as different decisions."""
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
    """Comparison is by resolved BODY SLOT, never by raw option index: two Dreepy→Drakloak evolves
    differ ONLY in which body they evolve, and the index says nothing about which."""
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
    """A Lane is (option_type, required_select_context|None) members, so the attach sweep's rule is DATA
    rather than a special case at a call site. An evolve lane is the single-member case."""
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
    """Back-compat is why the back-fill can be incremental: ~130 existing fixtures carry no `claims`
    block and must keep their present meaning with no edit — a Decision Claim over `correct`."""
    claims = parse_claims({"correct": [2], "chosen": [0]})
    assert claims.decision == DecisionClaim(correct=[2], owner=None)
    assert claims.axis == []
    assert evaluate_decision_claim(claims.decision, chosen=[2]) is True
    assert evaluate_decision_claim(claims.decision, chosen=[1]) is False


@pytest.mark.req("REQ-TRAIN-0041")
def test_an_axis_claim_asserts_ordering_within_one_lane_not_a_score():
    """Ordering, never scores: raw scores are not comparable across a currency re-banding, while
    ordering WITHIN a lane survives one."""
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
    """The single-option-lane case, which ordering cannot reach: does the option clear the endorsement
    floor (`score > 0`) at all? Zero is a STRUCTURAL boundary, not a tuned magnitude."""
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
    """f35's shape: its Decision Claim is owned by #165 while its Axis Claim still GATES. A per-fixture
    flag could not express that, and would either hide a live claim or gate a deferred one."""
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
    """Keying rows by `episode_id` alone silently merged frames from one episode and UNDER-REPORTED the
    diff. Rows key on the Correction's `identity_key` (episode, seat, scope, subject) instead."""
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
    """The Held-out Ledger's shape check over the real corpus. Whether that issue is still OPEN is
    explicitly NOT checked — the suite has no network (ADR-0072 decision 4)."""
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
    """The Ledger must not be inert: a ruling that exists in prose but produces no entry has not been
    encoded. Each entry's frame_key was verified by an EXACT `select`-payload match to its Correction."""
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

# ── Claim Agreement — a fixture's ruling must match its Correction's (ADR-0082) ───────────────────
# The two fixture generations measured perfectly disjoint; this gate makes losing a re-ruling loud.

#: Fixtures carrying an ``episode``+``frame`` pair that deliberately assert **no pick**. Both are
#: REFUTED Corrections whose `agent_choice`/`human_wanted` fields INVERT `chosen`/`correct`.
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
    """Escape 1 — a **Held-out Frame**, with `dragapult_hammer_over_develop_f32` the live instance.
    Deleting the owner returns it to gating, exactly as ADR-0072 decision 4 specifies."""
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
    """The escape must be auditable against the record ON A DATE, so `ruled` owes ``YYYY-MM-DD``; without
    it a value like "soon" disarms the gate forever. Malformed values are REJECTED rather than raise."""
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
    does not — ADR-0050 seeding, which changes HOW a fixture replays and never WHAT the human ruled."""
    store = _corr(tmp_path, obs={"current": {"turn": 3}})
    fx = _fixture_file(tmp_path, "seeded", {"frame_key": "1|0|decision|5",
                                            "claims": {"decision": {"correct": [1]}},
                                            "obs": {"current": {"turn": 3}, "own_prizes": 4,
                                                    "search_begin_input": {"seed": 7}}})
    assert gates.claim_agreement(fixtures_dir=fx, store=store) == []


@pytest.mark.req("REQ-TRAIN-0045")
def test_an_obs_mismatch_beyond_the_seeding_keys_is_reported_because_indices_stop_comparing(tmp_path):
    """`correct` is a list of positional option indices, so comparing it across two different boards is
    meaningless — reported even when an escape is declared, since that excuses a ruling, not a JOIN."""
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
    """Legal and load-bearing (ADR-0082): two fixtures may share one frame key, so the gate must not
    assume one per frame and one bad sibling must not exonerate the other."""
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
    """`parse_claims`'s back-compat promise upheld at the gate: declaring a `frame_key` is what opts a
    fixture in. Inventing one from a loose `episode`+`frame` pair would be guessing at the identity."""
    store = _corr(tmp_path, correct=(1,))
    fx = _fixture_file(tmp_path, "unkeyed", {"episode": 1, "frame": 5, "correct": [2],
                                             "obs": {"current": {"turn": 3}}})
    assert gates.claim_agreement(fixtures_dir=fx, store=store) == []


@pytest.mark.req("REQ-TRAIN-0045")
def test_both_corpus_readers_share_one_walk(tmp_path):
    """`iter_keyed_fixtures` is THE corpus walk: a second glob that drifted by a field would silently
    stop seeing frames, so a fixture invisible to one reader must be invisible to the other."""
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
    """`parse_claims` PREFERS an explicit `claims` block while 33 test modules still read
    `fx["correct"]` directly, so a fixture carrying both must keep them identical."""
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
    """ADR-0082 decision 1's completeness invariant: `claim_agreement` opts in on `frame_key`, so a
    fixture that has a joinable identity and omits one is silently ungated."""
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
    """The exclusion above must stay honest: if either fixture ever gains a `correct` it becomes
    gateable. Asserts the inversion too — `human_wanted` is the REFUTED ask, never the ruling."""
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
    """The property Amendment I restores: the sweeps this replaces compared against a kill-switch-OFF
    arm that became an empty scorer, so they could only ever produce FIX. All four directions here."""
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
    """A reordered multi-pick is NOT a regression: `DISCARD` asks for N cards and the engine applies the
    SET, so comparing sequences would report a false REGRESSION — the direction that blocks a merge."""
    before = _dcap([_drow("k", [0, 2], [0, 2], context=8)])
    after = _dcap([_drow("k", [2, 0], [0, 2], context=8)])
    assert decider_lab_diff(before, after)["rows"] == [], "order is not a decision"
    # a genuine change to the SET is still caught
    moved = _dcap([_drow("k", [2, 4], [0, 2], context=8)])
    assert [r["verdict"] for r in decider_lab_diff(before, moved)["rows"]] == ["REGRESSION"]


# ── `satisfies_human` — a Correction's `correct` is a CONSTRAINT, not the answer (ADR-0085 J) ─────

def test_a_multi_pick_satisfies_a_ruling_it_is_a_superset_of():
    """**The Amendment J ruling.** `correct` names the card the ruling was ABOUT; a multi-pick returns
    every index the engine demands. Under `⊆` the same corpus reads 10/12 where equality read 1/12."""
    assert satisfies_human([2, 3], [2]) is True
    assert satisfies_human([3, 4], [2]) is False, "the ruled card was NOT discarded"
    assert satisfies_human([2], [2, 3]) is False, "a partial answer does not satisfy a two-card ruling"


def test_satisfaction_degenerates_to_equality_on_a_single_pick():
    """Why the 220 single-pick agreements are untouched by the ruling: with one index a side, `⊆`
    and `==` are the same test. The change buys the multi-pick contexts and costs nothing elsewhere."""
    assert satisfies_human([1], [1]) is True
    assert satisfies_human([0], [1]) is False


def test_an_empty_correct_is_a_DECLINE_ruling_and_needs_an_empty_pick():
    """The guard that makes `⊆` safe: the empty set is a subset of everything, so `correct: []` is read
    EXACTLY — it is a recorded DECLINE, not an absence, and eleven such frames sit in the corpus."""
    assert satisfies_human([], []) is True
    assert satisfies_human([0], []) is False, "picking something does not satisfy a DECLINE"


def test_an_absent_ruling_and_an_unreplayable_frame_satisfy_nothing():
    """`correct is None` claims no direction; `chosen is None` is a frame this build could not replay.
    Neither may read as agreement — that is how a shrinking gated set looks green."""
    assert satisfies_human([0], None) is False
    assert satisfies_human(None, [0]) is False
    assert satisfies_human(None, None) is False


def test_the_diff_judges_direction_through_the_same_predicate_as_the_agree_rate():
    """The gate and the readout must not hold two ideas of "matches the human". The shared predicate
    makes the gate STRICTLY more sensitive on multi-pick contexts, never less."""
    before = _dcap([_drow("k", [2, 3], [2], context=8)])
    after = _dcap([_drow("k", [3, 4], [2], context=8)])
    assert [r["verdict"] for r in decider_lab_diff(before, after)["rows"]] == ["REGRESSION"]
    # ...and the reverse move is the FIX it looks like
    assert [r["verdict"] for r in decider_lab_diff(after, before)["rows"]] == ["FIX"]


def test_a_move_the_ruling_does_not_separate_is_NEUTRAL_in_both_directions():
    """NEUTRAL covers both-miss AND both-satisfy: a real change the corpus simply does not adjudicate.
    Calling it a REGRESSION would gate on a preference no one recorded."""
    before = _dcap([_drow("k", [2, 3], [2], context=8)])
    after = _dcap([_drow("k", [2, 5], [2], context=8)])
    assert [r["verdict"] for r in decider_lab_diff(before, after)["rows"]] == ["NEUTRAL"]


# ── the Corpus Reader — ONE reader, ONE key (ADR-0087, Issue #241) ────────────────────────────────
# A hand-built key drifts on both sides of a diff at once, so a wrong keyspace never goes red.





@pytest.mark.req("REQ-GATE-0007")
def test_the_corpus_reader_returns_the_stores_replayable_set(tmp_path):
    """`keyed_corrections` IS the corpus, and the expectation is derived independently. Set equality,
    not a count — a count passes happily on mis-keyed rows."""
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
    """40 records carry an empty ``agent`` with a populated ``agent_build``, and only a reader that
    CONSTRUCTS a Correction backfills the deck from the stem. Empty is RECOVERABLE, not missing."""
    root = _store(tmp_path, [_rec(1, 3, agent="", agent_build="mega_starmie_20260627_93a70be")],
                  build="mega_starmie_20260627_93a70be")
    got = gates.keyed_corrections(root, predicate=lambda c: c.obs and c.agent)
    assert [c.agent for _k, c in got] == ["mega_starmie"]


@pytest.mark.req("REQ-GATE-0007")
def test_the_reader_keys_by_identity_not_by_the_anchor_frame(tmp_path):
    """``seat`` is top-level and the Scope's SUBJECT is the identity (ADR-0049) — not seat 0, and not
    the Anchor frame. Defaulting the seat made every key say 0 over a corpus that is 201/171."""
    root = _store(tmp_path, [_rec(7, 51, seat=1), _rec(8, 82, seat=0, scope="turn", subject=8)])
    keys = {k for k, _c in gates.keyed_corrections(root)}
    assert keys == {"7|1|decision|51", "8|0|turn|8"}


@pytest.mark.req("REQ-GATE-0007")
def test_both_gates_key_a_frame_identically(tmp_path):
    """ADR-0072 decision 4 — *one ruling holds a frame out of BOTH gates* — as an executable assertion.
    It was FALSE for 4 of 11 committed rulings, so a held-out frame that regressed would fail `main`."""
    from train.leaf_lab import frame_key
    root = _store(tmp_path, [_rec(7, 51, seat=1), _rec(8, 82, seat=0, scope="turn", subject=8)])
    for key, c in gates.keyed_corrections(root):
        assert key == frame_key(c)


@pytest.mark.req("REQ-GATE-0007")
def test_two_corrections_sharing_a_key_both_survive_the_reader(tmp_path):
    """Pairs, not a dict: ``load_corrections`` deliberately KEEPS conflicts, and a reader that dropped
    one would commit this issue's own defect at the seam built to remove it."""
    root = _store(tmp_path, [_rec(1, 3, correct=[1], category="wasted_resource"),
                             _rec(1, 3, correct=[2], category="sequencing_error")])
    got = gates.keyed_corrections(root)
    assert [k for k, _c in got] == ["1|0|decision|3", "1|0|decision|3"]
    assert sorted(tuple(c.correct) for _k, c in got) == [(1,), (2,)]


@pytest.mark.req("REQ-GATE-0007")
def test_every_held_out_ruling_names_a_frame_the_committed_store_carries():
    """The detachment guard over the REAL corpus. Deliberately NOT ``baseline keys == store keys``:
    that would redden `main` on every new tag and apply exactly the pressure toward auto-recapture."""
    keys = {k for k, _c in gates.keyed_corrections()}
    missing = sorted(k for k in gates.held_out_frames() if k not in keys)
    assert missing == []


# ── Ruling Moves — the channel for a corpus whose RULING moved (ADR-0087 decision 7) ──────────


@pytest.mark.req("REQ-GATE-0008")
def test_a_moved_ruling_is_reported_even_when_the_agents_pick_did_not_move():
    """Both diffs emit a row only when the agent's pick MOVES, so a re-ruled frame the agent plays
    identically produces no row while its verdict silently flips. ``added``/``removed`` cannot see it."""
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
    """``leaf_lab_diff`` compares ``correct_is_top``, computed FROM ``correct``, so it carries the
    identical blindness. Shared implementation, because a second one would drift."""
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
    """``added``/``removed`` already own that case; reporting it twice would double-count a corpus-shape
    change as a re-ruling."""
    before, after = _dcap([_drow("a", [0], [0])]), _dcap([_drow("b", [0], [1])])
    d = decider_lab_diff(before, after)
    assert d["ruling_moves"] == [] and d["added"] == ["b"] and d["removed"] == ["a"]


@pytest.mark.req("REQ-GATE-0010")
def test_a_gate_artifact_is_written_LF_framed_not_the_platforms_newline(tmp_path):
    """Both committed baselines are LF, dev is Windows and the grader is Linux. `Path.write_text` turned
    a 40-row re-capture into a 4835-line rewrite, so `write_json_artifact` is the single writer."""
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
    """The baseline is a COMMITTED ruling record, so nothing it embeds may depend on who ran the capture.
    Slash normalisation must precede stripping the root — an exception's ``str`` is already escaped."""
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
    """``None -> [x]`` is a frame becoming gateable and ``[x] -> None`` one ceasing to be; both change
    what the corpus can adjudicate, and neither shows up in `added`/`removed`."""
    gained = decider_lab_diff(_dcap([_drow("k", [0], None)]), _dcap([_drow("k", [0], [1])]))
    assert gained["ruling_moves"] == [{"key": "k", "before": None, "after": [1]}]
    lost = decider_lab_diff(_dcap([_drow("k", [0], [1])]), _dcap([_drow("k", [0], None)]))
    assert lost["ruling_moves"] == [{"key": "k", "before": [1], "after": None}]
    # ...and a frame that never carried a ruling on either side has not moved.
    never = decider_lab_diff(_dcap([_drow("k", [0], None)]), _dcap([_drow("k", [1], None)]))
    assert never["ruling_moves"] == []


@pytest.mark.req("REQ-GATE-0008")
def test_the_leaf_diffs_ruling_moves_and_compared_describe_ONE_population():
    """`leaf_lab_diff` compares only SCORABLE rows, so its `ruling_moves` must use the same filter — two
    numbers printed side by side must describe one population. The Decision Gate has no such filter."""
    unscorable = {"key": "u", "correct_is_top": None, "unscorable": True, "correct": [1]}
    before = _report([_row("s", "OK"), {**unscorable, "correct": [1]}])
    after = _report([_row("s", "OK"), {**unscorable, "correct": [2]}])
    d = leaf_lab_diff(before, after)
    assert d["compared"] == 1                      # only the scorable frame is compared...
    assert d["ruling_moves"] == []                 # ...so the unscorable frame's move is not claimed


# ── the Stale Baseline partition — a re-ruling's flip is LABELLED, never excused ─────────────────


@pytest.mark.req("REQ-GATE-0013")
def test_a_flip_whose_ruling_moved_is_in_BOTH_ok_to_miss_and_stale_baseline():
    """`correct_is_top` is FROZEN into each capture, so a moved ruling makes the leaf diff grade its two
    halves under two oracles. The frame still gates and gains a LABEL saying the reference changed."""
    before = _report([{**_row("reruled", "OK"), "correct": [1]}])
    after = _report([{**_row("reruled", "MISS"), "correct": [2]}])
    d = leaf_lab_diff(before, after)
    assert [f["key"] for f in d["ok_to_miss"]] == ["reruled"]
    assert [f["key"] for f in d["stale_baseline"]] == ["reruled"]


@pytest.mark.req("REQ-GATE-0013")
def test_a_flip_with_no_ruling_move_is_NOT_labelled_stale():
    """The positive control's other half: a real regression must not acquire the excuse-shaped label.
    Same ``correct`` on both sides, so the flip is the agent's."""
    before = _report([{**_row("real", "OK"), "correct": [1]}])
    after = _report([{**_row("real", "MISS"), "correct": [1]}])
    d = leaf_lab_diff(before, after)
    assert [f["key"] for f in d["ok_to_miss"]] == ["real"]
    assert d["stale_baseline"] == []


@pytest.mark.req("REQ-GATE-0013")
def test_a_ruling_move_that_did_not_flip_the_verdict_is_not_a_stale_baseline():
    """`stale_baseline` is a partition OF `ok_to_miss`, not a second view of `ruling_moves`. A frame
    re-ruled without its verdict moving has nothing to explain — the gate says nothing about it."""
    before = _report([{**_row("quiet", "OK"), "correct": [1]}])
    after = _report([{**_row("quiet", "OK"), "correct": [1, 2]}])
    d = leaf_lab_diff(before, after)
    assert d["ruling_moves"] and d["ok_to_miss"] == [] and d["stale_baseline"] == []


@pytest.mark.req("REQ-GATE-0013")
def test_the_stale_label_NEVER_changes_the_verdict():
    """ADR-0110 decision 1: `discrimination_gate_verdict` must return the IDENTICAL verdict for the
    labelled and unlabelled shapes, so neither committed baseline is owed a re-capture."""
    stale = _report([{**_row("k", "MISS"), "correct": [2]}])
    plain = _report([{**_row("k", "MISS"), "correct": [1]}])
    base = _report([{**_row("k", "OK"), "correct": [1]}])
    labelled, unlabelled = leaf_lab_diff(base, stale), leaf_lab_diff(base, plain)
    assert labelled["stale_baseline"] and not unlabelled["stale_baseline"]
    for d in (labelled, unlabelled):
        assert discrimination_gate_verdict(d, held_out={}) is False
        assert discrimination_gate_verdict(d, held_out={"k": "#230"}) is True
    # ...and the entries are the SAME objects `ok_to_miss` holds, so "it stays gated" is literal
    # rather than a parallel list that could drift out of step with it.
    assert labelled["stale_baseline"][0] is labelled["ok_to_miss"][0]


@pytest.mark.req("REQ-GATE-0013")
def test_stale_baseline_is_drawn_from_the_same_scorable_population_as_ruling_moves():
    """The trap `ruling_moves`' `keep` argument exists for, re-checked one key along: a partition
    naming a frame that `compared` excludes puts two populations in one report."""
    unscorable = {"key": "u", "correct_is_top": None, "unscorable": True}
    before = _report([{**_row("s", "OK"), "correct": [1]}, {**unscorable, "correct": [1]}])
    after = _report([{**_row("s", "MISS"), "correct": [2]}, {**unscorable, "correct": [9]}])
    d = leaf_lab_diff(before, after)
    assert d["compared"] == 1
    assert [f["key"] for f in d["stale_baseline"]] == ["s"]


@pytest.mark.req("REQ-GATE-0013")
def test_the_decision_gate_is_deliberately_NOT_given_a_stale_baseline_partition():
    """The asymmetry (ADR-0110 decision 5): `decider_lab_diff` resolves ``correct`` from the AFTER
    capture alone and grades both sides through it, so it never runs two oracles and owes no label."""
    d = decider_lab_diff(_dcap([_drow("k", [0], [0])]), _dcap([_drow("k", [0], [1])]))
    assert d["rows"] == [] and d["ruling_moves"]          # a re-ruling alone produces no verdict row
    assert "stale_baseline" not in d

    moved = decider_lab_diff(_dcap([_drow("k", [1], [0])]), _dcap([_drow("k", [0], [1])]))
    assert [(r["verdict"], r["correct"]) for r in moved["rows"]] == [("REGRESSION", [1])]
    assert "stale_baseline" not in moved


@pytest.mark.req("REQ-GATE-0013")
def test_the_stale_readout_names_the_capture_point_and_stays_silent_when_empty(capsys):
    """A label with no instruction is scenery: the line must say WHERE to re-capture from, because
    capturing at HEAD bakes the change under test into its own reference."""
    gates.print_stale_baseline([])
    assert capsys.readouterr().out == ""

    gates.print_stale_baseline([{"key": "k",
                                 "before": {"correct": [1], "correct_rank": 1},
                                 "after": {"correct": [2], "correct_rank": 3}}])
    out = capsys.readouterr().out
    assert "STALE BASELINE (1)" in out
    assert "k" in out and "[1] -> [2]" in out and "1 -> 3" in out
    assert gates.CAPTURE_POINT in out          # the capture-point instruction, verbatim
    assert "still gate" in out                 # ...and that it is a label, not an excuse


@pytest.mark.req("REQ-GATE-0013")
def test_the_json_artifact_reports_stale_baseline_as_a_SUBSET_of_ok_to_miss():
    """`leaf_lab --diff --out` is consumed by `leaf-gate-main.yml`, so `stale_baseline` is a public
    contract. The property is **subset**, never difference — asserted on the artifact that leaves."""
    before = _report([_row("clean", "OK"), {**_row("reruled", "OK"), "correct": [1]}])
    after = _report([_row("clean", "MISS"), {**_row("reruled", "MISS"), "correct": [2]}])
    d = leaf_lab_diff(before, after)

    ok, stale = [f["key"] for f in d["ok_to_miss"]], [f["key"] for f in d["stale_baseline"]]
    assert set(stale) < set(ok)                       # STRICT subset: it partitions, never replaces
    assert sorted(ok) == ["clean", "reruled"] and stale == ["reruled"]
    # The un-re-ruled flip is NOT relabelled — otherwise the section would explain away a real
    # regression, which is the failure mode in the opposite direction.
    assert "clean" not in stale


@pytest.mark.req("REQ-GATE-0007")
def test_the_corpus_reader_over_the_COMMITTED_store_is_the_gates_corpus():
    """The invariant over the real corpus: the Decision Gate replays exactly the store's replayable set.
    Set equality, not a count, and independent of the committed capture on purpose."""
    from train.blunder.store import DEFAULT_ROOT
    from train.decider_lab import _records
    want = {k for k, _c in gates.keyed_corrections(
        predicate=lambda c: c.scope != "match" and c.obs and c.agent)}
    got = {k for k, _c in _records(DEFAULT_ROOT, None)}
    assert got == want
    assert len(got) == len(want) > 300              # a plausible corpus, not an empty walk


@pytest.mark.req("REQ-GATE-0007")
def test_decider_lab_reader_ignores_retired_match_scope_records(tmp_path):
    """Issue #353: even a hand-written legacy match row must not enter the one-move Decision Gate."""
    from train.decider_lab import _records
    root = _store(tmp_path, [_rec(1, 3), _rec(2, 4, scope="match", subject=None)])
    assert [k for k, _c in _records(root, None)] == ["1|0|decision|3"]


# ── the Ruling Index — one query over every store a ruling can live in (ADR-0088, Issue #239) ──


def _reviewed(tmp_path, entries):
    """A `reviewed.json` ledger on disk, keyed the way that store keys — by ADR-0049's Scope subject
    (`review_key`), NOT by Frame Key. The two keyspaces differing is why the join lives in the walk."""
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
    """A refutation says the ruling was wrong; ``covered`` says it stands. Only the first can stop
    grading — reading the ledger as a skip-list would drop 112 ``covered`` frames out of the corpus."""
    root = _store(tmp_path / "corpus", [_rec(1, 3), _rec(2, 4)])
    led = _reviewed(tmp_path, {"1-3": {"disposition": "refuted", "reason": "forgoes a KO"},
                               "2-4": {"disposition": "covered", "reason": "already handled"}})
    index = gates.ruling_index(root, reviewed_path=led, fixtures_dir=tmp_path / "none")
    assert sorted(gates.voided_frames(index)) == ["1|0|decision|3"]
    assert index["2|0|decision|4"][0].disposition == "covered"


@pytest.mark.req("REQ-GATE-0010")
def test_a_transposition_voids_for_a_DIFFERENT_reason_than_a_refutation(tmp_path):
    """Both void; the readout must still say WHICH. ADR-0085 decision 4 cites `81905522-75`'s human
    pick, so recording that frame as ``refuted`` would contradict a shipped ADR."""
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
    """The two stores key differently and NEITHER derives from the other, so a translation written
    anywhere but inside the corpus walk is the hand-built key ADR-0087 decision 2 forbids."""
    root = _store(tmp_path / "corpus", [_rec(7, 51, seat=1),
                                        _rec(8, 82, seat=1, scope="turn", subject=8)])
    led = _reviewed(tmp_path, {"7-51": {"disposition": "refuted", "reason": "x"},
                               "8-t8s1": {"disposition": "refuted", "reason": "y"}})
    index = gates.ruling_index(root, reviewed_path=led, fixtures_dir=tmp_path / "none")
    assert sorted(gates.voided_frames(index)) == ["7|1|decision|51", "8|1|turn|8"]


@pytest.mark.req("REQ-GATE-0010")
def test_a_voiding_source_wins_over_a_non_voiding_one_and_both_are_retained(tmp_path):
    """A refutation is a strictly later, stronger act than a ``covered`` or a hold-out, so the weaker
    disposition must not win. Every ruling is retained, which makes this an index, not a skip-list."""
    root = _store(tmp_path / "corpus", [_rec(1, 3)])
    led = _reviewed(tmp_path, {"1-3": {"disposition": "refuted", "reason": "bad label"}})
    fixtures = _held_out_fixture(tmp_path / "fixtures", "1|0|decision|3")
    rulings = gates.ruling_index(root, reviewed_path=led, fixtures_dir=fixtures)["1|0|decision|3"]
    assert gates.voiding_ruling(rulings).disposition == "refuted"
    assert {r.source for r in rulings} == {"reviewed", "held_out"}


@pytest.mark.req("REQ-GATE-0010")
def test_a_held_out_ruling_alone_never_voids(tmp_path):
    """Holding a frame out of a gate's SCOPE is not disowning the ruling: if it voided, the Held-out
    Ledger frames would silently leave the agree rate too — a denominator change nobody ruled on."""
    root = _store(tmp_path / "corpus", [_rec(1, 3)])
    fixtures = _held_out_fixture(tmp_path / "fixtures", "1|0|decision|3")
    index = gates.ruling_index(root, reviewed_path=_reviewed(tmp_path, {}), fixtures_dir=fixtures)
    assert gates.voided_frames(index) == {}
    assert index["1|0|decision|3"][0].owner == "#165"


@pytest.mark.req("REQ-GATE-0010")
def test_an_unrecognised_disposition_is_non_voiding_and_reported_not_swallowed(tmp_path):
    """The loud path. An unknown word keeps grading (the safe direction) but must not be silent: a
    disposition nobody registered is a ruling nobody's grader is honouring."""
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
    """18 of 101 recorded disagreements carried a refuted label, so a build correcting one failed `main`
    as a REGRESSION. The row must still EXIST — only the verdict is excused."""
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
    """A re-ruling can flip one frame disagree→agree and exactly cancel a regression's agree→disagree.
    The rate legitimately does not move; what must not happen is the report implying nothing did."""
    before = _dcap([_drow("regressed", [1], [1]), _drow("reruled", [0], [9])])
    after = _dcap([_drow("regressed", [4], [1]), _drow("reruled", [0], [0])])
    delta = decider_lab_diff(before, after)["agree_delta"]
    assert delta["before"] == delta["after"] == (1, 2)     # the rate is genuinely unchanged...
    assert (delta["moved"], delta["reruled"]) == (1, 1)    # ...and the report says two things moved


@pytest.mark.req("REQ-GATE-0011")
def test_the_delta_restates_BOTH_sides_against_todays_voided_set():
    """The rulings are one corpus, not a property of a capture, so restating the baseline is what makes
    the delta legible instead of an unexplained denominator jump."""
    rows = [_drow("kept", [1], [1]), _drow("void", [0], [1])]
    delta = decider_lab_diff(_dcap(rows), _dcap(rows), voided={"void"})["agree_delta"]
    assert delta["before"] == delta["after"] == (1, 1)     # 1/2 -> 1/1 on BOTH sides
    assert delta["voided"] == 1


@pytest.mark.req("REQ-GATE-0011")
def test_an_unlabelled_or_unreplayable_frame_is_outside_the_delta_entirely():
    """Neither agreement nor disagreement, and neither is a void: counting either in the denominator
    would report the agent as wrong about a frame nobody asked it about."""
    rows = [_drow("ok", [1], [1]), _drow("unlabelled", [0], None), _drow("dead", None, [1])]
    delta = decider_lab_diff(_dcap(rows), _dcap(rows))["agree_delta"]
    assert delta["before"] == delta["after"] == (1, 1)


@pytest.mark.req("REQ-GATE-0011")
def test_the_leaf_delta_is_drawn_from_the_SAME_population_as_its_compared_count():
    """The trap `ruling_moves` already documents, re-checked one function along: two numbers in one
    report must describe one population."""
    unscorable = {"key": "u", "correct_is_top": None, "unscorable": True, "correct": [1]}
    rpt = _report([_row("s", "OK"), unscorable])
    d = leaf_lab_diff(rpt, rpt)
    assert d["compared"] == 1
    assert d["agree_delta"]["before"] == d["agree_delta"]["after"] == (1, 1)


# ── the committed corpus, read through the index ──────────────────────────────────────────────────


@pytest.mark.req("REQ-GATE-0010")
def test_every_disposition_in_the_committed_ledger_is_recognised_vocabulary():
    """Over the REAL ledger. Its absence is what let two dispositions sit unregistered — the file and
    the vocabulary drifting apart in silence is the defect, not either word."""
    assert gates.unrecognised_rulings(gates.ruling_index()) == []


@pytest.mark.req("REQ-GATE-0010")
def test_an_orphaned_ledger_entry_is_reported_rather_than_ruling_on_nothing(tmp_path):
    """A ledger key matching no committed Correction voids NOTHING, silently. Asserting it through the
    index is impossible by construction, so the join has to be walked from the LEDGER's side."""
    root = _store(tmp_path / "corpus", [_rec(1, 3)])
    led = _reviewed(tmp_path, {"1-3": {"disposition": "refuted", "reason": "real"},
                               "9-99": {"disposition": "refuted", "reason": "rules on nothing"}})
    index = gates.ruling_index(root, reviewed_path=led, fixtures_dir=tmp_path / "none")
    assert sorted(gates.voided_frames(index)) == ["1|0|decision|3"]      # the orphan voids nothing...
    assert [k for k, _e in gates.orphan_rulings(root, reviewed_path=led)] == ["9-99"]   # ...but is SEEN


@pytest.mark.req("REQ-GATE-0010")
def test_no_committed_ledger_entry_rules_on_nothing():
    """Over the REAL ledger, in its strongest form: ZERO entries rule on no committed Correction, which
    makes this the reachability guard for the whole ledger rather than a two-orphan assertion."""
    assert [k for k, _e in gates.orphan_rulings()] == []


@pytest.mark.req("REQ-GATE-0010")
def test_the_excused_split_prefers_the_held_out_label_when_a_frame_is_both():
    """One precedence, shared by both gates: a HELD-OUT ruling STANDS and is merely out of scope, while
    a voided one cannot grade at all. Written once, because both gates had the same comprehensions."""
    rows = [{"key": "both"}, {"key": "held"}, {"key": "void"}, {"key": "bare"}]
    gating, ruled, void_hits = gates.split_excused(
        rows, {"both": "#1", "held": "#1"}, {"both": object(), "void": object()})
    assert [r["key"] for r in gating] == ["bare"]
    assert [r["key"] for r in ruled] == ["both", "held"]
    assert [r["key"] for r in void_hits] == ["void"]


@pytest.mark.req("REQ-GATE-0010")
def test_the_transposition_frame_is_now_GRADED_and_SATISFIED_not_voided():
    """`81905522|0|decision|75` is GRADED again (ADR-0091 decision 3): the agent's index 1 and the
    human's index 3 are the same undamaged Riolu, so voiding would excuse a gradeable frame."""
    voided = gates.voided_frames(gates.ruling_index())
    assert "81905522|0|decision|75" not in voided, "the transposition entry is retired, not re-filed"
    assert voided["82749168|1|decision|38"].disposition == "refuted"

    equiv = gates.equivalence_index()["81905522|0|decision|75"]
    assert equiv[1] == equiv[3] and 1 in equiv[3], "the two Riolu are ONE decision"
    assert gates.satisfies_human([1], [3], equiv=equiv) is True
    assert gates.satisfies_human([1], [3]) is False, "and it took the oracle to see it"


def test_the_transposition_WORD_survives_with_no_corpus_entry_behind_it():
    """Decision 3 deletes the ENTRY and keeps the VOCABULARY: the oracle is sound only over what the
    snapshot reveals, so an equivalence turning on information outside `obs` stays unrecordable."""
    assert "transposition" in gates.VOIDING_DISPOSITIONS
    assert "transposition" in gates.RECOGNISED_DISPOSITIONS


def test_the_SECOND_instance_nobody_ruled_is_graded_correctly():
    """`86091728|0|decision|19` sat scored as a DISAGREEMENT the whole time — the same Energy onto
    either of two identical basics. Nobody ruled it, so only an oracle reading the board finds it."""
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
    """`train.gates` must stay loadable with NO DLL, and ADR-0091 decision 7 has it importing shipped
    code. A subprocess, because this process has almost certainly imported `cg` already."""
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


def test_ONE_pick_cannot_satisfy_TWO_ruled_cards_in_the_same_class():
    """A class widens WHICH option satisfies a ruled card; it must never let ONE pick satisfy two of
    them. Zero committed frames hit this today, so it is latent — which is why it needs a test."""
    equiv = {1: frozenset({1, 3}), 3: frozenset({1, 3})}
    assert satisfies_human([1], [1, 3], equiv=equiv) is False, "half the ruling is not the ruling"
    assert satisfies_human([1, 3], [1, 3], equiv=equiv) is True
    # and the widening it must still allow: two ruled cards in DIFFERENT classes
    two = {0: frozenset({0, 2}), 2: frozenset({0, 2}), 1: frozenset({1, 4}), 4: frozenset({1, 4})}
    assert satisfies_human([2, 4], [0, 1], equiv=two) is True, "each ruled card met by its own twin"


def test_the_diff_classifies_a_SIBLING_pick_as_neutral_not_a_regression():
    """A build moving from one member of a class to another has changed nothing the ruling can see:
    before the oracle that read as a REGRESSION and failed `main`, and it must now be NEUTRAL."""
    before = _report([{"key": "e|0|decision|1", "chosen": [3], "correct": [3], "context": 0}])
    after = _report([{"key": "e|0|decision|1", "chosen": [1], "correct": [3], "context": 0}])
    equiv = {"e|0|decision|1": {1: frozenset({1, 3}), 3: frozenset({1, 3})}}

    blind = gates.decider_lab_diff(before, after)
    assert [r["verdict"] for r in blind["rows"]] == ["REGRESSION"], "the defect, reproduced"

    aware = gates.decider_lab_diff(before, after, equiv=equiv)
    assert [r["verdict"] for r in aware["rows"]] == ["NEUTRAL"]
    assert gates.decision_gate_verdict(aware["rows"], held_out={}) is True


def test_the_diff_restates_BOTH_sides_against_one_equivalence_map():
    """The equivalence is a property of the CORPUS, not of a capture — an old baseline carries no
    `equiv` field, so reading the map off each side would grade the two halves under two oracles."""
    before = _report([{"key": "e|0|decision|1", "chosen": [1], "correct": [3], "context": 0}])
    after = _report([{"key": "e|0|decision|1", "chosen": [1], "correct": [3], "context": 0}])
    equiv = {"e|0|decision|1": {1: frozenset({1, 3}), 3: frozenset({1, 3})}}
    assert gates.decider_lab_diff(before, after)["agree_delta"]["before"] == (0, 1)
    aware = gates.decider_lab_diff(before, after, equiv=equiv)["agree_delta"]
    assert aware["before"] == (1, 1) and aware["after"] == (1, 1)


# ── a re-capture may not move a verdict without a ruling (ADR-0094) ───────────────────────────────
# Measured before building: the convention had never been broken, so this removes the reliance on it.


@pytest.mark.req("REQ-GATE-0012")
def test_a_recapture_moving_an_unruled_frame_in_the_fail_direction_is_refused():
    """The frame is OK in the outgoing baseline and MISS in the fresh capture with no ruling for it, so
    the write is REFUSED rather than silently making the MISS the new reference."""
    outgoing = _report([_row("84071010|0|decision|15", "OK")])
    fresh = _report([_row("84071010|0|decision|15", "MISS")])
    fail = [f["key"] for f in leaf_lab_diff(outgoing, fresh)["ok_to_miss"]]

    assert gates.unruled_recapture_moves(fail, index={}) == ["84071010|0|decision|15"]
    with pytest.raises(gates.RecaptureRefused):
        gates.refuse_unruled_recapture(fail, index={})


@pytest.mark.req("REQ-GATE-0012")
def test_a_recapture_moving_a_RULED_frame_is_allowed():
    """The legitimate path, and the whole reason this is a guard rather than a ban: once the human
    has ruled the flip in a wave packet, re-capturing is exactly what records that ruling."""
    fail = ["84071010|0|decision|15"]
    index = {"84071010|0|decision|15": (gates.Ruling(disposition="covered", source="reviewed"),)}
    assert gates.unruled_recapture_moves(fail, index=index) == []
    gates.refuse_unruled_recapture(fail, index=index)        # raises nothing


@pytest.mark.req("REQ-GATE-0012")
def test_a_held_out_or_voided_frame_needs_no_second_excuse():
    """`ruling_index` already folds the Held-out Ledger and the voiding dispositions in, so "carries a
    ruling" is ONE predicate; a second special case would be a second idea of what ruled means."""
    fail = ["a", "b"]
    index = {"a": (gates.Ruling(disposition="held_out", source="held_out", owner="#165"),),
             "b": (gates.Ruling(disposition="refuted", source="reviewed"),)}
    assert gates.unruled_recapture_moves(fail, index=index) == []


@pytest.mark.req("REQ-GATE-0012")
def test_an_improvement_and_a_brand_new_key_write_freely():
    """Only the FAIL direction is guarded. A capture that sharpens the leaf, or that covers a frame
    the outgoing baseline never held, is not something a human owes a ruling on."""
    outgoing = _report([_row("a", "MISS")])
    fresh = _report([_row("a", "OK"), _row("b", "MISS")])
    d = leaf_lab_diff(outgoing, fresh)
    assert [f["key"] for f in d["ok_to_miss"]] == []
    assert d["added"] == ["b"]
    gates.refuse_unruled_recapture([f["key"] for f in d["ok_to_miss"]], index={})


@pytest.mark.req("REQ-GATE-0012")
def test_the_refusal_names_EVERY_offending_key_not_just_the_first():
    """A refusal that named one key would be re-run N times, and the operator would learn the scope
    of what they were about to overwrite one frame at a time."""
    with pytest.raises(gates.RecaptureRefused) as exc:
        gates.refuse_unruled_recapture(["b", "a", "c"], index={"c": (gates.Ruling("covered", "reviewed"),)})
    assert exc.value.keys == ["a", "b"]                       # sorted, and the ruled one excused
    assert "a" in str(exc.value) and "b" in str(exc.value)


@pytest.mark.req("REQ-GATE-0012")
def test_the_decider_fail_direction_is_REGRESSION_not_any_movement():
    """The Decision Gate's fail direction is `satisfies_human` True → False, exactly the verdict
    `decider_lab_diff` already computes — reusing it stops two ideas of "worse" drifting apart."""
    before = _report([{"key": "e|0|decision|1", "chosen": [0], "correct": [0], "context": 0},
                      {"key": "e|0|decision|2", "chosen": [1], "correct": [0], "context": 0}])
    after = _report([{"key": "e|0|decision|1", "chosen": [1], "correct": [0], "context": 0},
                     {"key": "e|0|decision|2", "chosen": [2], "correct": [0], "context": 0}])
    diff = gates.decider_lab_diff(before, after)
    assert gates.decision_fail_keys(diff) == ["e|0|decision|1"]   # f2 moved, but was already wrong


@pytest.mark.req("REQ-GATE-0012")
def test_both_labs_read_their_fail_direction_through_a_NAMED_reader():
    """The two labs must be actually symmetric, not merely described as such: the first build left the
    leaf inlining its `ok_to_miss` comprehension at the call site."""
    leaf = leaf_lab_diff(_report([_row("a", "OK")]), _report([_row("a", "MISS")]))
    assert gates.discrimination_fail_keys(leaf) == ["a"]
    assert gates.discrimination_fail_keys({}) == []          # absent key, not a crash
    assert gates.decision_fail_keys({}) == []


@pytest.mark.req("REQ-GATE-0012")
def test_the_shared_guarded_capture_writes_refuses_and_never_half_writes(tmp_path):
    """Three behaviours in one shared seam: a FIRST capture writes freely, a clean re-capture writes,
    and a fail-direction move with no ruling returns 1 and leaves the artifact byte-identical."""
    out = tmp_path / "baseline.json"
    fresh_ok = _report([_row("a", "OK")])
    wrote = []

    # first capture — nothing to guard against
    rc = gates.guarded_capture(out, fresh_ok, index={}, diff_fn=leaf_lab_diff,
                               fail_keys_fn=gates.discrimination_fail_keys,
                               write=lambda: (wrote.append(1),
                                              gates.write_json_artifact(out, fresh_ok)))
    assert rc == 0 and wrote == [1]
    before_bytes = out.read_bytes()

    # a re-capture that degrades an UNRULED frame — refused, and the file is untouched
    rc = gates.guarded_capture(out, _report([_row("a", "MISS")]), index={}, diff_fn=leaf_lab_diff,
                               fail_keys_fn=gates.discrimination_fail_keys,
                               write=lambda: wrote.append(2))
    assert rc == 1 and wrote == [1]                          # `write` never ran
    assert out.read_bytes() == before_bytes                  # not even partially rewritten

    # the same degrade, once the frame carries a ruling — allowed
    rc = gates.guarded_capture(out, _report([_row("a", "MISS")]),
                               index={"a": (gates.Ruling("covered", "reviewed"),)},
                               diff_fn=leaf_lab_diff, fail_keys_fn=gates.discrimination_fail_keys,
                               write=lambda: wrote.append(3))
    assert rc == 0 and wrote == [1, 3]


@pytest.mark.req("REQ-GATE-0012")
def test_a_restamp_changes_the_recorded_revision_and_NOTHING_else(tmp_path):
    """Four of the twelve committed re-captures moved NOTHING but the recorded revision, and serving
    that through `capture` means re-reading the build to achieve a metadata edit — so they split."""
    art = tmp_path / "baseline.json"
    doc = {"git_rev": "e4c46ca", "agent": None, "n": 2,
           "rows": [_row("a", "OK"), _row("b", "MISS")]}
    gates.write_json_artifact(art, doc)

    gates.restamp_artifact(art, "a8da62d")

    after = json.loads(art.read_text(encoding="utf-8"))
    assert after["git_rev"] == "a8da62d"
    assert after["rows"] == doc["rows"] and after["n"] == 2
    assert CRLF not in art.read_bytes()                       # goes through the one LF-framed writer


@pytest.mark.req("REQ-GATE-0012")
def test_a_restamp_refuses_an_artifact_that_carries_no_revision(tmp_path):
    """Fail loud rather than inventing a field: an artifact with no `git_rev` is not a gate baseline,
    and silently adding one would make a re-stamp able to manufacture provenance."""
    art = tmp_path / "notabaseline.json"
    gates.write_json_artifact(art, {"rows": []})
    with pytest.raises(ValueError):
        gates.restamp_artifact(art, "a8da62d")
