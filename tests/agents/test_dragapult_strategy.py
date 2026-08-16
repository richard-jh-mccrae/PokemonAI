from pathlib import Path
import json

import pytest

from agents.dragapult_ex.strategy import STRATEGY
from common.demand import StrategyBeamBuilder
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
        "dragapult.phantom_dive_damage_setup",
        "dragapult.crispin_fuel_the_line",
        "dragapult.crispin_fuel_the_payoff",
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
    assert "dragapult.evolve_drakloak_for_the_attack" in snapshot.active_ids


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


def _outcome(hint):
    """The identity of a desired outcome: what is wanted, of whom, from which cards, when.

    Matches the key protected-bundle ranking deduplicates on, so a doctrine that states one
    intention twice contributes one unit of coverage, not two.
    """
    fact = hint.desired_facts[0]
    return (fact.kind, hint.recipient_selector, fact.target_card_ids, hint.waypoint)


def test_deck_doctrine_spans_the_urgency_and_conviction_tiers():
    """Ranking is lexicographic on urgency then conviction. A doctrine that authors every hint
    into one tier ranks nothing, and leaves the order to whatever tie-break sits underneath."""
    deadlines = {hint.deadline for hint in STRATEGY.strategies}
    convictions = {hint.conviction for hint in STRATEGY.strategies}

    assert {"immediate", "this_turn"} <= deadlines
    assert {"high", "medium", "low"} <= convictions


def test_only_the_phantom_dive_line_and_its_conversions_are_immediate():
    immediate = {hint.identifier for hint in STRATEGY.strategies
                 if hint.deadline == "immediate"}

    assert immediate == {
        "dragapult.fund_active_phantom_dive",
        "dragapult.evolve_drakloak_for_the_attack",
        "dragapult.phantom_dive_damage_setup",
        "dragapult.boss_softened_two_prize_target",
        "dragapult.unfair_stamp_before_draw",
    }


def test_funding_hints_do_not_restate_a_printed_attack_cost():
    """An attack's cost is a card fact. A deck that copies it into a declaration names half of
    it sooner or later, and scores the other half at zero."""
    funding = [hint for hint in STRATEGY.strategies
               if hint.desired_facts[0].kind == "fund_attack"]

    assert funding
    for hint in funding:
        assert hint.desired_facts[0].target_card_ids == ()


def test_the_crispin_declarations_state_one_desired_outcome():
    """Crispin's recipient does not select the play, so three recipient-distinct declarations
    were one intention counted three times."""
    crispin = [hint for hint in STRATEGY.strategies
               if 1198 in hint.desired_facts[0].target_card_ids]

    assert len(crispin) > 1
    assert len({_outcome(hint) for hint in crispin}) == 1


def test_hints_sharing_an_outcome_activate_on_different_boards():
    """Two hints may share an outcome to cover different boards, as Crispin's do. Sharing the
    activation as well means the second says nothing the first did not."""
    seen = {}
    for hint in STRATEGY.strategies:
        key = (_outcome(hint), hint.conditions)
        assert key not in seen, f"{hint.identifier} repeats {seen.get(key)}"
        seen[key] = hint.identifier


def test_every_deck_hint_is_gated_on_a_board_that_makes_it_true():
    """An always-active hint claims search attention, and coverage, on every turn including the
    ones where it cannot act."""
    ungated = [hint.identifier for hint in STRATEGY.strategies if not hint.conditions]

    assert ungated == []


def test_the_dunsparce_draw_line_has_a_driver():
    """Neither Dunsparce nor Dudunsparce is an attacker, so the shared evolution machinery drops
    the relationship and no general hint ever reaches it."""
    roles = STRATEGY.roles.resolve(_deck(), EngineCardStatProvider(), CardFunctions.load())
    assert 305 not in roles.evolves

    evolve = {hint.desired_facts[0].target_card_ids for hint in STRATEGY.strategies
              if hint.desired_facts[0].kind == "evolve"}
    assert (66,) in evolve


