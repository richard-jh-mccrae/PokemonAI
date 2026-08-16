from pathlib import Path
import json

from agents.dragapult_ex.strategy import STRATEGY
from agents.dragapult_ex.potential import DragapultPotential
from common.cards import CardFunctions
from common.effects import CardEffects
from common.value import ValueRegistry
from common.scouting.provider import EngineCardStatProvider
from common.strategy.strategies import (
    GENERAL_STRATEGIES, activate_strategies, general_card_strategies, resolve_strategies,
)


REPO = Path(__file__).resolve().parents[2]
POKEMON = {66, 112, 119, 120, 121, 140, 235, 305, 1071}
TRAINERS = {1080, 1086, 1097, 1120, 1121, 1152, 1182, 1198, 1213, 1227, 1240, 1260}
SPECIAL_POKEMON = POKEMON - {119}


def _deck():
    return tuple(int(row) for row in (
        REPO / "src" / "agents" / "dragapult_ex" / "deck.csv"
    ).read_text().splitlines())


def test_every_dragapult_card_has_machine_readable_purpose():
    stats = EngineCardStatProvider()
    functions = CardFunctions.load()
    effects = CardEffects.load()
    roles = STRATEGY.roles.resolve(_deck(), stats, functions)

    assert POKEMON <= roles.keys()
    assert all(functions.tags(card_id) or effects.clauses(card_id)
               for card_id in TRAINERS)
    for card_id in SPECIAL_POKEMON:
        stat = stats.get(card_id)
        attacks = tuple(stats.attack(attack_id) for attack_id in stat.attacks)
        markers = (
            functions.tags(card_id), effects.clauses(card_id), stat.abilityEnergyTypes,
            stat.tera,
            any(attack and (attack.benchSnipe or attack.benchSpread
                            or attack.selfReturn)
                for attack in attacks),
        )
        assert any(markers), card_id
    registry = ValueRegistry.from_strategy(
        strategy=STRATEGY, stats=stats, functions=functions, deck=_deck(), roles=roles)
    assert all(registry.worth(card_id) > 0 for card_id in set(_deck()))


def test_dragapult_uses_flexible_prizes_and_explicit_backup_attackers():
    assert STRATEGY.prize_plan is None
    assert STRATEGY.params["prize_path"] == "flexible_best_available"
    assert "backup_attacker" in STRATEGY.roles[112]
    assert "backup_attacker" in STRATEGY.roles[140]
    assert STRATEGY.potential_factory is DragapultPotential


def test_dragapult_has_dense_executable_strategy_doctrine():
    identifiers = {hint.identifier for hint in STRATEGY.strategies}
    assert len(identifiers) >= 15
    assert {
        "dragapult.risky_ruins_counter_loop",
        "dragapult.preserve_drakloak_draw_engine",
        "dragapult.phantom_dive_damage_setup",
        "dragapult.crispin_dragapult_acceleration",
        "dragapult.crispin_munkidori_fallback",
        "dragapult.crispin_fezandipiti_fallback",
        "dragapult.unfair_stamp_before_draw",
    } <= identifiers

    stats = EngineCardStatProvider()
    roles = STRATEGY.roles.resolve(_deck(), stats, CardFunctions.load())
    general = {hint.identifier for hint in general_card_strategies(
        _deck(), roles, CardFunctions.load(), stats, CardEffects.load())}
    assert {
        "general.card.235.item_lock",
        "general.card.112.fund_ability",
        "general.card.112.use_ability",
        "general.card.112.confusion_attack",
        "general.card.140.draw_ability",
        "general.card.140.deploy_after_ko",
        "general.card.66.draw_ability",
    } <= general


def test_munkidori_ability_hint_activates_for_a_benched_munkidori():
    observation = {
        "current": {"turn": 2, "yourIndex": 0, "players": [
            {"active": [{"id": 119, "serial": 1, "hp": 60, "maxHp": 70}],
             "bench": [{"id": 112, "serial": 2, "hp": 110, "maxHp": 110}],
             "benchMax": 5},
            {"active": [], "bench": []},
        ]},
        "select": {"context": 0, "option": [
            {"type": 10, "inPlayArea": 5, "inPlayIndex": 0},
        ]},
    }
    stats = EngineCardStatProvider()
    functions = CardFunctions.load()
    roles = STRATEGY.roles.resolve(_deck(), stats, functions)
    general = general_card_strategies(_deck(), roles, functions, stats, CardEffects.load())
    snapshot = activate_strategies(
        observation, resolve_strategies(general), roles=roles, stats=stats,
        effects=CardEffects.load())

    hint = next(row for row in snapshot.hints
                if row.strategy_id == "general.card.112.use_ability")
    assert hint.recipient_serial == 2


