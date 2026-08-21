from common.ledger import (
    ArchetypeBelief,
    BehaviorIdentity,
    ComputeConfiguration,
    FEATURE_CATALOG,
    DeckOverlay,
    EvaluationModel,
    OpponentBeliefs,
    ValuationConfiguration,
)
from dataclasses import replace
import pytest
from common.cards import (FUNCTION_CATALOG, FUNCTION_FEATURES, Attack, Clause, PokemonCard,
                          card_store)
from common.cards.pokemon_roles import POKEMON_ROLES
from common.ledger.worth import _compile_forward_lines, usable_units
from common.scouting.briefs import load_briefs
from common.scouting.traits import OpponentTrait, TRAIT_CATALOG
from common.observation import ObservationStateBuilder
from ledger_helpers import ULTRA_BALL, body, player, printout
from common.ledger import evaluate


def test_runtime_context_resolves_the_complete_catalog_with_a_deck_residual():
    general = ValuationConfiguration.general()
    context = EvaluationModel.build(
        configuration=general,
        overlay=DeckOverlay({"role.primary_attacker": 0.25}),
    )

    assert set(context.configuration) == set(FEATURE_CATALOG.priced_keys)
    assert context.configuration["role.primary_attacker"] == 0.75
    assert context.configuration.identity != general.identity


def test_runtime_context_rejects_an_unknown_declared_role():
    with pytest.raises(KeyError, match="unknown Pokemon Role 'typo_role'"):
        EvaluationModel.build(roles={1: ("typo_role",)})


def test_feature_catalog_covers_every_pokemon_role():
    catalog_roles = {key.removeprefix("role.") for key in FEATURE_CATALOG.priced_keys
                     if key.startswith("role.")}
    assert catalog_roles == set(POKEMON_ROLES)


def test_ambiguous_and_target_directive_roles_are_retired_from_construction():
    assert "engine" not in POKEMON_ROLES
    assert "disruption_target" not in POKEMON_ROLES
    EvaluationModel.build()


def test_behavior_identity_pairs_valuation_with_a_separate_compute_profile():
    context = EvaluationModel.build(compute=ComputeConfiguration())
    faster = EvaluationModel.build(compute=replace(context.compute, chain_node_cap=64))

    assert context.behavior_identity == BehaviorIdentity(
        context.configuration.identity, context.compute.identity)
    assert faster.configuration.identity == context.configuration.identity
    assert faster.compute.identity != context.compute.identity
    assert faster.behavior_identity != context.behavior_identity


def test_catalog_contains_the_complete_generic_surface_without_tags_or_card_pins():
    keys = set(FEATURE_CATALOG.priced_keys)
    assert {
        "kind.pokemon", "kind.item", "kind.special_energy",
        "zone.in_play", "zone.in_hand",
        "belief.unknown_card", "context.opponent_unknown_card",
        "action.opportunity_cost", "result.win",
    } <= keys
    assert not any(key.startswith(("tag.", "card.")) for key in keys)


def test_card_worth_adds_independent_roles_and_explicit_unknown_coverage():
    card_id = 999_999
    context = EvaluationModel.build(
        roles={card_id: ("primary_attacker", "healer")},
        overlay=DeckOverlay({"role.primary_attacker": 0.25}),
    )

    valuation = evaluate(ObservationStateBuilder().root(printout(me=player(hand=[card_id]))), context)
    activation = {item.feature: item.value for item in valuation.activations}

    assert activation["role.primary_attacker"] == 1.0
    assert activation["role.healer"] == 1.0
    assert activation["coverage.unknown_card"] >= 1.0
    assert any(f"unknown card {card_id}" in gap for gap in valuation.gaps)


def test_partial_known_card_emits_coverage_unknown_activation_and_gap():
    valuation = evaluate(ObservationStateBuilder().root(printout(me=player(hand=[1052]))), EvaluationModel.build())
    activation = {item.feature: item.value for item in valuation.activations}

    assert activation["coverage.unknown_card"] == 1.0
    assert any("incomplete card coverage 1052" in gap for gap in valuation.gaps)


def test_opponent_roles_use_observed_facts_plus_continuous_posterior_expectation():
    card_id = 999_998
    beliefs = OpponentBeliefs(
        observed_roles={card_id: ("support_pokemon",)},
        candidates=(
            ArchetypeBelief(0.25, roles={card_id: ("primary_attacker",)}),
            ArchetypeBelief(0.50, roles={card_id: ("healer",)}),
        ),
        unknown_mass=0.25,
    )
    context = EvaluationModel.build().with_opponent(beliefs)

    valuation = evaluate(ObservationStateBuilder().root(printout(
        them=player(own=False, active=body(card_id, 1)))), context)
    activation = {item.feature: item.value for item in valuation.activations}

    assert activation["role.support_pokemon"] == -1.0
    assert activation["role.primary_attacker"] == -0.25
    assert activation["role.healer"] == -0.50


def test_runtime_context_has_one_valuation_authority():
    context = EvaluationModel.build()
    assert not hasattr(context, "weights")


