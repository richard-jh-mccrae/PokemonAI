from common.cards import FUNCTION_CATALOG
from common.cards import card_clauses, card_store
from common.cards.card_facts import Clause
from common.ledger.coverage import (
    CLAUSE_PARAMETER_CONTRACTS,
    CLAUSE_PARAMETER_DIRECTION_CONTRACTS,
    CLAUSE_PARAMETER_DIRECT_EQUATIONS,
    CLAUSE_PRIMARY_PARAMETER_FEATURES,
    CLAUSE_PARAMETER_PLACEMENT_CONTRACTS,
    CLAUSE_VALUATION_CONTRACTS,
    DIRECT_CAPABILITY_CLAUSES,
    OBSERVATION_FIELD_EXPECTATIONS,
    OBSERVATION_FIELD_FEATURES,
    OBSERVATION_FIELD_OWNERS,
    ClauseValuationMode,
    clause_parameter_expected_direction,
    clause_parameter_mode,
    card_coverage_gap,
    SUCCESSOR_CLAUSES,
    clause_contract_findings,
    clause_parameter_findings,
    observation_contract_findings,
    unowned_clause_kinds,
    unowned_observation_fields,
)
from common.ledger.features import CLAUSE_PARAMETER_DEFAULTS, FEATURE_CATALOG
from common.ledger.capabilities import card_option_units
from common.ledger import EvaluationModel
from common.observation import ObservationStateBuilder
from ledger_helpers import body, player, printout


def test_every_observation_field_has_a_value_legal_belief_or_identity_owner():
    assert unowned_observation_fields() == ()
    assert observation_contract_findings() == ()


def test_runtime_and_readiness_share_the_card_coverage_verdict():
    assert card_coverage_gap(858, card_store()[858]) == (
        "incomplete card coverage 858 (partial)")


def test_every_value_or_belief_field_names_a_seeded_feature_witness():
    assert OBSERVATION_FIELD_FEATURES
    assert not {feature for features in OBSERVATION_FIELD_FEATURES.values()
                for feature in features if feature not in FEATURE_CATALOG}
    assert set(OBSERVATION_FIELD_EXPECTATIONS) == {
        f"{node.__name__}.{name}"
        for node, owners in OBSERVATION_FIELD_OWNERS.items()
        for name in owners
    }


def test_every_clause_is_directly_valued_or_owned_by_engine_successor_differencing():
    assert unowned_clause_kinds() == ()
    assert not DIRECT_CAPABILITY_CLAUSES & SUCCESSOR_CLAUSES


def test_clause_contracts_explicitly_cover_the_authoritative_catalog():
    assert set(CLAUSE_VALUATION_CONTRACTS) == set(FUNCTION_CATALOG.kinds)
    assert all(contract.features and contract.witness
               for contract in CLAUSE_VALUATION_CONTRACTS.values())
    assert not {feature for contract in CLAUSE_VALUATION_CONTRACTS.values()
                for feature in contract.features if feature not in FEATURE_CATALOG}


def test_every_clause_parameter_and_deployed_value_has_an_explicit_contract():
    assert CLAUSE_PARAMETER_CONTRACTS
    assert clause_parameter_findings() == ()
    assert set(CLAUSE_PARAMETER_DIRECT_EQUATIONS) == {
        name for name, mode in CLAUSE_PARAMETER_CONTRACTS.items()
        if mode is ClauseValuationMode.DIRECT_EQUATION
    }
    assert set(CLAUSE_PARAMETER_DEFAULTS) == {
        name for name, equation in CLAUSE_PARAMETER_DIRECT_EQUATIONS.items()
        if equation == "evaluate._situational_functions"
        or name in {"cost", "rider", "target"}
    }
    assert not {
        name for name in CLAUSE_PARAMETER_DEFAULTS
        if f"clause.parameter.{name}" not in FEATURE_CATALOG
    }
    assert set(CLAUSE_PARAMETER_DIRECTION_CONTRACTS) == set(
        CLAUSE_PARAMETER_DEFAULTS)
    assert set(CLAUSE_PRIMARY_PARAMETER_FEATURES) == {
        (parameter, clause.kind)
        for facts in card_store().values()
        for clause in card_clauses(facts)
        for parameter in clause.params
        if parameter not in CLAUSE_PARAMETER_DEFAULTS
    }
    assert not {
        feature for feature in CLAUSE_PRIMARY_PARAMETER_FEATURES.values()
        if feature not in FEATURE_CATALOG
    }