def _funding_energy(card_id, attached=()):
    """Deck Energy the shared beam would treat as funding this body as our active."""
    from types import SimpleNamespace
    from common.demand import StrategyBeamBuilder
    from common.strategy.strategies import GENERAL_STRATEGIES

    stats, functions, effects = (
        EngineCardStatProvider(), CardFunctions.load(), CardEffects.load())
    deck = _deck()
    roles = STRATEGY.roles.resolve(deck, stats, functions)
    resolved = resolve_strategies(
        (*GENERAL_STRATEGIES, *general_card_strategies(deck, roles, functions, stats, effects)),
        STRATEGY.strategies, (), STRATEGY.strategy_overrides)
    maximum = int(stats.get(card_id).hp)
    observation = {"current": {"turn": 3, "yourIndex": 0, "result": -1, "players": [
        {"active": [{"id": card_id, "serial": 1, "hp": maximum, "maxHp": maximum,
                     "energies": list(attached), "energyCards": [], "preEvolution": [],
                     "tools": []}],
         "bench": [], "hand": [], "prize": [None] * 6, "benchMax": 5},
        {"active": [], "bench": [], "prize": [None] * 6, "benchMax": 5},
    ]}, "select": {"context": 0, "option": []}}
    snapshot = activate_strategies(
        observation, resolved, roles=roles, stats=stats, effects=effects)
    builder = StrategyBeamBuilder(snapshot, effects=effects, stats=stats)
    state = SimpleNamespace(
        obs=observation, root_seat=0,
        deck_counts=tuple({row: deck.count(row) for row in set(deck)}.items()))
    funding = set()
    for hint in snapshot.hints:
        if hint.kind == "fund_attack":
            funding.update(builder._funding_energy_ids(state, hint))
    return funding


DARKNESS_ENERGY, FIRE_ENERGY, PSYCHIC_ENERGY = 7, 2, 5


@pytest.mark.parametrize("card_id", [119, 120, 121])
def test_darkness_is_never_funding_for_the_dragapult_line(card_id):
    """Darkness fuels Munkidori's Ability. Dragapult ex also prints a one-Colorless attack, and
    a Colorless slot accepts anything, so an empty Dragapult once read as wanting Darkness."""
    assert DARKNESS_ENERGY not in _funding_energy(card_id)
    assert DARKNESS_ENERGY not in _funding_energy(card_id, attached=(FIRE_ENERGY,))
    assert _funding_energy(card_id) == {FIRE_ENERGY, PSYCHIC_ENERGY}


@pytest.mark.parametrize("card_id", [1071, 305, 66])
def test_support_pokemon_are_never_funded(card_id):
    """Meowth ex, Dunsparce and Dudunsparce hold no attacker role, so no funding hint reaches
    them. The requirement lives in the shared role vocabulary, not in this deck's doctrine."""
    roles = STRATEGY.roles.resolve(_deck(), EngineCardStatProvider(), CardFunctions.load())

    assert not {"primary_attacker", "backup_attacker"} & set(roles.get(card_id, ()))
    assert _funding_energy(card_id) == set()


def test_munkidori_declares_its_darkness_ability_slot_from_the_card():
    """The Ability's Energy requirement is printed on the card; general_card_strategies reads it
    rather than the deck naming Darkness."""
    stats, functions = EngineCardStatProvider(), CardFunctions.load()
    assert stats.get(112).abilityEnergyTypes == (7,)

    roles = STRATEGY.roles.resolve(_deck(), stats, functions)
    hint = next(row for row in general_card_strategies(
        _deck(), roles, functions, stats, CardEffects.load())
        if row.identifier == "general.card.112.fund_ability")

    assert hint.desired_facts[0].target_card_ids == (DARKNESS_ENERGY,)


def _active_snapshot(card_id, bench=()):
    from common.strategy.strategies import GENERAL_STRATEGIES

    stats, functions, effects = (
        EngineCardStatProvider(), CardFunctions.load(), CardEffects.load())
    deck = _deck()
    roles = STRATEGY.roles.resolve(deck, stats, functions)
    resolved = resolve_strategies(
        (*GENERAL_STRATEGIES, *general_card_strategies(deck, roles, functions, stats, effects)),
        STRATEGY.strategies, (), STRATEGY.strategy_overrides)

    def _body(row, serial):
        maximum = int(stats.get(row).hp)
        return {"id": row, "serial": serial, "hp": maximum, "maxHp": maximum,
                "energies": [], "energyCards": [], "preEvolution": [], "tools": []}

    observation = {"current": {"turn": 5, "yourIndex": 0, "result": -1, "players": [
        {"active": [_body(card_id, 1)],
         "bench": [_body(row, index + 2) for index, row in enumerate(bench)],
         "hand": [], "prize": [None] * 6, "benchMax": 5},
        {"active": [], "bench": [_body(121, 20)], "prize": [None] * 6, "benchMax": 5},
    ]}, "select": {"context": 0, "option": []}}
    return activate_strategies(observation, resolved, roles=roles, stats=stats, effects=effects,
                               opponent_role_worth={121: 30.0})


def test_cruel_arrow_is_a_pinch_attack_not_a_plan():
    """Fezandipiti ex gives up two prizes. It shoots only while no Dragapult ex is on the board,
    so a turn that could promote the real attacker is never spent on the fallback."""
    fallback = "dragapult.fezandipiti_bench_snipe_fallback"

    assert fallback in _active_snapshot(140).active_ids
    assert fallback not in _active_snapshot(140, bench=(121,)).active_ids
    assert fallback not in _active_snapshot(121).active_ids


