"""The develop-rung correction classifier (Phase 3 consumer, `docs/plans/phase3-tooling.md`).

A turn-scope Correction carrying a `turn_plan` note is a develop-rung correction. `classify_develop_
correction` reads its live trace (`plan_candidates`, `planned`, `opts[correct].fired`) and the note,
and returns the machine verdict a blunder-buster leaf routes on: whether the rung was right, mis-ranked
the leaf, was inactive, or the note is prose-only — plus the rules the human's pick leans on (derived
from `fired`, never typed) and whether the human's reasoning is cross-turn (beyond the within-turn leaf).
"""
from types import SimpleNamespace

import pytest

from train.tuner.develop import classify_develop_correction


def _corr(*, correct, live_trace, turn_plan=None, rationale=""):
    return SimpleNamespace(correct=correct, live_trace=live_trace,
                           turn_plan=turn_plan or {}, rationale=rationale, scope="turn")


@pytest.mark.req("REQ-TUNER-0018")
def test_leaf_misrank_when_the_rung_overrode_the_human_pick():
    """The gold case (dragapult ep86090164): the rung fired and committed [2]@65, but the human wants
    [0]@50 — the greedy pick. The rung mis-ranked the leaf (picked a higher-valued board the human
    rejects), and it overrode greedy. Verdict = leaf-misrank, diverged, with the committed vs correct
    values and the rules [0] leans on."""
    lt = {"chosen": [2],
          "planned": {"step": [2], "goal": "develop", "value": 65.0, "diverged": True},
          "plan_candidates": [
              {"step": [2], "value": 65.0, "committed": True},
              {"step": [3], "value": 65.0},
              {"step": [0], "value": 50.0, "greedy": True}],
          "opts": [{"i": 0, "fired": [["power-up-attacker", 18.0],
                                      ["prefer-active-attach-in-setup", 8], ["attach-energy-last", -2.0]]}]}
    v = classify_develop_correction(_corr(correct=[0], live_trace=lt,
                                          turn_plan={"intended_line": "attach to dreepy"}))
    assert v["kind"] == "leaf-misrank"
    assert v["committed"] == [2] and v["committed_value"] == 65.0
    assert v["correct_value"] == 50.0                       # from the greedy candidate
    assert v["diverged"] is True
    assert v["overrode_greedy"] is True                    # correct == the greedy pick the rung beat
    assert v["leans_on_rule"] == ["power-up-attacker", "prefer-active-attach-in-setup"]  # positive only


@pytest.mark.req("REQ-TUNER-0018")
def test_rung_right_is_a_retire_candidate():
    """When the rung committed the human's `correct` pick, it reproduced what the tuned rules would —
    a rule-retirement datum: the rules `correct` leans on are candidates (confirmed by the R-off run)."""
    lt = {"planned": {"step": [1], "goal": "develop", "value": 70.0, "diverged": False},
          "plan_candidates": [{"step": [1], "value": 70.0, "committed": True, "greedy": True}],
          "opts": [{"i": 1, "fired": [["prefer-bench-fill-first", 12.0]]}]}
    v = classify_develop_correction(_corr(correct=[1], live_trace=lt))
    assert v["kind"] == "rung-right"
    assert v["route"] == "retire-candidate"
    assert v["leans_on_rule"] == ["prefer-bench-fill-first"]


@pytest.mark.req("REQ-TUNER-0018")
def test_rung_inactive_when_no_develop_line_was_committed():
    """No develop `planned` / no `plan_candidates` → the rung did not fire (greedy or a higher rung
    drove the pick). Routes to the existing turn-scope planner-code logic, not the develop leaf."""
    lt = {"chosen": [25], "planned": None, "opts": [{"i": 1, "fired": []}]}
    v = classify_develop_correction(_corr(correct=[1], live_trace=lt))
    assert v["kind"] == "rung-inactive"
    assert v["route"] == "planner-code"


@pytest.mark.req("REQ-TUNER-0018")
def test_no_prescription_for_a_prose_only_turn_tag():
    """A turn tag with no `correct` option is prose-only — nothing to compare against the rung."""
    v = classify_develop_correction(_corr(correct=[], live_trace={"planned": None},
                                          turn_plan={"intended_line": "attach to Munkidori"}))
    assert v["kind"] == "no-prescription"
    assert v["route"] == "prose"