def test_semantic_qualifier_directions_are_explicit_and_board_correct():
    assert clause_parameter_expected_direction(
        "distinct_types", True, Clause("fetch", distinct_types=True)) == 1
    assert clause_parameter_expected_direction(
        "no_ability", True, Clause("fetch", no_ability=True)) == 1
    assert clause_parameter_expected_direction(
        "no_rule_box", True, Clause("fetch", no_rule_box=True)) == 1
    assert clause_parameter_expected_direction(
        "source_class", "ex", Clause("prevent_damage", source_class="ex")) == 1
    assert clause_parameter_expected_direction(
        "target_class", "ex", Clause("damage_boost", target_class="ex")) == 1
    assert clause_parameter_expected_direction(
        "target_condition", "not_played_this_turn",
        Clause("fetch", target_condition="not_played_this_turn")) == 1
    assert clause_parameter_expected_direction(
        "exclude_name", "Froslass", Clause(
            "checkup_trigger", effect="damage_counters",
            exclude_name="Froslass")) == 1
    assert clause_parameter_expected_direction(
        "exclude_name", "Pecharunt ex", Clause(
            "self_switch", exclude_name="Pecharunt ex")) == -1
    assert clause_parameter_expected_direction(
        "rider_amount", 30, Clause(
            "damage_boost", rider="recoil", rider_amount=30)) == -1
    assert clause_parameter_expected_direction(
        "symmetric", True, Clause(
            "stadium_static", effect="damage_counters", symmetric=True)) == 1
    assert clause_parameter_expected_direction(
        "symmetric", True, Clause(
            "stadium_static", effect="damage_reduction", symmetric=True)) == -1
    assert clause_parameter_expected_direction(
        "target", "both_actives", Clause(
            "ko", target="both_actives")) == -1


def test_value_and_placement_specific_parameter_paths_use_direct_equations():
    assert CLAUSE_PARAMETER_PLACEMENT_CONTRACTS
    assert clause_parameter_mode(
        "rider", "discard_own_energy", "trainer", "heal") \
        is ClauseValuationMode.DIRECT_EQUATION
    assert clause_parameter_mode(
        "rider", "self_switch", "trainer", "gust") \
        is ClauseValuationMode.DIRECT_EQUATION
    assert clause_parameter_mode(
        "rider", "discard_basic_f_energy", "ability", "draw") \
        is ClauseValuationMode.DIRECT_EQUATION


def test_conditional_amount_parameter_changes_the_direct_draw_equation():
    context = EvaluationModel.build()
    rocket = ObservationStateBuilder().root(printout(me=player(
        active=body(414, 1), bench=[body(399, 2)], hand=[1216])))
    mixed = ObservationStateBuilder().root(printout(me=player(
        active=body(414, 1), bench=[body(1031, 2)], hand=[1216])))

    rocket_units = card_option_units(
        card_store()[1216], rocket.me, rocket.them, rocket, context)
    mixed_units = card_option_units(
        card_store()[1216], mixed.me, mixed.them, mixed, context)

    assert rocket_units.draw > mixed_units.draw


def test_an_unlisted_clause_cannot_be_automatically_owned_as_a_successor():
    contracts = {"draw": CLAUSE_VALUATION_CONTRACTS["draw"]}

    assert clause_contract_findings(("draw", "synthetic"), contracts) == (
        "missing clause contract: synthetic",
    )


def test_clause_contracts_have_one_closed_primary_mode():
    assert {contract.mode for contract in CLAUSE_VALUATION_CONTRACTS.values()} == {
        ClauseValuationMode.DIRECT_EQUATION,
    }
