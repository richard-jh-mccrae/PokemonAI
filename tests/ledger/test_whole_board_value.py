from __future__ import annotations

from dataclasses import replace
from types import MappingProxyType

from ledger_helpers import (DARKNESS, DARK_E, FIRE_E, LILLIES, LUNATONE, PSYCHIC_E,
                            body, player, printout)

from common.ledger import EvaluationModel, evaluate
from common.ledger.capabilities import body_capability, card_option_units, card_option_value
from common.observation import ObservationStateBuilder


DUNSPARCE = 65
ENERGY_RETRIEVAL = 1118
MUNKIDORI = 112
SOLROCK = 676
ABRA = 109
APPLIN = 149
JACINTHE = 1241
WONDROUS_PATCH = 1146
ANNIHILAPE = 224
BASIC_FIGHTING_ENERGY = 6
WALLYS_COMPASSION = 1229
ARVENS_SANDWICH = 1130
BIANCAS_DEVOTION = 1190
SUPER_POTION = 1112


def board(**kwargs):
    return ObservationStateBuilder().root(printout(**kwargs))


def value(state, context=None):
    return evaluate(state, context or EvaluationModel.build()).total


def test_evaluation_model_has_no_strategy_role_surface():
    state = board(me=player(active=body(DUNSPARCE, 1)))
    context = EvaluationModel.build()

    assert not hasattr(context, "roles")
    assert not hasattr(context, "card_roles")
    assert not any(item.feature.startswith("role.")
                   for item in evaluate(state, context).activations)


def test_solrock_attack_is_live_only_with_lunatone_on_the_bench():
    alone = board(me=player(active=body(SOLROCK, 1, energies=(6,))))
    paired = board(me=player(active=body(SOLROCK, 1, energies=(6,)),
                             bench=[body(LUNATONE, 2)]))

    assert value(paired) > value(alone) + 0.1


def test_dark_energy_prefers_munkidori_damage_transfer_over_dunsparce_gnaw():
    before = board(
        me=player(active=body(119, 1, hp=40, max_hp=70),
                  bench=[body(DUNSPARCE, 2), body(MUNKIDORI, 3)], hand=[DARK_E]),
        them=player(own=False, active=body(119, 4, hp=70, max_hp=70)))
    dunsparce = board(
        me=player(active=body(119, 1, hp=40, max_hp=70),
                  bench=[body(DUNSPARCE, 2, energies=(DARKNESS,)), body(MUNKIDORI, 3)]),
        them=player(own=False, active=body(119, 4, hp=70, max_hp=70)))
    munkidori = board(
        me=player(active=body(119, 1, hp=40, max_hp=70),
                  bench=[body(DUNSPARCE, 2), body(MUNKIDORI, 3, energies=(DARKNESS,))]),
        them=player(own=False, active=body(119, 4, hp=70, max_hp=70)))

    context = EvaluationModel.build()
    assert value(munkidori, context) - value(before, context) \
        > value(dunsparce, context) - value(before, context) + 0.05


def test_discarded_energy_has_more_value_when_retrieval_is_available():
    empty = board(me=player(active=body(119, 1)))
    stranded = board(me=player(active=body(119, 1), discard=[FIRE_E]))
    retrieval = board(me=player(active=body(119, 1), hand=[ENERGY_RETRIEVAL]))
    recoverable = board(me=player(active=body(119, 1), hand=[ENERGY_RETRIEVAL],
                               discard=[FIRE_E]))

    assert value(recoverable) - value(retrieval) > value(stranded) - value(empty) + 0.02


def test_opponent_hidden_zones_are_board_liabilities():
    thin = board(them=player(own=False, hand_count=1, deck_count=5))
    deep = board(them=player(own=False, hand_count=7, deck_count=30))
    valuation = evaluate(deep, EvaluationModel.build())

    assert value(thin) > value(deep)
    assert any(item.feature == "resource.opponent_hidden_option" and item.value < 0
               for item in valuation.activations)
    assert any(item.feature == "resource.opponent_hidden_deck" and item.value < 0
               for item in valuation.activations)