def test_the_pinch_attacker_never_outranks_the_real_line():
    by_id = {hint.identifier: hint for hint in STRATEGY.strategies}
    pinch = by_id["dragapult.fezandipiti_bench_snipe_fallback"]
    plan = by_id["dragapult.phantom_dive_damage_setup"]

    assert (pinch.deadline, pinch.conviction) == ("this_turn", "low")
    assert (plan.deadline, plan.conviction) == ("immediate", "high")


def test_drakloak_is_held_while_a_dragapult_is_already_doing_the_job():
    """Evolving spends a draw engine and puts a two-prize body down, and it can be done on the
    very turn it attacks. With a Dragapult ex already in play the benched Drakloak keeps
    drawing."""
    attacking = _active_snapshot(121, bench=(120,))

    assert "dragapult.evolve_drakloak_for_the_attack" not in attacking.active_ids
    assert "dragapult.evolve_threatened_drakloak" not in attacking.active_ids


def test_drakloak_evolves_once_the_line_has_no_payoff_of_its_own():
    """No Dragapult ex anywhere is what makes the evolution wanted -- not our active, which is
    fixed at the planning-epoch boundary and would strand a promote-then-evolve turn."""
    from types import SimpleNamespace
    from common.strategy.strategies import GENERAL_STRATEGIES

    stats, functions, effects = (
        EngineCardStatProvider(), CardFunctions.load(), CardEffects.load())
    deck = _deck()
    roles = STRATEGY.roles.resolve(deck, stats, functions)
    resolved = resolve_strategies(
        (*GENERAL_STRATEGIES, *general_card_strategies(deck, roles, functions, stats, effects)),
        STRATEGY.strategies, (), STRATEGY.strategy_overrides)

    def _snapshot(energies):
        observation = {"current": {"turn": 6, "yourIndex": 0, "result": -1, "players": [
            {"active": [{"id": 119, "serial": 1, "hp": 70, "maxHp": 70, "energies": [],
                         "energyCards": [], "preEvolution": [], "tools": []}],
             "bench": [{"id": 120, "serial": 2, "hp": 90, "maxHp": 90, "energies": list(energies),
                        "energyCards": [], "preEvolution": [], "tools": []}],
             "hand": [], "prize": [None] * 6, "benchMax": 5},
            {"active": [], "bench": [], "prize": [None] * 6, "benchMax": 5},
        ]}, "select": {"context": 0, "option": []}}
        return activate_strategies(
            observation, resolved, roles=roles, stats=stats, effects=effects)

    # Benched, not active: the hint must still be live so a promote-then-evolve turn is guided.
    assert "dragapult.evolve_drakloak_for_the_attack" in _snapshot((2, 5)).active_ids
    # Unfunded: evolving would put down a two-prize body that cannot swing.
    assert "dragapult.evolve_drakloak_for_the_attack" not in _snapshot(()).active_ids


def test_a_threatened_drakloak_evolves_even_behind_an_attacking_dragapult():
    """90 HP becomes 320 and the damage already on it stops being lethal. Losing the Drakloak
    loses the line behind the attacker."""
    from types import SimpleNamespace
    from common.strategy.strategies import GENERAL_STRATEGIES

    stats, functions, effects = (
        EngineCardStatProvider(), CardFunctions.load(), CardEffects.load())
    deck = _deck()
    roles = STRATEGY.roles.resolve(deck, stats, functions)
    resolved = resolve_strategies(
        (*GENERAL_STRATEGIES, *general_card_strategies(deck, roles, functions, stats, effects)),
        STRATEGY.strategies, (), STRATEGY.strategy_overrides)
    observation = {"current": {"turn": 6, "yourIndex": 0, "result": -1, "players": [
        {"active": [{"id": 121, "serial": 1, "hp": 320, "maxHp": 320, "energies": [2, 5],
                     "energyCards": [], "preEvolution": [], "tools": []}],
         "bench": [{"id": 120, "serial": 2, "hp": 30, "maxHp": 90, "energies": [],
                    "energyCards": [], "preEvolution": [], "tools": []}],
         "hand": [], "prize": [None] * 6, "benchMax": 5},
        {"active": [], "bench": [], "prize": [None] * 6, "benchMax": 5},
    ]}, "select": {"context": 0, "option": []}}
    snapshot = activate_strategies(
        observation, resolved, roles=roles, stats=stats, effects=effects)

    assert "dragapult.evolve_threatened_drakloak" in snapshot.active_ids
