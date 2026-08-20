from __future__ import annotations

import json

from common import RootDecision
from deprecated.bellman.state import DecisionState
from common.board_cards import body_card_ids
from common.card_worth import ACE_SPEC_TIER, ENERGY_TIER, ROLE_TIER, function_role, role_value
from common.option_equivalence import (
    class_representatives, fan_out, fingerprint_source_card_id, option_in_play_source_id,
    option_source_card, semantic_option_fingerprint,
)
from common.strategy import PrizePlan, Roles, Strategy
from common.telemetry import to_record
from observation_helpers import engine_opt


def test_declarative_roles_derive_a_complete_evolution_line():
    roles = Roles({12: ["primary_attacker"]},
                  evolves={10: 11, 11: 12}, ready={12: 2})
    strategy = Strategy(name="test", roles=roles, prize_plan=PrizePlan([[12, 12]]))
    assert 10 not in roles
    assert strategy.lines[0].path == (10, 11, 12)
    assert strategy.lines[0].ready.energy == 2
    assert strategy.prize_plan.prizes_to_win == 6


def test_roles_resolve_reads_the_store_records_across_an_evolution_line():
    # Dreepy 119 -> Drakloak 120 -> Dragapult ex 121: ancestry from `evolves_from`, roles
    # from authored `default_roles`, and a deck declaration REPLACING the payoff's default.
    roles = Roles({121: ["primary_attacker"]}, ready={121: 2}).resolve((119, 120, 121))

    assert roles.evolves == {119: 120, 120: 121}
    assert roles[119] == ["primary_attacker"]
    assert roles[120] == ["primary_attacker", "draw_engine"]
    assert roles[121] == ["primary_attacker"]        # declared, so the authored sniper is gone
    assert roles.lines[0].path == (119, 120, 121)


def test_portable_worth_is_independent_of_a_legacy_value_stack():
    assert role_value(["primary_attacker", "engine"]) == ROLE_TIER["primary_attacker"]
    assert role_value([], is_typed_basic_energy=True) == ENERGY_TIER
    assert role_value(["engine"], is_ace_spec=True) == ACE_SPEC_TIER
    assert role_value([]) == 0.0
    assert role_value(["primary_attacker"]) > role_value(["support_pokemon"])


def test_intrinsic_card_functions_resolve_to_general_roles():
    assert function_role(("search", "tutor_pokemon")) == "tutor"
    assert function_role(("energy_denial", "coin")) == "disruption"
    assert function_role(("draw", "dig")) is None


def test_board_card_walk_uses_attached_cards_not_energy_units():
    body = {"id": 10, "energies": [0, 0, 6],
            "energyCards": [{"id": 17}, {"id": 20}],
            "tools": [{"id": 1250}], "preEvolution": [{"id": 9}]}
    assert list(body_card_ids(body)) == [10, 17, 20, 1250, 9]


def test_option_equivalence_helpers_preserve_the_best_member():
    classes = {1: frozenset({1, 3}), 3: frozenset({1, 3})}
    assert class_representatives(classes, 5) == [0, 1, 2, 4]
    assert fan_out([5.0, 10.0, None, 7.0], classes) == [5.0, 10.0, None, 10.0]


#: A main-menu Play exactly as `cg.game` emits it: EVERY field present, unused ones ``None``. A
#: hand-written ``{"type": 7, "index": 1}`` omits `area` and so exercises a shape the engine never
#: produces — the gap that let `option_source_card` return None for every real Play.
ENGINE_PLAY_OPTION = {
    "area": None, "attackId": None, "cardId": None, "count": None, "energyIndex": None,
    "inPlayArea": None, "inPlayIndex": None, "index": 1, "number": None, "playerIndex": None,
    "serial": None, "specialConditionType": None, "toolIndex": None, "type": 7,
}


