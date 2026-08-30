from common.ledger import (
    ActivationCompiler,
    ActivationEnvironment,
    ActivationRule,
    BehaviorIdentity,
    ComputeConfiguration,
    FEATURE_CATALOG,
    DeckOverlay,
    EvaluationModel,
    FeatureCatalog,
    FeatureSpec,
    OpponentProfile,
    ValuationConfiguration,
)
from dataclasses import replace
import pytest
from common.cards import FUNCTION_CATALOG, Attack, Clause, PokemonCard, card_store
from common.cards.pokemon_roles import POKEMON_ROLES
from common.ledger.worth import _compile_forward_lines, usable_units
from common.ledger.features import FeatureDisposition
from common.opponent import (
    ArchetypeBelief, OpponentEvidence, OpponentMechanic, OpponentSnapshot, OpponentTrait,
)
from common.strategy import PrizePlan
from common.observation import LegalKnowledge, ObservationStateBuilder, OpponentBelief
from ledger_helpers import ULTRA_BALL, body, player, printout
from common.ledger import evaluate


def _snapshot(*, observed_roles=None, candidates=(), unknown_mass=1.0):
    state = ObservationStateBuilder().root(printout())
    return OpponentSnapshot(
        OpponentEvidence.from_state(state), observed_roles or {}, candidates, unknown_mass)


def _profiles(snapshot):
    return {candidate.archetype: OpponentProfile(
        candidate.roles, candidate.traits, candidate.mechanics, candidate.resources)
            for candidate in snapshot.candidates}


def test_runtime_context_resolves_the_complete_catalog_with_a_deck_residual():
    general = ValuationConfiguration.general()
    context = EvaluationModel.build(
        configuration=general,
        overlay=DeckOverlay({"combat.realization": 0.25}),
    )

    assert set(context.configuration) == set(FEATURE_CATALOG.priced_keys)
    assert context.configuration["combat.realization"] == 1.25
    assert context.configuration.identity != general.identity


def test_runtime_context_rejects_the_retired_role_surface():
    with pytest.raises(TypeError, match="unexpected keyword argument 'roles'"):
        EvaluationModel.build(roles={1: ("typo_role",)})


def test_feature_catalog_contains_no_strategy_role_values():
    assert not any("role." in key for key in FEATURE_CATALOG.priced_keys)


def test_ambiguous_and_target_directive_roles_are_retired_from_construction():
    assert "engine" not in POKEMON_ROLES
    assert "disruption_target" not in POKEMON_ROLES
    EvaluationModel.build()


def test_evaluation_model_excludes_deployment_compute_configuration():
    context = EvaluationModel.build()

    assert not hasattr(context, "compute")
    assert context.identity


def test_evaluation_model_identity_covers_canonical_card_store_content():
    context = EvaluationModel.build()
    card_id, card = next(iter(context.store.items()))
    changed = replace(context, store={**context.store, card_id: replace(
        card, name=f"{card.name} changed")})

    assert changed.configuration.identity == context.configuration.identity
    assert changed.identity != context.identity


def test_evaluation_model_identity_covers_profiles_and_valuation():
    base = EvaluationModel.build()
    profile = EvaluationModel.build(opponent_profiles={
        "fixture": OpponentProfile({}, (), (), {1: 0.5})})
    valued = EvaluationModel.build(configuration=
                                   ValuationConfiguration.general().with_values({
                                       "prize.race": 2.0}))

    assert len({base.identity, profile.identity, valued.identity}) == 3


def test_feature_catalog_identity_covers_activation_semantics():
    left = FeatureCatalog((FeatureSpec(
        "synthetic", 1.0,
        rules=(ActivationRule("function", ("draw",), "constant"),)),),
        schema_version=1)
    right = FeatureCatalog((FeatureSpec(
        "synthetic", 1.0,
        rules=(ActivationRule("function", ("fetch",), "constant"),)),),
        schema_version=1)

    assert left.priced_keys == right.priced_keys
    assert left.identity != right.identity


