from __future__ import annotations

import json

from common import RootDecision
from common.observation import ObservationStateBuilder
from deprecated.bellman.telemetry import to_record


def test_bellman_telemetry_exposes_only_the_teacher_contract():
    decision = RootDecision((2,), None, 3.5, True, {"backend": "test"})

    assert to_record(decision) == {
        "bellman": True, "chosen": [2], "action": None, "value": 3.5,
        "complete": True, "diagnostics": {"backend": "test"}, "belief": None,
    }


def test_bellman_telemetry_records_whole_decision_duration():
    decision = RootDecision((2,), None, 3.5, True, {"backend": "test"})

    assert to_record(decision, decision_seconds=0.125)["decision_seconds"] == 0.125


def test_bellman_telemetry_persists_the_observation_record():
    state = ObservationStateBuilder().root({
        "select": None, "logs": [], "current": {
            "yourIndex": 0, "turn": 1, "firstPlayer": 0, "supporterPlayed": False,
            "stadiumPlayed": False, "energyAttached": False, "retreated": False,
            "result": None, "stadium": [], "looking": None, "players": [
                {"active": [], "bench": [], "hand": [], "handCount": 0,
                 "discard": [], "prize": [], "deckCount": 0, "benchMax": 5,
                 "poisoned": False, "burned": False, "asleep": False,
                 "paralyzed": False, "confused": False},
                {"active": [], "bench": [], "hand": None, "handCount": 0,
                 "discard": [], "prize": [], "deckCount": 0, "benchMax": 5,
                 "poisoned": False, "burned": False, "asleep": False,
                 "paralyzed": False, "confused": False}],
        }})
    decision = RootDecision((0,), None, 0.0, True, {})

    record = to_record(decision, state=state)

    assert record["observation_record"]["schema_version"] == 1
    assert record["observation_record"]["payload"]["$type"] == "ObservationState"


def test_bellman_telemetry_compacts_production_evidence():
    candidate = {
        "action": "ActionIdentity(kind='attach', parts=('" + "x" * 10_000 + "',))",
        "family": "attachment", "features": {"ready": 1.0},
        "contributions": {"ready": 2.5}, "score": 2.5, "gap": 0.0,
        "wave": 0, "status": "leader", "shadow": True,
    }
    decision = RootDecision((2,), None, 3.5, True, {
        "backend": "test",
        "root": {"chosen_key": candidate["action"], "nodes": 12, "cache_hits": 3,
                 "stopped_reason": "complete", "alternatives": [candidate] * 20},
        "production": {"family_candidates": [candidate], "structural_prunes": [{
            "proof_type": "commutativity", "pruned": candidate["action"],
            "retained_event": "attach:active",
        }]},
    })

    record = to_record(decision, compact=True)
    evidence = record["diagnostics"]["production"]["family_candidates"]

    assert len(json.dumps(record)) < 2_000
    assert evidence == [{
        "action_key": evidence[0]["action_key"], "family": "attachment",
        "features": {"ready": 1.0}, "contributions": {"ready": 2.5},
        "score": 2.5, "gap": 0.0, "wave": 0, "status": "leader", "shadow": True,
    }]
    assert len(evidence[0]["action_key"]) == 20
    assert record["diagnostics"]["production"]["structural_prunes"] == [{
        "proof_type": "commutativity", "retained_event": "attach:active",
        "pruned_key": evidence[0]["action_key"],
    }]