def test_general_configuration_can_replace_values_for_training_trials():
    configured = ValuationConfiguration.general().with_values({"demand.dead": -0.5})

    assert configured["demand.dead"] == -0.5


def test_partial_or_extra_configuration_refuses_at_construction():
    with pytest.raises(ValueError, match="exact catalog"):
        ValuationConfiguration({"zone.in_hand": 1.0}, schema_version=1)


def test_every_card_function_compiles_against_the_closed_parameter_schema():
    clauses = []
    for card in card_store().values():
        clauses.extend(getattr(card, "clauses", ()) or ())
        for ability in getattr(card, "abilities", ()) or ():
            clauses.extend(ability.clauses)
        for attack in getattr(card, "attacks", ()) or ():
            clauses.extend(attack.clauses)

    assert FUNCTION_CATALOG.compile(clauses) == tuple(clauses)
    with pytest.raises(KeyError, match="unknown card Function"):
        FUNCTION_CATALOG.compile((Clause("typo_function"),))


def test_every_valued_card_function_declares_a_catalogued_feature():
    assert set(FUNCTION_FEATURES) <= set(FUNCTION_CATALOG.kinds)
    assert set(FUNCTION_FEATURES.values()) <= set(FEATURE_CATALOG.priced_keys)


def test_reusable_in_play_function_emits_a_situational_activation():
    valuation = evaluate(
        ObservationStateBuilder().root(printout(me=player(active=body(120, 1), hand=[]))),
        EvaluationModel.build())

    assert any(item.feature == "function.draw.hand_deficit" and item.value > 0
               for item in valuation.activations)

    opponent = evaluate(
        ObservationStateBuilder().root(printout(them=player(own=False, active=body(120, 1), hand=[]))),
        EvaluationModel.build())
    assert any(item.feature == "function.draw.hand_deficit" and item.value < 0
               for item in opponent.activations)


def test_development_reach_has_no_hidden_line_depth_cap_and_rejects_cycles():
    line = {
        index: PokemonCard(index, f"Stage {index}", 100, 1, "basic",
                           evolves_from=(f"Stage {index - 1}" if index else None))
        for index in range(7)
    }
    forward = _compile_forward_lines(line)
    assert 6 in forward["Stage 0"]

    cycle = {
        1: PokemonCard(1, "A", 100, 1, "basic", evolves_from="B"),
        2: PokemonCard(2, "B", 100, 1, "basic", evolves_from="A"),
    }
    with pytest.raises(ValueError, match="cycle"):
        _compile_forward_lines(cycle)


def test_posterior_forward_reach_scales_typed_energy_usability(monkeypatch):
    base = PokemonCard(1, "Base", 100, 1, "basic")
    child = PokemonCard(2, "Child", 100, 8, "stage1", evolves_from="Base",
                        attacks=(Attack(1, "Typed", (8,), 10),))
    context = replace(EvaluationModel.build(), store={1: base, 2: child})
    monkeypatch.setattr("common.ledger.worth._forward_lines", lambda: {"Base": (2,)})

    assert usable_units(base, (8,), context, {2: 0.1}) == pytest.approx(0.1)
    assert usable_units(base, (8,), context, {2: 1.0}) == pytest.approx(1.0)


def test_every_opponent_trait_compiles_against_the_closed_typed_schema():
    for brief in load_briefs():
        TRAIT_CATALOG.compile(brief.opponent_properties)

    with pytest.raises(KeyError, match="unknown opponent Trait"):
        TRAIT_CATALOG.compile({"opp_typo": True})

    with pytest.raises(TypeError, match="OpponentTrait"):
        ArchetypeBelief(1.0, traits=(object(),))
    with pytest.raises(KeyError, match="unknown opponent Trait"):
        ArchetypeBelief(1.0, traits=(OpponentTrait("opp_typo", True),))


def test_opponent_traits_compile_through_the_full_posterior_with_provenance():
    belief = ArchetypeBelief(
        0.4, traits=TRAIT_CATALOG.compile({"opp_item_locks": True}), archetype="lock-deck")
    context = EvaluationModel.build().with_opponent(OpponentBeliefs(
        candidates=(belief,), unknown_mass=0.6))

    valuation = evaluate(ObservationStateBuilder().root(printout(
        me=player(hand=[ULTRA_BALL]), them=player(own=False))), context)
    activation = next(item for item in valuation.activations
                      if item.feature == "trait.opp_item_locks")

    assert activation.value == 0.4
    assert activation.provenance == ("belief:lock-deck:opp_item_locks",)


def test_card_functions_compile_to_situational_feature_activations():
    valuation = evaluate(ObservationStateBuilder().root(printout(
        me=player(active=body(1031, 1), hand=[17]), them=player(own=False))),
        EvaluationModel.build())

    assert any(item.feature == "continuation.multi_provision_in_hand"
               for item in valuation.activations)
    assert not any(item.feature.startswith("function.") for item in valuation.activations)