def test_fezandipiti_deploys_after_ko_without_needing_unfair_stamp():
    stats = EngineCardStatProvider()
    functions, effects = CardFunctions.load(), CardEffects.load()
    roles = STRATEGY.roles.resolve(_deck(), stats, functions)
    general = general_card_strategies(_deck(), roles, functions, stats, effects)
    observation = {
        "current": {"turn": 3, "yourIndex": 0, "players": [
            {"active": [{"id": 119, "serial": 1, "hp": 70, "maxHp": 70}],
             "bench": [], "benchMax": 5,
             "hand": [{"id": 140, "serial": 2}]},
            {"active": [], "bench": []},
        ]},
        "select": {"context": 0, "option": [{"type": 7, "index": 0}]},
        "search_begin_input": "cgpy/1:" + json.dumps({"ko_turn": [2, -1]}),
    }
    snapshot = activate_strategies(
        observation, resolve_strategies(general), roles=roles, stats=stats, effects=effects)

    assert "general.card.140.deploy_after_ko" in snapshot.active_ids


def test_fezandipiti_deploy_hint_survives_unfair_stamp_replan():
    stats = EngineCardStatProvider()
    functions, effects = CardFunctions.load(), CardEffects.load()
    roles = STRATEGY.roles.resolve(_deck(), stats, functions)
    general = general_card_strategies(_deck(), roles, functions, stats, effects)
    observation = {
        "current": {"turn": 3, "yourIndex": 0, "supporterPlayed": True, "players": [
            {"active": [{"id": 119, "serial": 1, "hp": 70, "maxHp": 70}],
             "bench": [], "benchMax": 5, "hand": [{"id": 140, "serial": 2}]},
            {"active": [], "bench": []},
        ]},
        "select": {"context": 0, "option": [{"type": 7, "index": 0}]},
        "search_begin_input": "cgpy/1:" + json.dumps({"ko_turn": [2, -1]}),
    }
    snapshot = activate_strategies(
        observation, resolve_strategies(general), roles=roles, stats=stats, effects=effects)

    assert "general.card.140.deploy_after_ko" in snapshot.active_ids


def test_drakloak_general_evolution_waits_for_the_deck_gate():
    observation = {
        "current": {"turn": 3, "yourIndex": 0, "players": [
            {"active": [{"id": 120, "serial": 1, "hp": 90, "maxHp": 90,
                         "energies": [2, 5]}], "bench": [], "benchMax": 5},
            {"active": [], "bench": []},
        ]},
        "select": {"context": 0, "option": []},
    }
    stats = EngineCardStatProvider()
    roles = STRATEGY.roles.resolve(_deck(), stats, CardFunctions.load())
    snapshot = activate_strategies(
        observation,
        resolve_strategies(
            GENERAL_STRATEGIES, STRATEGY.strategies,
            overrides=STRATEGY.strategy_overrides),
        roles=roles, stats=stats,
    )

    assert "general.evolve_active_attacker" not in snapshot.active_ids
    assert "dragapult.evolve_ready_drakloak" in snapshot.active_ids


def test_threatened_drakloak_can_evolve_before_it_is_attack_ready():
    observation = {
        "current": {"turn": 3, "yourIndex": 0, "players": [
            {"active": [{"id": 120, "serial": 1, "hp": 50, "maxHp": 90,
                         "energies": []}], "bench": [], "benchMax": 5},
            {"active": [], "bench": []},
        ]},
        "select": {"context": 0, "option": []},
    }
    stats = EngineCardStatProvider()
    roles = STRATEGY.roles.resolve(_deck(), stats, CardFunctions.load())
    snapshot = activate_strategies(
        observation,
        resolve_strategies(
            GENERAL_STRATEGIES, STRATEGY.strategies,
            overrides=STRATEGY.strategy_overrides),
        roles=roles, stats=stats,
    )

    assert "dragapult.evolve_threatened_drakloak" in snapshot.active_ids


def test_boss_gate_sees_an_unscouted_softened_multi_prize_target():
    observation = {
        "current": {"turn": 4, "yourIndex": 0, "players": [
            {"active": [{"id": 121, "serial": 1, "hp": 320, "maxHp": 320}],
             "bench": [], "benchMax": 5},
            {"active": [], "bench": [
                {"id": 121, "serial": 2, "hp": 200, "maxHp": 320}]},
        ]},
        "select": {"context": 0, "option": []},
    }
    stats = EngineCardStatProvider()
    snapshot = activate_strategies(
        observation, resolve_strategies((), STRATEGY.strategies),
        roles=STRATEGY.roles, stats=stats, opponent_role_worth={})

    assert "dragapult.boss_softened_two_prize_target" in snapshot.active_ids
