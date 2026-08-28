from __future__ import annotations

from dataclasses import replace
from types import MappingProxyType

from ledger_helpers import (DARKNESS, DARK_E, FIRE_E, LILLIES, LUNATONE, PSYCHIC_E,
                            body, player, printout)

from common.ledger import EvaluationModel, evaluate
from common.ledger.capabilities import (OptionUnits, body_capability, card_option_units,
                                        card_option_value)
from common.ledger.portfolio import feasible_option_portfolio_result
from common.observation import ObservationStateBuilder
from common.cards.card_facts import (BASIC, STAGE1, Clause, ITEM, SUPPORTER,
                                     PokemonCard, TrainerCard)


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
ULTRA_BALL = 1121
POFFIN = 1086
SECRET_BOX = 1092
MAX_ROD = 1110
ENERGY_SEARCH_PRO = 1100
POKEGEAR = 1122
CARMINE = 1192
WONDROUS_PATCH_CARD = 1146
RARE_CANDY = 1079
REBOOT_POD = 1089
SALVATORE = 1189
CRISPIN = 1198
WAITRESS = 1235
TELEPATH_PSYCHIC_ENERGY = 19


def board(**kwargs):
    return ObservationStateBuilder().root(printout(**kwargs))


def value(state, context=None):
    return evaluate(state, context or EvaluationModel.build()).total


def feasible_option_portfolio(*args, **kwargs):
    return feasible_option_portfolio_result(*args, **kwargs).units


def activation(state, feature, context=None):
    return sum(item.value for item in evaluate(
        state, context or EvaluationModel.build()).activations
               if item.feature == feature)


def test_feasible_portfolio_counts_one_supporter_but_compatible_items():
    context = EvaluationModel.build()
    supporter_id, item_id = 9_999_101, 9_999_102
    store = MappingProxyType({
        **context.store,
        supporter_id: TrainerCard(
            supporter_id, "Probe Supporter", SUPPORTER,
            clauses=(Clause("draw", amount=2),), covers="full"),
        item_id: TrainerCard(
            item_id, "Probe Item", ITEM,
            clauses=(Clause("draw", amount=2),), covers="full"),
    })
    context = replace(context, store=store)
    one = board(me=player(active=body(DUNSPARCE, 1), hand=[supporter_id]))
    duplicates = board(me=player(
        active=body(DUNSPARCE, 1), hand=[supporter_id, supporter_id, supporter_id]))
    compatible = board(me=player(
        active=body(DUNSPARCE, 1), hand=[supporter_id, item_id]))

    assert activation(one, "option.draw", context) == 2
    assert activation(duplicates, "option.draw", context) == 2
    assert activation(compatible, "option.draw", context) == 4


def test_feasible_portfolio_can_pay_costs_with_dead_hand_material():
    context = EvaluationModel.build()
    state = replace(
        board(me=player(active=body(DUNSPARCE, 1),
                        hand=[ULTRA_BALL, DUNSPARCE, DUNSPARCE])),
        deck_counts=((119, 1),))
    entry = [(context.facts(ULTRA_BALL), OptionUnits(search=1))]

    assert feasible_option_portfolio(
        entry, state.me, state, context, hand_size=1).search == 0
    assert feasible_option_portfolio(
        entry, state.me, state, context, hand_size=3).search == 1


def test_feasible_portfolio_optimizes_weighted_ledger_worth():
    context = EvaluationModel.build()
    supporter_id = 9_999_103
    supporter = TrainerCard(
        supporter_id, "Probe Supporter", SUPPORTER,
        clauses=(Clause("draw", amount=1),), covers="full")
    state = board(me=player(active=body(DUNSPARCE, 1), hand=[supporter_id]))
    entries = [
        (supporter, OptionUnits(draw=1.1)),
        (supporter, OptionUnits(search=1.0)),
    ]

    chosen = feasible_option_portfolio(
        entries, state.me, state, context, hand_size=2)

    assert chosen.search == 1.0
    assert chosen.draw == 0.0

    result = feasible_option_portfolio_result(
        entries, state.me, state, context, hand_size=2)
    assert result.selected_indices == (1,)
    assert result.selected_units == ((1, OptionUnits(search=1.0)),)