@pytest.mark.req("REQ-TUNER-0018")
def test_within_turn_leaf_misrank_routes_to_leaf_tune():
    """A leaf mis-rank whose reasoning is WITHIN this turn (no cross-turn marker) is fixable by the
    leaf — routes to leaf-tune, not capability-gap."""
    lt = {"planned": {"step": [2], "goal": "develop", "value": 60.0, "diverged": True},
          "plan_candidates": [{"step": [2], "value": 60.0, "committed": True},
                              {"step": [0], "value": 55.0, "greedy": True}],
          "opts": [{"i": 0, "fired": [["concentrate-energy-on-wincon", 16.0]]}]}
    v = classify_develop_correction(_corr(correct=[0], live_trace=lt,
                                          turn_plan={"intended_line": "put the energy on the wincon now"}))
    assert v["kind"] == "leaf-misrank"
    assert v["route"] == "leaf-tune"
    assert v["cross_turn"] is False


def _build_turn_corr(live_trace, turn_plan, correct):
    """A real turn-scope Correction via build_correction, for the propose_hypothesis wiring test."""
    from train.blunder.correction import build_correction
    from train.blunder.decisions import Decision
    d = Decision(episode_id=1, frame=5, seat=0, turn=3, select_context="Main", select_type="Main",
                 options=[{"type": 0}, {"type": 0}, {"type": 0}], chosen=[2], current={})
    return build_correction(d, source="own", agent="dragapult_ex", correct=correct,
                            category="sequencing_error", rationale="", scope="turn",
                            live_trace=live_trace, turn_plan=turn_plan)


@pytest.mark.req("REQ-TUNER-0018")
def test_proposal_carries_the_develop_class_for_a_turn_plan_correction():
    """The Phase-3 wiring: a turn_plan correction's proposal carries the develop-rung verdict so a
    blunder-buster leaf routes on it. A non-turn-plan correction carries None (sparse)."""
    from train.tuner.propose import propose_hypothesis
    lt = {"planned": {"step": [2], "goal": "develop", "value": 65.0, "diverged": True},
          "plan_candidates": [{"step": [2], "value": 65.0, "committed": True},
                              {"step": [0], "value": 50.0, "greedy": True}],
          "opts": [{"i": 0, "fired": [["power-up-attacker", 18.0]]}]}
    p = propose_hypothesis(_build_turn_corr(lt, {"intended_line": "attach now"}, [0]))
    assert p.develop_class is not None
    assert p.develop_class["kind"] == "leaf-misrank"


@pytest.mark.req("REQ-TUNER-0018")
def test_batch_report_buckets_retire_corroboration_and_leaf_fodder():
    """The Phase-3 aggregate: rung-right corrections corroborate a rule's retirement (rung reproduced
    its pick); leaf-misranks are leaf/gate fodder. A cross-turn leaf-misrank is a capability-gap, not
    a leaf tune. Prose/inactive are counted but routed elsewhere."""
    from train.tuner.develop import develop_batch_report
    right = _corr(correct=[1], turn_plan={"intended_line": "bench the second basic"}, live_trace={
        "planned": {"step": [1], "goal": "develop", "value": 70.0},
        "plan_candidates": [{"step": [1], "value": 70.0, "committed": True, "greedy": True}],
        "opts": [{"i": 1, "fired": [["prefer-bench-fill-first", 12.0]]}]})
    misrank = _corr(correct=[0], live_trace={
        "planned": {"step": [2], "goal": "develop", "value": 60.0, "diverged": True},
        "plan_candidates": [{"step": [2], "value": 60.0, "committed": True},
                            {"step": [0], "value": 55.0, "greedy": True}],
        "opts": [{"i": 0, "fired": [["concentrate-energy-on-wincon", 16.0]]}]},
        turn_plan={"intended_line": "energy on the wincon now"})
    cross = _corr(correct=[0], live_trace=misrank.live_trace,
                  turn_plan={"intended_line": "save it — evolve next turn"})
    prose = _corr(correct=[], live_trace={"planned": None},
                  turn_plan={"intended_line": "attach to Munkidori and KO Budew"})
    rpt = develop_batch_report([right, misrank, cross, prose])
    assert rpt["counts"]["rung-right"] == 1
    assert rpt["retire_corroboration"] == {"prefer-bench-fill-first": 1}
    assert rpt["counts"]["leaf-misrank"] == 2
    assert len(rpt["capability_gaps"]) == 1               # the cross-turn one
    assert len(rpt["leaf_tune"]) == 1                     # the within-turn one
    assert rpt["counts"]["no-prescription"] == 1
