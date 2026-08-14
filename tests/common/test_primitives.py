from __future__ import annotations

import json

from common import DecisionState, RootDecision
from common.board_cards import body_card_ids
from common.card_worth import ACE_SPEC_TIER, ENERGY_TIER, ROLE_TIER, role_value
from common.option_equivalence import class_representatives, fan_out
from common.strategy import PrizePlan, Roles, Strategy
from common.telemetry import to_record


def test_declarative_roles_derive_a_complete_evolution_line():
    roles = Roles({12: ["win_condition", "primary_attacker"]},
                  evolves={10: 11, 11: 12}, ready={12: 2})
    strategy = Strategy(name="test", roles=roles, prize_plan=PrizePlan([[12, 12]]))
    assert roles[10] == ["win_condition_base"]
    assert strategy.lines[0].path == (10, 11, 12)
    assert strategy.lines[0].ready.energy == 2
    assert strategy.prize_plan.prizes_to_win == 6


def test_portable_worth_is_independent_of_a_legacy_value_stack():
    assert role_value(["win_condition", "engine"]) == ROLE_TIER["win_condition"]
    assert role_value([], is_typed_basic_energy=True) == ENERGY_TIER
    assert role_value(["engine"], is_ace_spec=True) == ACE_SPEC_TIER
    assert role_value([]) == 0.0


def test_board_card_walk_uses_attached_cards_not_energy_units():
    body = {"id": 10, "energies": [0, 0, 6],
            "energyCards": [{"id": 17}, {"id": 20}],
            "tools": [{"id": 1250}], "preEvolution": [{"id": 9}]}
    assert list(body_card_ids(body)) == [10, 17, 20, 1250, 9]


def test_option_equivalence_helpers_preserve_the_best_member():
    classes = {1: frozenset({1, 3}), 3: frozenset({1, 3})}
    assert class_representatives(classes, 5) == [0, 1, 2, 4]
    assert fan_out([5.0, 10.0, None, 7.0], classes) == [5.0, 10.0, None, 10.0]


def test_telemetry_exposes_only_the_bellman_decision_contract():
    decision = RootDecision((2,), None, 3.5, True, {"backend": "test"})
    record = to_record(decision)
    assert record == {
        "bellman": True, "chosen": [2], "action": None, "value": 3.5,
        "complete": True, "diagnostics": {"backend": "test"}, "belief": None,
    }


def test_telemetry_records_whole_decision_duration():
    decision = RootDecision((2,), None, 3.5, True, {"backend": "test"})

    record = to_record(decision, decision_seconds=0.125)

    assert record["decision_seconds"] == 0.125


def test_search_session_resume_blob_is_not_part_of_plan_suffix_identity():
    observation = {"current": {"yourIndex": 0, "players": []}, "search_begin_input": "opaque"}
    without_blob = {"current": {"yourIndex": 0, "players": []}}

    with_blob = DecisionState.from_observation(observation, deck=(), deck_name="test")
    without_blob = DecisionState.from_observation(without_blob, deck=(), deck_name="test")

    assert with_blob.semantic_key != without_blob.semantic_key
    assert with_blob.plan_key == without_blob.plan_key


def test_live_telemetry_compacts_paths_without_losing_family_evidence():
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
        "needs": {
            "focused": [{"action_key": "focus", "family": "attachment", "score": 0.8,
                         "reason": "need_path", "path_ids": ["path"] * 100}],
            "safety": [],
            "unknown": [{"action_key": "unknown", "card_id": 999, "context": 0,
                         "reason": "no_need_capability"}],
            "paths": [{"large": "x" * 10_000}] * 20,
            "features": [{"outcome": "take_prize", "deadline": 0}],
            "elapsed_ms": 2.0, "exhausted": False,
        },
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
    needs = record["diagnostics"]["needs"]
    assert needs["path_count"] == 20
    assert needs["focused"][0]["path_count"] == 100
    assert needs["unknown"][0]["card_id"] == 999