def test_feasible_portfolio_does_not_reuse_fetch_targets_or_bench_slots():
    context = EvaluationModel.build()
    state = replace(
        board(me=player(active=body(DUNSPARCE, 1), hand=[POFFIN, POFFIN])),
        deck_counts=((119, 3),))
    entries = [(context.facts(POFFIN), OptionUnits(search=2))] * 2

    chosen = feasible_option_portfolio(
        entries, state.me, state, context, hand_size=2)

    assert chosen.search == 3


def test_feasible_portfolio_does_not_reuse_heal_energy_target():
    context = EvaluationModel.build()
    state = board(me=player(
        active=body(DUNSPARCE, 1, hp=40, max_hp=100, energies=(6,)),
        bench=[body(119, 2, hp=10, max_hp=70)],
        hand=[SUPER_POTION, SUPER_POTION]))
    entries = [(context.facts(SUPER_POTION), OptionUnits(healing=0.6, cost=1))] * 2

    chosen = feasible_option_portfolio(
        entries, state.me, state, context, hand_size=2)

    assert chosen.healing == 0.6


def test_multi_fetch_cost_is_paid_once_and_targets_are_not_reused():
    context = EvaluationModel.build()
    state = replace(
        board(me=player(active=body(DUNSPARCE, 1),
                        hand=[SECRET_BOX, SECRET_BOX, DUNSPARCE, DUNSPARCE,
                              DUNSPARCE, DUNSPARCE, DUNSPARCE, DUNSPARCE])),
        deck_counts=((1121, 1), (1260, 1), (1227, 1), (1159, 1)))
    entries = [(context.facts(SECRET_BOX), OptionUnits(search=4))] * 2

    chosen = feasible_option_portfolio(
        entries, state.me, state, context, hand_size=8)

    assert chosen.search == 4


def test_discard_fetch_and_distinct_type_limits_are_feasible():
    context = EvaluationModel.build()
    state = replace(
        board(me=player(active=body(DUNSPARCE, 1),
                        hand=[MAX_ROD, ENERGY_SEARCH_PRO])),
        deck_counts=((BASIC_FIGHTING_ENERGY, 3),))

    assert feasible_option_portfolio(
        [(context.facts(MAX_ROD), OptionUnits(search=5))],
        state.me, state, context, hand_size=2).search == 0
    assert feasible_option_portfolio(
        [(context.facts(ENERGY_SEARCH_PRO), OptionUnits(search=3))],
        state.me, state, context, hand_size=2).search == 1


def test_dig_is_expected_value_and_discard_hand_excludes_played_card():
    context = EvaluationModel.build()
    pokegear_state = replace(
        board(me=player(active=body(DUNSPARCE, 1), hand=[POKEGEAR])),
        deck_counts=((LILLIES, 1), (119, 9)))
    carmine_state = replace(
        board(me=player(active=body(DUNSPARCE, 1), hand=[CARMINE])),
        deck_counts=((LILLIES, 1), (119, 9)))

    pokegear = feasible_option_portfolio(
        [(context.facts(POKEGEAR), OptionUnits(search=1))],
        pokegear_state.me, pokegear_state, context, hand_size=1)
    carmine = feasible_option_portfolio(
        [(context.facts(CARMINE), OptionUnits(draw=5, cost=1))],
        carmine_state.me, carmine_state, context, hand_size=1)

    assert 0 < pokegear.search < 1
    assert carmine.draw == 5
    assert carmine.cost == 0


