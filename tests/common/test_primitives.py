from __future__ import annotations

from deprecated.bellman.state import DecisionState
from common.option_equivalence import (
    class_representatives, fan_out, fingerprint_source_card_id, option_in_play_source_id,
    option_source_card, semantic_option_fingerprint,
)
from common.strategy import Roles
from observation_helpers import engine_opt


def test_roles_resolve_reads_store_defaults_and_deck_overrides():
    roles = Roles({121: ["primary_attacker"]}).resolve((119, 120, 121))

    assert roles[119] == ["primary_attacker"]
    assert roles[120] == ["primary_attacker", "draw_engine"]
    assert roles[121] == ["primary_attacker"]


def test_option_equivalence_helpers_preserve_the_best_member():
    classes = {1: frozenset({1, 3}), 3: frozenset({1, 3})}
    assert class_representatives(classes, 5) == [0, 1, 2, 4]
    assert fan_out([5.0, 10.0, None, 7.0], classes) == [5.0, 10.0, None, 10.0]


#: A real main-menu Play shape; omitted fields once masked `option_source_card` failures.
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


def test_search_session_resume_blob_is_not_part_of_plan_suffix_identity():
    observation = {"current": {"yourIndex": 0, "players": []}, "search_begin_input": "opaque"}
    without_blob = {"current": {"yourIndex": 0, "players": []}}

    with_blob = DecisionState.from_observation(observation, deck=(), deck_name="test")
    without_blob = DecisionState.from_observation(without_blob, deck=(), deck_name="test")

    assert with_blob.semantic_key != without_blob.semantic_key
    assert with_blob.plan_key == without_blob.plan_key