def test_behavior_identity_covers_every_decision_component():
    identity = BehaviorIdentity(
        "evaluator", "model", "search", "policy-model", "decision-policy",
        "fail-safe-policy", "provider", "compute", "prize-plan")

    assert tuple(identity.__dataclass_fields__) == (
        "evaluator", "evaluation_model", "search", "policy_model",
        "decision_policy", "fail_safe_policy", "provider", "compute", "prize_plan")


def test_behavior_identity_includes_the_effective_prize_plan():
    general = EvaluationModel.build(prize_plan=PrizePlan())
    offered = EvaluationModel.build(prize_plan=PrizePlan(offer=(666,)))

    assert offered.configuration.identity == general.configuration.identity
    assert offered.identity != general.identity


def test_catalog_contains_the_complete_generic_surface_without_tags_or_card_pins():
    keys = set(FEATURE_CATALOG.priced_keys)
    assert {
        "kind.pokemon", "kind.item", "kind.special_energy",
        "zone.in_play", "zone.in_hand",
        "belief.unknown_card", "context.opponent_unknown_card",
        "action.opportunity_cost", "result.win",
    } <= keys
    assert not any(key.startswith(("tag.", "card.")) for key in keys)


def test_every_active_feature_has_a_nonzero_seed():
    assert not [spec.key for spec in FEATURE_CATALOG.priced_specs
                if spec.default == 0.0]


def test_nonpriced_feature_dispositions_stay_out_of_valuation():
    catalog = FeatureCatalog((
        FeatureSpec("active", 1.0),
        FeatureSpec("old", 0.0, disposition=FeatureDisposition.ALIAS,
                    replacement="active"),
        FeatureSpec("rule", 0.0, disposition=FeatureDisposition.LEGALITY_ONLY),
        FeatureSpec("gone", 0.0, disposition=FeatureDisposition.RETIRED),
        FeatureSpec("seed-me", 0.0,
                    disposition=FeatureDisposition.AWAITING_SEED),
    ), schema_version=1)

    assert catalog.priced_keys == ("active",)


def test_unknown_card_ignores_declared_roles_and_emits_explicit_coverage():
    card_id = 999_999
    context = EvaluationModel.build()

    valuation = evaluate(ObservationStateBuilder().root(printout(me=player(hand=[card_id]))), context)
    activation = {item.feature: item.value for item in valuation.activations}

    assert not any(key.startswith("role.") for key in activation)
    assert activation["coverage.unknown_card"] >= 1.0
    assert any(f"unknown card {card_id}" in gap for gap in valuation.gaps)


def test_partial_known_card_emits_coverage_unknown_activation_and_gap():
    valuation = evaluate(ObservationStateBuilder().root(printout(me=player(hand=[1052]))), EvaluationModel.build())
    activation = {item.feature: item.value for item in valuation.activations}

    assert activation["coverage.unknown_card"] == 1.0
    assert any("incomplete card coverage 1052" in gap for gap in valuation.gaps)


def test_opponent_roles_are_belief_metadata_not_board_value():
    card_id = 999_998
    beliefs = _snapshot(
        observed_roles={card_id: ("support_pokemon",)},
        candidates=(
            ArchetypeBelief(0.25, roles={card_id: ("primary_attacker",)},
                            archetype="attacker"),
            ArchetypeBelief(0.50, roles={card_id: ("healer",)}, archetype="healer"),
        ),
        unknown_mass=0.25,
    )
    context = EvaluationModel.build(
        opponent_profiles=_profiles(beliefs))
    knowledge = LegalKnowledge(opponent=OpponentBelief.from_snapshot(beliefs))
    valuation = evaluate(ObservationStateBuilder().root(printout(
        them=player(own=False, active=body(card_id, 1))), knowledge=knowledge), context)
    activation = {item.feature: item.value for item in valuation.activations}

    assert not any(key.startswith("role.") for key in activation)
    assert activation["coverage.unknown_card"] > 0


def test_runtime_context_has_one_valuation_authority():
    context = EvaluationModel.build()
    assert not hasattr(context, "weights")