def test_items_can_be_played_before_discarding_the_rest_of_the_hand():
    context = EvaluationModel.build()
    item = TrainerCard(
        9_999_104, "Probe Item", ITEM,
        clauses=(Clause("draw", amount=1),), covers="full")
    state = board(me=player(
        active=body(DUNSPARCE, 1), hand=[item.card_id, CARMINE]))

    chosen = feasible_option_portfolio([
        (item, OptionUnits(draw=1)),
        (context.facts(CARMINE), OptionUnits(draw=5, cost=2)),
    ], state.me, state, context, hand_size=2)

    assert chosen.draw == 6


def test_discard_hand_cannot_reuse_cards_spent_on_an_earlier_discard_cost():
    context = EvaluationModel.build()
    state = replace(
        board(me=player(active=body(DUNSPARCE, 1),
                        hand=[ULTRA_BALL, CARMINE, DUNSPARCE])),
        deck_counts=((119, 1),))

    chosen = feasible_option_portfolio([
        (context.facts(ULTRA_BALL), OptionUnits(search=1)),
        (context.facts(CARMINE), OptionUnits(draw=100, cost=2)),
    ], state.me, state, context, hand_size=3)

    assert chosen.draw == 100
    assert chosen.search == 0


def test_acceleration_opportunities_do_not_reuse_discard_energy():
    context = EvaluationModel.build()
    state = board(me=player(
        active=body(DUNSPARCE, 1), bench=[body(ABRA, 2)],
        discard=[PSYCHIC_E], hand=[WONDROUS_PATCH_CARD, WONDROUS_PATCH_CARD]))
    entries = [(context.facts(WONDROUS_PATCH_CARD),
                OptionUnits(acceleration=1))] * 2

    chosen = feasible_option_portfolio(
        entries, state.me, state, context, hand_size=2)

    assert chosen.acceleration == 1


def test_rare_candies_cannot_reuse_one_basic_evolution_target():
    context = EvaluationModel.build()
    state = board(me=player(
        active=body(DUNSPARCE, 1), bench=[body(119, 2)],
        hand=[RARE_CANDY, RARE_CANDY, 121, 121]))

    chosen = feasible_option_portfolio(
        [(context.facts(RARE_CANDY), OptionUnits(search=1))] * 2,
        state.me, state, context, hand_size=4)

    assert chosen.search == 1


def test_in_play_fetch_target_cannot_also_pay_another_discard_cost():
    context = EvaluationModel.build()
    state = replace(
        board(me=player(
            active=body(DUNSPARCE, 1), bench=[body(119, 2)],
            hand=[RARE_CANDY, 121, ULTRA_BALL, DUNSPARCE])),
        deck_counts=((120, 1),))

    chosen = feasible_option_portfolio([
        (context.facts(RARE_CANDY), OptionUnits(search=1)),
        (context.facts(ULTRA_BALL), OptionUnits(search=1)),
    ], state.me, state, context, hand_size=4)

    assert chosen.search == 1


def test_salvatore_can_evolve_a_pokemon_played_this_turn():
    context = EvaluationModel.build()
    basic_id, evolution_id = 9_999_105, 9_999_106
    basic = PokemonCard(basic_id, "Probe Basic", 60, 5, BASIC)
    evolution = PokemonCard(
        evolution_id, "Probe Evolution", 100, 5, STAGE1,
        evolves_from=basic.name)
    context = replace(context, store=MappingProxyType({
        **context.store, basic_id: basic, evolution_id: evolution,
    }))
    appeared = {**body(basic_id, 2), "appearThisTurn": True}
    state = replace(
        board(me=player(active=body(DUNSPARCE, 1), bench=[appeared],
                        hand=[SALVATORE])),
        deck_counts=((evolution_id, 1),))

    chosen = feasible_option_portfolio(
        [(context.facts(SALVATORE), OptionUnits(search=1))],
        state.me, state, context, hand_size=1)

    assert chosen.search == 1


