"""The two deterministic merge gates for a mid-build decider swap (ADR-0072, #167).

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

from train import gates
from train.gates import (EVOLVE_LANE, OWNER_RE, RULED_RE, AxisClaim, DecisionClaim, EndorsementClaim,
                         decision_gate_verdict, discrimination_gate_verdict, evaluate_axis_claim,
                         evaluate_decision_claim, evaluate_endorsement_claim, held_out_owner,
                         lane_slots, leaf_lab_diff, option_slot, parse_claims,
                         decider_lab_diff, decision_gate_verdict)

# ── slot resolution — the shared basis both sweeps and Axis Claims compare on ─────────────────────


@pytest.mark.req("REQ-TRAIN-0040")
def test_lane_constants_match_the_engine_enums():
    """CLAUDE.md: engine vocabulary (option types, select contexts) comes from `src/cg/api.py`, never
    from memory. But importing `cg.api` MAPS THE NATIVE LIBRARY (`libcg` shows up in /proc/self/maps
    on a bare import), and `train.gates` must stay loadable with no DLL — the same reason
    `planner.py` keeps its engine import lazy. So the lane constants are written literally there and
    PINNED here: this test is what makes them sourced rather than remembered, and it fails the moment
    one drifts."""
    from cg.api import OptionType, SelectContext
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
    `correct` names the card the RULING was about, not the whole legal answer. That mismatch is why
    context 8 reads 1/12 agreement and why the per-context agree rate is not meaningful for
    multi-pick contexts — the movement detection is, which is what actually gates.
    """
    before = _dcap([_drow("k", [0, 2], [0, 2], context=8)])
    after = _dcap([_drow("k", [2, 0], [0, 2], context=8)])
    assert decider_lab_diff(before, after)["rows"] == [], "order is not a decision"
    # a genuine change to the SET is still caught
    moved = _dcap([_drow("k", [2, 4], [0, 2], context=8)])
    assert [r["verdict"] for r in decider_lab_diff(before, moved)["rows"]] == ["REGRESSION"]
