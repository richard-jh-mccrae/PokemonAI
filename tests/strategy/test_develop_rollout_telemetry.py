"""Develop-rollout telemetry (develop-rung Phase 1, ``docs/plans/turn-planner-develop-rung.md``).

A rollout that emits only its winning pick is un-debuggable — a correction reader can't tell whether
the rung chose wrong or the *leaf value* mis-ranked. So a develop-rollout Decision must emit the
RANKING: the ``planned`` block gains its leaf ``value``, and a sparse ``plan_candidates`` list carries
the top-K end-boards it valued, sorted by value desc, with the committed and greedy picks flagged.

Sparse discipline (the invariant that keeps the rung shippable default-OFF): when the rung didn't
fire, ``plan_candidates`` is absent and a non-develop ``planned`` block is byte-identical to today.
Verified through the wire contract ``telemetry.to_record`` — what the tuner / blunder-buster read.
"""
import pytest

from common.pilot import Decision, OptionTrace
from common.strategy import Plan
from common.strategy.planner import TurnLine
from common.telemetry import to_record


def _opt(index, score):
    return OptionTrace(index=index, score=score, plan=Plan.SETUP, card_id=None, fired=[])


def _candidates():
    return [
        {"step": [2], "value": 55.0, "why": "attach on the wincon line", "committed": True},
        {"step": [1], "value": 40.0, "why": "bench a second basic"},
        {"step": [0], "value": 30.0, "why": "attack into empty bench", "greedy": True},
    ]


@pytest.mark.req("REQ-PLANNER-0012")
def test_develop_decision_emits_the_ranked_candidates_and_value():
    """A develop-rollout Decision serialises the full ranking: ``plan_candidates`` present, sorted by
    value desc, with the committed pick and the greedy pick each flagged, and the committed leaf
    ``value`` on the ``planned`` block."""
    planned = TurnLine(next_step=[2], goal="develop", value=55.0, rationale="attach on the wincon line",
                       ranked_by="engine", diverged=True)
    rec = to_record(Decision(chosen=[2], options=[_opt(0, 5.0), _opt(1, 4.0), _opt(2, 3.0)],
                             planned=planned, plan_candidates=_candidates()))
    pc = rec["plan_candidates"]
    assert [c["value"] for c in pc] == sorted((c["value"] for c in pc), reverse=True)   # sorted desc
    assert next(c for c in pc if c.get("committed"))["step"] == [2]                     # committed flagged
    assert next(c for c in pc if c.get("greedy"))["step"] == [0]                        # greedy flagged
    assert rec["planned"]["value"] == 55.0                                             # committed leaf value
    assert rec["planned"]["goal"] == "develop"


@pytest.mark.req("REQ-PLANNER-0012")
def test_non_develop_record_is_byte_identical_when_the_rung_did_not_fire():
    """Sparse invariant: a Decision with no ``plan_candidates`` emits no such key, and a non-develop
    ``planned`` block carries no ``value`` — byte-identical to the pre-rung wire format."""
    planned = TurnLine(next_step=[1], goal="ko_for_prizes", value=1200.0, rationale="ko for prizes")
    rec = to_record(Decision(chosen=[1], options=[_opt(0, 5.0), _opt(1, 9.0)], planned=planned))
    assert "plan_candidates" not in rec
    assert "value" not in rec["planned"]                # non-develop planned block unchanged
    assert set(rec["planned"]) == {"step", "goal", "why"}