def test_general_configuration_can_replace_values_for_training_trials():
    configured = ValuationConfiguration.general().with_values({"demand.dead": -0.5})

    assert configured["demand.dead"] == -0.5


def test_partial_or_extra_configuration_refuses_at_construction():
    with pytest.raises(ValueError, match="exact catalog"):
        ValuationConfiguration(
            {"zone.in_hand": 1.0}, schema_version=FEATURE_CATALOG.schema_version)


def test_complete_deck_overlay_rejects_missing_duplicate_and_non_finite_coefficients():
    values = dict(ValuationConfiguration.general())
    with pytest.raises(ValueError, match="exact catalog"):
        DeckOverlay.complete({"zone.in_hand": 1.0})
    with pytest.raises(ValueError, match="duplicate"):
        DeckOverlay.complete([*values.items(), ("zone.in_hand", 2.0)])
    with pytest.raises(ValueError, match="finite"):
        DeckOverlay.complete({**values, "zone.in_hand": float("nan")})


def test_two_complete_deck_overlays_reverse_a_generic_state_ranking():
    general = dict(ValuationConfiguration.general())
    positive = DeckOverlay.complete({**general, "kind.item": 5.0})
    negative = DeckOverlay.complete({**general, "kind.item": -5.0})
    item = ObservationStateBuilder().root(printout(me=player(hand=[ULTRA_BALL])))
    empty = ObservationStateBuilder().root(printout(me=player(hand=[])))

    assert evaluate(item, EvaluationModel.build(overlay=positive)).total \
        > evaluate(empty, EvaluationModel.build(overlay=positive)).total
    assert evaluate(item, EvaluationModel.build(overlay=negative)).total \
        < evaluate(empty, EvaluationModel.build(overlay=negative)).total


def test_valuation_multiplies_each_activation_once_and_sums_every_contribution():
    valuation = evaluate(
        ObservationStateBuilder().root(printout(me=player(hand=[ULTRA_BALL]))),
        EvaluationModel.build())

    assert all(item.value == pytest.approx(item.activation * item.coefficient)
               for item in valuation.contributions)
    assert valuation.total == pytest.approx(sum(
        item.value for item in valuation.contributions))


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


def test_feature_catalog_executes_declared_function_rules_without_a_second_registry():
    catalog = FeatureCatalog((FeatureSpec(
        "function.synthetic", 2.0,
        rules=(ActivationRule("function", ("synthetic",), "constant"),)),),
        schema_version=99)

    activations = ActivationCompiler(catalog).compile(
        "function", {"synthetic"}, ActivationEnvironment(scale=3.0))

    assert [(item.feature, item.value) for item in activations] == [
        ("function.synthetic", 3.0)]


def test_feature_catalog_reuses_a_compiled_rule_lookup():
    catalog = FeatureCatalog((FeatureSpec(
        "function.synthetic", 2.0,
        rules=(ActivationRule("function", ("synthetic",), "constant"),)),),
        schema_version=99)

    first = catalog.activation_rules("function", {"synthetic"})

    assert catalog.activation_rules("function", ("synthetic", "synthetic")) is first


def test_every_valued_card_function_is_owned_by_a_feature_activation_rule():
    declared = {claim for spec in FEATURE_CATALOG.specs for rule in spec.rules
                if rule.source == "function" for claim in rule.claims}

    assert declared <= set(FUNCTION_CATALOG.kinds)
    assert FEATURE_CATALOG["function.draw.available"].disposition \
        is FeatureDisposition.RETIRED
    assert FEATURE_CATALOG["function.fetch.live_target"].disposition \
        is FeatureDisposition.RETIRED
    assert FEATURE_CATALOG["development.hand_line"].disposition \
        is FeatureDisposition.RETIRED


def test_every_valuation_feature_owns_a_typed_activation_rule_without_direct_bypass():
    active_specs = tuple(spec for spec in FEATURE_CATALOG.specs
                         if spec.disposition is FeatureDisposition.ACTIVE)
    assert all(spec.rules for spec in active_specs)
    assert not any(rule.source == "direct" for spec in active_specs
                   for rule in spec.rules)