def test_known_valuable_prize_is_an_explicit_locked_option():
    unknown = board(me=player(active=body(119, 1)))
    printed = printout(me=player(active=body(119, 1)))
    printed["own_prizes"] = {str(LILLIES): 1}
    locked = ObservationStateBuilder().root(printed)
    valuation = evaluate(locked, EvaluationModel.build())

    assert value(unknown) > valuation.total
    assert any(item.feature.startswith("option.") and item.value < 0
               for item in valuation.activations)


def test_basic_pokemon_option_includes_its_complete_evolution_line():
    state = board(me=player(active=body(DUNSPARCE, 1)))
    context = EvaluationModel.build()

    assert card_option_units(
        context.facts(119), state.me, state.them, state, context).attack \
        > card_option_units(
            context.facts(DUNSPARCE), state.me, state.them, state, context).attack


def test_energy_option_has_diminishing_value_for_interchangeable_hand_copies():
    one = board(me=player(active=body(119, 1), hand=[FIRE_E]))
    two = board(me=player(active=body(119, 1), hand=[FIRE_E, FIRE_E]))
    context = EvaluationModel.build()
    facts = context.facts(FIRE_E)

    assert card_option_value(facts, one.me, one.them, one, context) \
        > card_option_value(facts, two.me, two.them, two, context)


def test_spent_supporter_allowance_discounts_instead_of_erasing_next_turn_option():
    printed = printout(me=player(active=body(119, 1), hand=[LILLIES]))
    printed["current"]["supporterPlayed"] = True
    state = ObservationStateBuilder().root(printed)
    context = EvaluationModel.build()

    assert card_option_value(
        context.facts(LILLIES), state.me, state.them, state, context) > 0


def test_card_option_units_do_not_embed_trainable_feature_weights():
    state = board(me=player(active=body(DUNSPARCE, 1), hand=[LILLIES]))
    general = EvaluationModel.build()
    reweighted = EvaluationModel.build(configuration=general.configuration.with_values({
        "ability.draw_cards": general.configuration["ability.draw_cards"] * 20,
        "combat.attack_future": general.configuration["combat.attack_future"] * 20,
        "option.attack": general.configuration["option.attack"] * 20,
    }))

    for card_id in (LILLIES, DUNSPARCE, FIRE_E):
        assert card_option_value(
            general.facts(card_id), state.me, state.them, state, general) == card_option_value(
                reweighted.facts(card_id), state.me, state.them, state, reweighted)


def test_restricted_heal_is_live_only_with_an_eligible_active():
    psychic = board(me=player(active=body(ABRA, 1, hp=30, max_hp=70)))
    grass = board(me=player(active=body(APPLIN, 1, hp=30, max_hp=70)))
    context = EvaluationModel.build()
    facts = context.facts(JACINTHE)

    assert card_option_units(
        facts, psychic.me, psychic.them, psychic, context).healing > 0
    assert card_option_units(
        facts, grass.me, grass.them, grass, context).healing == 0


def test_matching_typed_supply_and_targets_increase_feasibility_features():
    scarce = board(me=player(
        active=body(119, 1), bench=[body(APPLIN, 2)],
        hand=[WONDROUS_PATCH], discard=[FIRE_E]))
    live = board(me=player(
        active=body(119, 1), bench=[body(ABRA, 2)],
        hand=[WONDROUS_PATCH], discard=[PSYCHIC_E, PSYCHIC_E]))
    context = EvaluationModel.build()

    def activation(state, feature):
        return sum(item.value for item in evaluate(state, context).activations
                   if item.feature == feature)

    assert activation(live, "clause.parameter.energy_type") \
        > activation(scarce, "clause.parameter.energy_type")
    assert activation(live, "clause.parameter.target_type") \
        > activation(scarce, "clause.parameter.target_type")


def test_lunar_cycle_requires_basic_fighting_energy_in_hand():
    empty = board(me=player(active=body(SOLROCK, 1), bench=[body(LUNATONE, 2)]))
    payable = board(me=player(
        active=body(SOLROCK, 1), bench=[body(LUNATONE, 2)],
        hand=[BASIC_FIGHTING_ENERGY]))
    context = EvaluationModel.build()
    facts = context.facts(LUNATONE)

    assert card_option_units(
        facts, empty.me, empty.them, empty, context).draw == 0
    assert card_option_units(
        facts, payable.me, payable.them, payable, context).draw > 0


