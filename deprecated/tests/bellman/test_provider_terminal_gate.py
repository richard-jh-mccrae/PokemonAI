"""The lethal gate's per-action coverage hook on the search provider (moved with the hook)."""
from __future__ import annotations

from common import DecisionState, enumerate_legal_actions
from deprecated.bellman.providers import BellmanNativeProvider


def test_terminal_proof_abstains_when_attack_metadata_is_missing():
    observation = {
        "current": {"yourIndex": 0, "players": [{}, {}]},
        "select": {"context": 0, "minCount": 1, "maxCount": 1,
                   "option": [{"type": 13, "attackId": 999}]},
    }
    state = DecisionState.from_observation(observation, deck=(), deck_name="test")
    action = enumerate_legal_actions(observation)[0]
    provider = object.__new__(BellmanNativeProvider)
    provider.effects = None
    provider.stats = type("MissingStats", (), {"attack": lambda _self, _attack_id: None})()

    assert not provider.terminal_action_supported(state, action)


def test_terminal_proof_abstains_when_play_effect_metadata_is_missing():
    observation = {
        "current": {"yourIndex": 0, "players": [
            {"hand": [{"id": 999}], "active": [], "bench": []}, {}]},
        "select": {"context": 0, "minCount": 1, "maxCount": 1,
                   "option": [{"type": 7, "index": 0}]},
    }
    state = DecisionState.from_observation(observation, deck=(), deck_name="test")
    action = enumerate_legal_actions(observation)[0]
    provider = object.__new__(BellmanNativeProvider)
    provider.effects = None
    provider.stats = type("TrainerStats", (), {
        "get": lambda _self, _card_id: type("Trainer", (), {"is_pokemon": False})(),
    })()

    assert not provider.terminal_action_supported(state, action)


def test_terminal_proof_resolves_the_engine_shaped_ability_source():
    # The deployed engine emits every option key, unused ones None — `inPlayArea: None` must not
    # shadow the `area` reference the ability actually carries (the PR #532 shape).
    from observation_helpers import engine_opt

    observation = {
        "current": {"yourIndex": 0, "players": [
            {"hand": [], "active": [{"id": 112}], "bench": []}, {}]},
        "select": {"context": 0, "minCount": 1, "maxCount": 1,
                   "option": [engine_opt(type=10, area=4, index=0)]},
    }
    state = DecisionState.from_observation(observation, deck=(), deck_name="test")
    action = enumerate_legal_actions(observation)[0]
    provider = object.__new__(BellmanNativeProvider)
    provider.effects = type("Effects", (), {
        "clauses": lambda _self, _card_id: ({"kind": "heal"},),
        "fully_covers": lambda _self, card_id: card_id == 112,
    })()
    provider.stats = type("Stats", (), {"get": lambda _self, _card_id: None})()

    assert provider.terminal_action_supported(state, action)


def test_terminal_proof_abstains_when_attach_trigger_metadata_is_missing():
    observation = {
        "current": {"yourIndex": 0, "players": [
            {"hand": [{"id": 999}], "active": [{"id": 1000}], "bench": []}, {}]},
        "select": {"context": 0, "minCount": 1, "maxCount": 1,
                   "option": [{"type": 8, "index": 0,
                               "inPlayArea": 4, "inPlayIndex": 0}]},
    }
    state = DecisionState.from_observation(observation, deck=(), deck_name="test")
    action = enumerate_legal_actions(observation)[0]
    provider = object.__new__(BellmanNativeProvider)
    provider.effects = None
    provider.stats = type("SpecialEnergyStats", (), {
        "get": lambda _self, card_id: type("Stat", (), {
            "is_basic_energy": False, "hasAbility": card_id == 1000,
        })(),
    })()

    assert not provider.terminal_action_supported(state, action)