def test_catalog_maps_legal_facts_to_feature_identity():
    activations = ActivationCompiler().compile(
        "observation", ("unready_active",), ActivationEnvironment(scale=-1.0))

    assert [(item.feature, item.value) for item in activations] == [
        ("active.unready_fraction", -1.0)]


def test_evaluator_identity_tracks_executable_semantics_but_not_prose(tmp_path):
    from common.ledger.decision import evaluator_semantics_identity

    source = tmp_path / "semantics.py"
    source.write_text('"""one"""\ndef value():\n    return 1\n', encoding="utf-8")
    first = evaluator_semantics_identity((source,))
    source.write_text('"""two"""\ndef value():\n    return 1\n', encoding="utf-8")
    prose_only = evaluator_semantics_identity((source,))
    source.write_text('"""two"""\ndef value():\n    return 2\n', encoding="utf-8")

    assert prose_only == first
    assert evaluator_semantics_identity((source,)) != first


def test_evaluator_identity_tracks_catalog_rule_selection_semantics(tmp_path):
    from common.ledger.decision import evaluator_semantics_identity

    source = tmp_path / "features.py"
    source.write_text(
        "def activation_rules(rule, source):\n    return rule.source == source\n",
        encoding="utf-8")
    first = evaluator_semantics_identity((source,))
    source.write_text(
        "def activation_rules(rule, source):\n    return rule.source != source\n",
        encoding="utf-8")

    assert evaluator_semantics_identity((source,)) != first


def test_behavior_component_identities_cover_all_ranking_semantic_dependencies():
    from pathlib import Path

    from common.ledger import LedgerOnePlySearch, LedgerValueEvaluator
    from common.ledger.decision import evaluator_semantics_identity
    from common.ledger import decision, search

    evaluator_paths = tuple(Path(decision.__file__).with_name(name) for name in (
        "activation.py", "capabilities.py", "evaluate.py", "features.py", "portfolio.py",
        "prizes.py", "worth.py"))
    search_paths = (
        Path(search.__file__), Path(search.__file__).with_name("chance.py"),
        Path(search.__file__).with_name("preview.py"))

    assert evaluator_semantics_identity(evaluator_paths) in LedgerValueEvaluator.identity
    assert evaluator_semantics_identity(search_paths) in LedgerOnePlySearch.identity