def test_acceleration_requires_an_eligible_recipient():
    context = EvaluationModel.build()
    wondrous = board(me=player(
        active=body(ABRA, 1), hand=[WONDROUS_PATCH], discard=[PSYCHIC_E]))
    reboot = board(me=player(
        active=body(DUNSPARCE, 1), hand=[REBOOT_POD],
        discard=[BASIC_FIGHTING_ENERGY]))

    assert feasible_option_portfolio(
        [(context.facts(WONDROUS_PATCH), OptionUnits(acceleration=1))],
        wondrous.me, wondrous, context, hand_size=1).acceleration == 0
    assert feasible_option_portfolio(
        [(context.facts(REBOOT_POD), OptionUnits(acceleration=1))],
        reboot.me, reboot, context, hand_size=1).acceleration == 0


def test_reboot_pod_scales_over_explicit_future_tags():
    context = EvaluationModel.build()
    state = board(me=player(
        active=body(DUNSPARCE, 1), bench=[body(27, 2), body(37, 3)],
        hand=[REBOOT_POD],
        discard=[BASIC_FIGHTING_ENERGY, PSYCHIC_E]))

    chosen = feasible_option_portfolio(
        [(context.facts(REBOOT_POD), OptionUnits(acceleration=1))],
        state.me, state, context, hand_size=1)

    assert chosen.acceleration == 2


def test_acceleration_respects_dig_and_distinct_energy_types():
    context = EvaluationModel.build()
    waitress = replace(
        board(me=player(active=body(DUNSPARCE, 1), hand=[WAITRESS])),
        deck_counts=((BASIC_FIGHTING_ENERGY, 1), (119, 9)))
    crispin = replace(
        board(me=player(active=body(DUNSPARCE, 1), hand=[CRISPIN])),
        deck_counts=((BASIC_FIGHTING_ENERGY, 2),))

    waitress_units = feasible_option_portfolio(
        [(context.facts(WAITRESS), OptionUnits(acceleration=1))],
        waitress.me, waitress, context, hand_size=1)
    crispin_units = feasible_option_portfolio(
        [(context.facts(CRISPIN), OptionUnits(acceleration=2))],
        crispin.me, crispin, context, hand_size=1)

    assert 0 < waitress_units.acceleration < 1
    assert crispin_units.acceleration == 1


def test_telepath_energy_realizes_its_triggered_fetch():
    context = EvaluationModel.build()
    psychic = replace(
        board(me=player(active=body(ABRA, 1), hand=[TELEPATH_PSYCHIC_ENERGY])),
        deck_counts=((ABRA, 2),))
    non_psychic = replace(
        board(me=player(active=body(DUNSPARCE, 1),
                        hand=[TELEPATH_PSYCHIC_ENERGY])),
        deck_counts=((ABRA, 2),))

    assert feasible_option_portfolio(
        [(context.facts(TELEPATH_PSYCHIC_ENERGY), OptionUnits(energy=1))],
        psychic.me, psychic, context, hand_size=1).search == 2
    assert feasible_option_portfolio(
        [(context.facts(TELEPATH_PSYCHIC_ENERGY), OptionUnits(energy=1))],
        non_psychic.me, non_psychic, context, hand_size=1).search == 0


def test_hand_acceleration_and_manual_attach_share_the_energy_card():
    context = EvaluationModel.build()
    trainer_id = 9_999_107
    trainer = TrainerCard(
        trainer_id, "Probe Accelerator", ITEM,
        clauses=(Clause("accel", amount=1, source="hand",
                        target="any_pokemon", energy="basic"),), covers="full")
    context = replace(context, store=MappingProxyType({**context.store, trainer_id: trainer}))
    state = board(me=player(
        active=body(DUNSPARCE, 1), hand=[trainer_id, BASIC_FIGHTING_ENERGY]))

    chosen = feasible_option_portfolio([
        (trainer, OptionUnits(acceleration=1)),
        (context.facts(BASIC_FIGHTING_ENERGY), OptionUnits(energy=1)),
    ], state.me, state, context, hand_size=2)

    assert chosen.acceleration + chosen.energy == 1


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