def test_restricted_heals_accept_eligible_benched_targets():
    psychic = board(me=player(
        active=body(APPLIN, 1), bench=[body(ABRA, 2, hp=30, max_hp=70)]))
    mega = board(me=player(
        active=body(APPLIN, 1), bench=[body(1031, 2, hp=200, max_hp=330)]))
    context = EvaluationModel.build()

    assert card_option_units(
        context.facts(JACINTHE), psychic.me, psychic.them, psychic, context).healing > 0
    assert card_option_units(
        context.facts(WALLYS_COMPASSION), mega.me, mega.them, mega,
        context).healing > 0


def test_arvens_sandwich_uses_only_the_active_pokemon_and_not_both_modes():
    context = EvaluationModel.build()
    arven_id = 9_999_001
    arven = replace(
        context.facts(APPLIN), card_id=arven_id, name="Arven's Mabosstiff")
    context = replace(context, store=MappingProxyType({
        **context.store, arven_id: arven}))
    benched = board(me=player(
        active=body(APPLIN, 1, hp=10, max_hp=100),
        bench=[body(arven_id, 2, hp=10, max_hp=100)]))
    active = board(me=player(
        active=body(arven_id, 1, hp=10, max_hp=100),
        bench=[body(APPLIN, 2, hp=10, max_hp=100)]))
    facts = context.facts(ARVENS_SANDWICH)

    assert card_option_units(
        facts, benched.me, benched.them, benched, context).healing == 0.3
    assert card_option_units(
        facts, active.me, active.them, active, context).healing == 0.9


def test_jacinthe_ignores_damage_on_ineligible_pokemon():
    state = board(me=player(
        active=body(ABRA, 1, hp=70, max_hp=70),
        bench=[body(APPLIN, 2, hp=10, max_hp=100)]))
    context = EvaluationModel.build()

    assert card_option_units(
        context.facts(JACINTHE), state.me, state.them, state, context).healing == 0


def test_bianca_heals_only_the_low_remaining_hp_target():
    state = board(me=player(
        active=body(APPLIN, 1, hp=30, max_hp=100),
        bench=[body(DUNSPARCE, 2, hp=40, max_hp=200)]))
    context = EvaluationModel.build()

    assert card_option_units(
        context.facts(BIANCAS_DEVOTION), state.me, state.them, state,
        context).healing == 0.7


def test_super_potion_energy_cost_comes_from_the_selected_heal_target():
    blocked = board(me=player(
        active=body(APPLIN, 1, hp=40, max_hp=100),
        bench=[body(DUNSPARCE, 2, hp=100, max_hp=100, energies=(6,))]))
    payable = board(me=player(
        active=body(APPLIN, 1, hp=40, max_hp=100, energies=(6,)),
        bench=[body(DUNSPARCE, 2, hp=100, max_hp=100)]))
    context = EvaluationModel.build()
    facts = context.facts(SUPER_POTION)

    assert card_option_units(
        facts, blocked.me, blocked.them, blocked, context).healing == 0
    payable_units = card_option_units(
        facts, payable.me, payable.them, payable, context)
    assert payable_units.healing == 0.6
    assert payable_units.cost == 1.0


def test_both_active_ko_prices_own_prize_and_terminal_loss():
    safe = board(
        me=player(active=body(ANNIHILAPE, 1, energies=(6, 0))),
        them=player(own=False, active=body(1031, 2, hp=330, max_hp=330), prizes=2))
    terminal = board(
        me=player(active=body(ANNIHILAPE, 1, energies=(6, 0))),
        them=player(own=False, active=body(1031, 2, hp=330, max_hp=330), prizes=1))
    context = EvaluationModel.build()

    def liability(state):
        return sum(item.value for item in evaluate(state, context).activations
                   if item.feature == "function.ko.self_prize_liability")

    assert liability(terminal) > liability(safe) + 50
    safe_capability = body_capability(
        safe.me.active, safe.me, safe.them, safe, context)
    terminal_capability = body_capability(
        terminal.me.active, terminal.me, terminal.them, terminal, context)
    assert safe_capability.attack_now > terminal_capability.attack_now
    assert safe_capability.resource_cost > terminal_capability.resource_cost