def test_reusable_in_play_function_emits_an_exact_capability_activation():
    valuation = evaluate(
        ObservationStateBuilder().root(printout(me=player(active=body(120, 1), hand=[]))),
        EvaluationModel.build())

    assert any(item.feature == "ability.draw_cards" and item.value > 0
               for item in valuation.activations)

    opponent = evaluate(
        ObservationStateBuilder().root(printout(them=player(own=False, active=body(120, 1), hand=[]))),
        EvaluationModel.build())
    assert any(item.feature == "ability.draw_cards" and item.value < 0
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
    with pytest.raises(TypeError, match="OpponentTrait"):
        ArchetypeBelief(1.0, traits=(object(),))
    with pytest.raises(KeyError, match="unknown opponent Trait"):
        ArchetypeBelief(1.0, traits=(OpponentTrait("typo", True),))


def test_opponent_traits_compile_through_the_full_posterior_with_provenance():
    belief = ArchetypeBelief(
        0.4, mechanics=(OpponentMechanic("item_lock", 1.0),), archetype="lock-deck")
    snapshot = _snapshot(candidates=(belief,), unknown_mass=0.6)
    context = EvaluationModel.build(
        opponent_profiles=_profiles(snapshot))
    knowledge = LegalKnowledge(opponent=OpponentBelief.from_snapshot(snapshot))

    valuation = evaluate(ObservationStateBuilder().root(printout(
        me=player(hand=[ULTRA_BALL]), them=player(own=False)), knowledge=knowledge), context)
    activation = next(item for item in valuation.activations
                      if item.feature == "mechanic.item_lock")

    assert activation.value == 0.4
    assert activation.provenance == ("cards:lock-deck:item_lock",)


def test_opening_fragility_activates_only_while_the_opponent_bench_is_empty():
    candidate = ArchetypeBelief(
        1.0, traits=(OpponentTrait("opening_fragility", True),),
        archetype="fragile-opener")
    snapshot = _snapshot(candidates=(candidate,), unknown_mass=0.0)
    context = EvaluationModel.build(opponent_profiles=_profiles(snapshot))
    knowledge = LegalKnowledge(opponent=OpponentBelief.from_snapshot(snapshot))

    empty = evaluate(ObservationStateBuilder().root(printout(
        them=player(own=False, active=body(1031, 1))), knowledge=knowledge), context)
    developed = evaluate(ObservationStateBuilder().root(printout(
        them=player(own=False, active=body(1031, 1), bench=[body(1031, 2)])),
        knowledge=knowledge), context)

    assert next(item for item in empty.activations
                if item.feature == "trait.opening_fragility").value == 1.0
    assert not any(item.feature == "trait.opening_fragility"
                   for item in developed.activations)


def test_opponent_belief_keeps_public_evidence_not_compiled_roles():
    card_id = 999_997
    state = ObservationStateBuilder().root(printout(
        them=player(own=False, active=body(card_id, 1))))
    source = OpponentSnapshot(
        OpponentEvidence.from_state(state), {card_id: ("support_pokemon",)},
        (ArchetypeBelief(
            1.0, roles={card_id: ("primary_attacker",)}, archetype="candidate"),), 0.0)
    belief = OpponentBelief.from_snapshot(source)

    assert not hasattr(belief.decision_evidence, "observed_roles")
    assert card_id in belief.decision_evidence.revealed_card_ids


def test_same_opponent_facts_have_same_value_under_different_role_labels():
    card_id = 999_996
    evidence = OpponentEvidence.from_state(ObservationStateBuilder().root(printout(
        them=player(own=False, active=body(card_id, 1)))))
    attacker = OpponentSnapshot(
        evidence, {}, (ArchetypeBelief(
            1.0, roles={card_id: ("primary_attacker",)}, archetype="candidate"),), 0.0)
    healer = OpponentSnapshot(
        evidence, {}, (ArchetypeBelief(
            1.0, roles={card_id: ("healer",)}, archetype="candidate"),), 0.0)
    knowledge = LegalKnowledge(opponent=OpponentBelief.from_snapshot(attacker))
    state = ObservationStateBuilder().root(
        printout(them=player(own=False, active=body(card_id, 1))), knowledge=knowledge)

    attacker_value = evaluate(state, EvaluationModel.build(
        opponent_profiles=_profiles(attacker)))
    healer_value = evaluate(state, EvaluationModel.build(
        opponent_profiles=_profiles(healer)))

    assert attacker_value.total == healer_value.total
    assert attacker_value.activations == healer_value.activations


def test_card_functions_compile_to_situational_feature_activations():
    valuation = evaluate(ObservationStateBuilder().root(printout(
        me=player(active=body(1031, 1), hand=[17]), them=player(own=False))),
        EvaluationModel.build())

    assert any(item.feature == "continuation.multi_provision_in_hand"
               for item in valuation.activations)
    assert any(item.feature == "function.energy.provision"
               for item in valuation.activations)


def test_schema_19_recording_migrates_to_one_combat_realization_owner():
    old = dict(ValuationConfiguration.general().values)
    old.pop("combat.realization")
    old.pop("body.development")
    old.update({
        "combat.attack_now": 0.35,
        "combat.attack_progress": 0.20,
        "combat.attack_future": 0.16,
        "combat.bench_reach": 0.10,
        "combat.active_threat": 0.12,
        "combat.line_potential": 0.40,
        "combat.prize_phase_fit": 1.0,
        "bench.developed_body": 0.30,
    })

    migrated = ValuationConfiguration.from_recorded(old, schema_version=19)

    assert migrated.schema_version == FEATURE_CATALOG.schema_version
    assert migrated["combat.realization"] == 1.0
    assert migrated["body.development"] == 0.30