def test_option_source_card_resolves_the_engine_shaped_main_menu_play():
    frame = {"current": {"yourIndex": 0, "players": [
        {"hand": [{"id": 500, "serial": 1}, {"id": 1223, "serial": 2}]},
        {"hand": None},
    ]}}

    card = option_source_card(ENGINE_PLAY_OPTION, frame)

    assert card == {"id": 1223, "serial": 2}          # the bare `index` IS a hand slot
    assert option_source_card({**ENGINE_PLAY_OPTION, "index": 9}, frame) is None   # off the end
    # Not a Play: a null area stays unresolvable rather than being guessed as HAND.
    assert option_source_card({**ENGINE_PLAY_OPTION, "type": 9}, frame) is None


#: The board for every in-play source-resolution test below.
IN_PLAY_FRAME = {"current": {"yourIndex": 0, "players": [
    {"active": [{"id": 112, "serial": 7}], "bench": [{"id": 674, "serial": 8}]},
    {"active": [{"id": 999, "serial": 9}], "bench": []},
], "stadium": [{"id": 1260, "serial": 3, "playerIndex": 0}]}}


def test_in_play_source_resolves_the_engine_shaped_ability_option():
    # The engine emits `inPlayArea: None` on an ability that carries its reference in `area` —
    # a `get("inPlayArea", option.get("area"))` fallback never fires on that shape (PR #532 class).
    assert option_in_play_source_id(engine_opt(type=10, area=4, index=0), IN_PLAY_FRAME) == 112
    assert option_in_play_source_id(engine_opt(type=10, area=5, index=0), IN_PLAY_FRAME) == 674
    assert option_in_play_source_id(engine_opt(type=10, area=7, index=0), IN_PLAY_FRAME) == 1260


def test_in_play_source_prefers_the_explicit_card_and_fails_closed():
    assert option_in_play_source_id(engine_opt(type=15, cardId=678), IN_PLAY_FRAME) == 678
    # A materialized reference that does not resolve is None — never a guess from the other pair.
    assert option_in_play_source_id(engine_opt(type=10, area=4, index=5), IN_PLAY_FRAME) is None
    assert option_in_play_source_id(engine_opt(type=10), IN_PLAY_FRAME) is None
    assert option_in_play_source_id(None, IN_PLAY_FRAME) is None
    # The sparse cgpy shape (keys absent instead of None) resolves identically.
    assert option_in_play_source_id({"type": 10, "area": 4, "index": 0}, IN_PLAY_FRAME) == 112


def test_two_attachments_on_one_body_are_two_decisions():
    from common.option_equivalence import option_fingerprint

    frame = {"current": {"yourIndex": 0, "players": [
        {"active": [{"id": 700, "serial": 1,
                     "energyCards": [{"id": 3, "serial": 2}, {"id": 5, "serial": 4}]}]},
        {},
    ]}}
    fire = {"type": 5, "area": 4, "index": 0, "playerIndex": 0, "energyIndex": 0}
    water = {"type": 5, "area": 4, "index": 0, "playerIndex": 0, "energyIndex": 1}

    assert option_fingerprint(fire, frame) != option_fingerprint(water, frame)


def test_fingerprint_source_card_id_reads_the_embedded_reference():
    ability_part = semantic_option_fingerprint(engine_opt(type=10, area=4, index=0), IN_PLAY_FRAME)
    skill_part = semantic_option_fingerprint(engine_opt(type=15, cardId=678), IN_PLAY_FRAME)

    assert fingerprint_source_card_id(ability_part, IN_PLAY_FRAME) == 112
    assert fingerprint_source_card_id(skill_part, IN_PLAY_FRAME) == 678
    assert fingerprint_source_card_id(None, IN_PLAY_FRAME) is None
    assert fingerprint_source_card_id("not json", IN_PLAY_FRAME) is None


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
        "strategy_beam": {
            "focused": [{"action_key": "focus", "family": "attachment", "score": 0.8,
                         "reason": "strategy_hint", "path_ids": ["path"] * 100}],
            "safety": [],
            "unknown": [{"action_key": "unknown", "card_id": 999, "context": 0,
                         "reason": "no_strategy_hint"}],
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
    strategy_beam = record["diagnostics"]["strategy_beam"]
    assert strategy_beam["path_count"] == 20
    assert strategy_beam["focused"][0]["path_count"] == 100
    assert strategy_beam["unknown"][0]["card_id"] == 999
