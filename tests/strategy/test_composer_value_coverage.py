"""Issue #493 static Composer valuation-coverage census."""
from __future__ import annotations

import collections
import dataclasses
import json
import sys
from pathlib import Path

import pytest

from common import apply_option as seam
from common import snapshot_coverage
from common import state_value


ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import composer_value_coverage as coverage  # noqa: E402


@pytest.fixture(scope="module")
def inventory():
    return coverage.build_inventory()


def records(inventory, source_kind):
    return tuple(record for record in inventory.records if record.source_kind == source_kind)


def one(inventory, mechanic_key):
    matches = [record for record in inventory.records if record.mechanic_key == mechanic_key]
    assert len(matches) == 1, (mechanic_key, len(matches))
    return matches[0]


def test_locked_audit_record_schema_is_exact_and_immutable():
    assert [field.name for field in dataclasses.fields(coverage.AuditRecord)] == [
        "mechanic_key",
        "source_kind",
        "source_symbol_or_site",
        "transition_fate",
        "written_dimensions",
        "absolute_owners",
        "local_owners",
        "runtime_callers",
        "leaf_path",
        "search_path",
        "classification",
        "search_overlay",
        "evidence",
        "deliberate_ruling",
        "exposure",
        "live_owner",
    ]
    assert coverage.AuditRecord.__dataclass_params__.frozen
    assert coverage.Inventory.__dataclass_params__.frozen
    assert coverage.EquationCandidate.__dataclass_params__.frozen
    assert [field.name for field in dataclasses.fields(coverage.EquationCandidate)] == [
        "key", "path", "line", "disposition", "reason", "runtime_callers",
        "absolute_owners", "local_owners", "classification",
    ]
    assert tuple(coverage.CLASSIFICATIONS) == (
        "SHARED-EXACT", "LEAF-ONLY", "LOCAL-ONLY", "LOSSY-REEXPRESSION",
        "DUPLICATE/CONFLICT", "UNVALUED-MODELED", "DELIBERATE-ZERO",
        "UNKNOWN/REFUSED", "SEARCH-LOSS",
    )


def test_positive_control_exactly_reproduces_the_legacy_exposure_census():
    control = coverage.legacy_positive_control()
    assert control.matched
    assert control.legacy_digest == control.census_digest
    assert (control.pool_cards, control.sites) == (383, 412)
    assert dict(control.fate_counts) == {
        seam.MODELLED: 323,
        seam.ENGINE_RESOLVED: 43,
        seam.REFUSED: 46,
    }


def test_completeness_uses_all_cards_not_the_legacy_exposure_pool(inventory):
    populations = dict(inventory.populations)
    assert populations["all_cards"] == 1267
    assert populations["apply_sites"] == 1344
    assert populations["terminal_attacks"] == 1556
    assert populations["passive_abilities"] == 114
    assert len(records(inventory, "card-effect-site")) == populations["apply_sites"]
    assert len(records(inventory, "terminal-attack-site")) == populations["terminal_attacks"]
    assert len(records(inventory, "passive-ability-site")) == populations["passive_abilities"]
    assert populations["apply_sites"] > coverage.legacy_positive_control().sites

    fates = collections.Counter(
        record.transition_fate for record in records(inventory, "card-effect-site"))
    assert fates == {seam.MODELLED: 1152, seam.ENGINE_RESOLVED: 96, seam.REFUSED: 96}


def test_every_source_site_has_one_stable_inventory_identity(inventory):
    source = coverage.source_sites()
    audited = records(inventory, "card-effect-site")
    expected = {
        f"card {site.card_id} {site.name} / {site.label} / site {site.ordinal}"
        for site in source
    }
    actual = {record.source_symbol_or_site for record in audited}
    assert len(source) == len(audited) == len(expected) == len(actual)
    assert actual == expected
    assert all(record.mechanic_key.startswith("card-site:") for record in audited)


def test_site_ownership_separates_transport_from_clause_writes(inventory):
    attach = next(
        record for record in records(inventory, "card-effect-site")
        if record.source_symbol_or_site.startswith("card 14 Spiky Energy")
    )
    assert "my_hand_ids" in attach.written_dimensions
    assert "state:hand" not in attach.absolute_owners
    assert "common.needs.assignment_value" not in attach.local_owners

    bounce = next(
        record for record in records(inventory, "card-effect-site")
        if "Wally's Compassion" in record.source_symbol_or_site
    )
    assert "my_hand_ids" in bounce.written_dimensions
    assert "state:hand" in bounce.absolute_owners
    assert "common.needs.assignment_value" in bounce.local_owners


def test_printed_attacks_are_terminal_leaf_evidence_not_fake_local_claimants(inventory):
    attacks = records(inventory, "terminal-attack-site")
    assert attacks
    assert all(record.classification == coverage.LEAF_ONLY for record in attacks)
    assert all(record.absolute_owners == ("terminal:attack_ev",) for record in attacks)
    assert all(not record.local_owners for record in attacks)


def test_option_kind_join_is_total_and_keeps_terminal_outside_fates(inventory):
    option_records = records(inventory, "option-kind")
    assert len(option_records) == len(seam.KIND_COVERAGE) == 17
    by_name = {record.mechanic_key.removeprefix("option-kind:"): record
               for record in option_records}
    assert set(by_name) == {name.lower() for _kind, name in coverage.OPTION_KINDS}
    assert by_name["attack"].transition_fate == seam.TERMINAL
    assert by_name["end"].transition_fate == seam.TERMINAL
    assert seam.TERMINAL not in seam.FATES
    assert by_name["number"].classification == coverage.UNKNOWN_REFUSED
    assert by_name["attack"].classification == coverage.LEAF_ONLY
    assert by_name["end"].classification == coverage.DELIBERATE_ZERO
    assert not by_name["end"].absolute_owners
    assert "ADR-0129" in by_name["end"].deliberate_ruling


def test_writable_dimension_join_is_total_without_nominal_overclaims(inventory):
    zone_records = records(inventory, "writable-state")
    assert {record.written_dimensions[0] for record in zone_records} == set(
        snapshot_coverage.BY_ID)
    assert len(zone_records) == len(snapshot_coverage.WRITABLE) == 25
    grouped = inventory.records_by_written_dimension()
    assert set(snapshot_coverage.BY_ID) <= set(grouped)

    # The family registry explicitly declares these blind. A related board fact is not ownership.
    for dimension in ("my_deck_count", "their_deck_count", "special_conditions"):
        summary = inventory.owner_summary(dimension)
        assert not summary.absolute_owners
        assert not summary.terminal_owners
        assert one(inventory, f"state-dimension:{dimension}").classification == coverage.UNVALUED_MODELLED

    # Attach/supporter currencies constrain the shared Budget; the remaining usage markers are
    # structural legality reads rather than invented leaf/local owners.
    for dimension in ("allowance_energy_attached", "allowance_supporter_played"):
        marker = one(inventory, f"state-dimension:{dimension}")
        assert marker.absolute_owners == ("state:readiness", "state:threat")
        assert "composer:state_value leaf" in marker.search_path
        assert any(path.startswith("composer:_still_legal@") for path in marker.search_path)
    for dimension in (
        "allowance_ability_used", "allowance_retreat_used", "allowance_stadium_played",
    ):
        summary = inventory.owner_summary(dimension)
        assert not summary.absolute_owners
        assert not summary.terminal_owners
        marker = one(inventory, f"state-dimension:{dimension}")
        assert any(path.startswith("composer:_still_legal@") for path in marker.search_path)

    for dimension in ("allowance_supporter_played", "allowance_stadium_played", "new_in_play"):
        marker = one(inventory, f"state-dimension:{dimension}")
        assert not marker.local_owners
    assert one(inventory, "state-dimension:new_in_play").search_path == (
        "composer:_still_legal@308",)

    boosts = one(inventory, "state-dimension:this_turn_damage_boosts")
    assert boosts.absolute_owners == (
        "state:readiness", "state:threat", "terminal:attack_ev")

    tools = one(inventory, "state-dimension:attached_tools")
    assert tools.classification == coverage.LOSSY_REEXPRESSION
    assert tools.absolute_owners == ("state:readiness", "state:threat", "terminal:attack_ev")
    assert tools.local_owners == ("common.deciders.attach.AttachMixin._tool_attach_value",)
    assert tools.live_owner == "#494"
    assert "mixed Tool classes" in " ".join(tools.evidence)

    retreat = one(inventory, "state-dimension:allowance_retreat_used")
    assert retreat.classification == coverage.LOCAL_ONLY
    assert not retreat.absolute_owners
    assert retreat.live_owner == "ADR-0135"


def test_zone_and_selector_exposure_preserves_occurrences_not_only_unique_cards(inventory):
    sites = coverage.source_sites()
    expected = [site.card_id for site in sites if "my_hand_ids" in coverage._site_writes(site)]
    hand = one(inventory, "state-dimension:my_hand_ids")
    assert hand.exposure.cards == len(set(expected))
    assert hand.exposure.mechanic_sites == len(expected)
    assert hand.exposure.mechanic_sites > hand.exposure.cards

    _values, selectors = coverage._clause_population(coverage.apply_census.load_effects())
    assert len(selectors[("zone", "deck")]) == 48
    assert len(set(selectors[("zone", "deck")])) == 35
    assert len(selectors[("condition", "coin_tails")]) == 3


def test_energy_is_lossy_and_prize_counts_are_leaf_only(inventory):
    energy = one(inventory, "state-dimension:attached_energy")
    assert energy.classification == coverage.LOSSY_REEXPRESSION
    assert "state:readiness" in energy.absolute_owners
    assert "common.deciders.attach.AttachMixin._attach_value" in energy.local_owners
    assert "terminal:attack_ev" in energy.absolute_owners
    assert energy.live_owner == "#495"
    assert coverage._measured_factor(energy, "local_leaf_disagreement") == 1.2

    for dimension in ("my_prizes", "their_prizes"):
        prize = one(inventory, f"state-dimension:{dimension}")
        assert prize.classification == coverage.LEAF_ONLY
        assert prize.absolute_owners == ("state:prize_race",)
        assert prize.local_owners == ()


def test_clause_parameter_selector_and_family_populations_close(inventory):
    clause = records(inventory, "effect-clause-value")
    assert {record.mechanic_key.removeprefix("effect-clause:") for record in clause} == set(
        snapshot_coverage.CLAUSE_WRITES)
    assert len(records(inventory, "effect-clause-parameter")) == len(
        snapshot_coverage.CLAUSE_PARAMETERS) == 40
    assert len(records(inventory, "effect-clause-selector")) == sum(
        len(values) for values in snapshot_coverage.CLAUSE_SELECTORS.values()) == 76

    deliberate = (*records(inventory, "effect-clause-parameter"),
                  *records(inventory, "effect-clause-selector"))
    assert deliberate
    assert all(record.classification == coverage.DELIBERATE_ZERO for record in deliberate)
    assert all(record.deliberate_ruling for record in deliberate)
    assert all(record.live_owner != "#493 audit registry" for record in deliberate)

    state = records(inventory, "state-value-family")
    terminal = records(inventory, "terminal-family")
    assert {record.mechanic_key.rsplit(":", 1)[-1] for record in state} == set(
        state_value.FAMILIES)
    assert {record.mechanic_key.rsplit(":", 1)[-1] for record in terminal} == set(
        state_value.TERMINAL_FAMILIES)


def test_provider_primary_rows_are_shipped_nondefault_and_declarations_stay_closed(inventory):
    ledger = inventory.provider_fields
    assert {(item.class_name, item.field_name) for item in ledger} == set(
        coverage._provider_members())
    primary = (*records(inventory, "card-stat"), *records(inventory, "attack-stat"))
    primary_symbols = {tuple(record.source_symbol_or_site.rsplit(".", 2)[-2:])
                       for record in primary}
    primary_keys = {(parts[0], parts[1]) for parts in primary_symbols}
    observed = {(item.class_name, item.field_name) for item in ledger if item.observed_nondefault}
    assert primary_keys == observed
    assert all(item.observed_cards or item.override_sites for item in ledger
               if item.observed_nondefault)
    assert all("observed non-default" in " ".join(record.evidence) for record in primary)
    assert ("CardStat", "cardType") not in {
        (item.class_name, item.field_name) for item in ledger}
    assert not [record for record in primary if record.mechanic_key.endswith(":cardType")]

    reduction = one(inventory, "provider-stat:cardstat:attackCostReduction")
    assert reduction.classification == coverage.UNVALUED_MODELLED
    assert not reduction.runtime_callers
    assert "no runtime attribute reader" in " ".join(reduction.evidence)

    retreat = one(inventory, "provider-stat:cardstat:retreatReduction")
    assert "common.retreat_cost:attached_retreat_delta@35" in retreat.runtime_callers
    assert not [caller for caller in retreat.runtime_callers if "plan.cost" in caller]
    assert retreat.classification == coverage.LOCAL_ONLY
    assert not retreat.absolute_owners
    assert retreat.local_owners == (
        "common.deciders.attach.AttachMixin._tool_attach_value",
        "common.retreat_cost.effective_retreat_cost",
    )
    assert retreat.live_owner == "ADR-0135"
    free_at_hp = one(inventory, "provider-stat:cardstat:retreatFreeAtHp")
    assert free_at_hp.runtime_callers == ("common.retreat_cost:effective_retreat_cost@65",)
    for field in ("retreatFreeAtHp", "retreatFreeGrant"):
        mobility = one(inventory, f"provider-stat:cardstat:{field}")
        assert mobility.classification == coverage.LOCAL_ONLY
        assert not mobility.absolute_owners
        assert mobility.local_owners == ("common.retreat_cost.effective_retreat_cost",)
        assert mobility.live_owner == "ADR-0135"
        assert "ADR-0135 accepted" in " ".join(mobility.evidence)

    hp_bonus = one(inventory, "provider-stat:cardstat:hpBonus")
    assert hp_bonus.classification == coverage.LOSSY_REEXPRESSION
    assert hp_bonus.written_dimensions == ("damage_counters",)
    assert hp_bonus.absolute_owners == ("state:survival",)
    assert not hp_bonus.local_owners
    assert hp_bonus.live_owner == "#494"
    assert "integer turns_to_ko_me" in " ".join(hp_bonus.evidence)
    assert "no local value owner remains" in " ".join(hp_bonus.evidence)

    attack_cost = one(inventory, "provider-stat:attackstat:cost")
    assert attack_cost.runtime_callers == (
        "common.deciders.tactical:TacticalMixin._valued_attack_types@209",
        "common.strategy.combat_math.cards:CardFactsMixin.attack_cost@22",
        "common.strategy.combat_math.energy:EnergyMixin._attack_slots@218",
    )
    assert {"state:readiness", "terminal:attack_ev"} <= set(attack_cost.absolute_owners)
    assert "common.strategy.combat_math.reach.ReachMixin.best_affordable_ko_value" in (
        attack_cost.local_owners)
    assert attack_cost.classification == coverage.LOSSY_REEXPRESSION

    for field, caller in {
        "damageReduction": "common.strategy.damage:compute_active_damage@118",
        "damageReductionTypes": "common.strategy.damage:compute_active_damage@119",
        "preventsDamageAtLeast": "common.strategy.damage:compute_active_damage@122",
        "preventsDamageFrom": "common.strategy.damage:_prevented@142",
        "resistance": "common.strategy.damage:compute_active_damage@114",
    }.items():
        record = one(inventory, f"provider-stat:cardstat:{field}")
        assert caller in record.runtime_callers
        assert "terminal:attack_ev" in record.absolute_owners

    prize = one(inventory, "provider-stat:cardstat:prize_value")
    assert prize.classification == coverage.LOSSY_REEXPRESSION
    assert prize.absolute_owners == ("state:survival", "terminal:attack_ev")
    assert "different economics" in " ".join(prize.evidence)

    snipe = one(inventory, "provider-stat:attackstat:benchSnipe")
    assert snipe.classification == coverage.LOSSY_REEXPRESSION
    assert snipe.absolute_owners == ("state:threat", "terminal:attack_ev")
    assert "common.state_model:StateModel._attack_profile@1365" in snipe.runtime_callers
    assert "StateModel._attack_profile" in " ".join(snipe.evidence)

    recoil = one(inventory, "provider-stat:attackstat:recoil")
    assert recoil.classification == coverage.LOCAL_ONLY
    assert not recoil.absolute_owners
    assert recoil.local_owners == (
        "common.composer._survives_recoil",
        "common.deciders.hand.HandMixin._is_simultaneous_draw",
        "common.deciders.tactical.TacticalMixin._recoil_flips_doom",
    )
    assert recoil.search_path == ("composer:_selection_candidates",)
    assert "terminal attack_ev explicitly declares recoil blind" in " ".join(recoil.evidence)

    for field in ("nextTurnSameAttackLock", "nextTurnSelfLock"):
        lock = one(inventory, f"provider-stat:attackstat:{field}")
        assert lock.classification == coverage.LOSSY_REEXPRESSION
        assert lock.absolute_owners == ("terminal:attack_ev",)
        assert lock.local_owners == ("common.deciders.deny.DenyMixin._lock_sequence_cost",)
        assert "StateModel._attack_profile copies" in " ".join(lock.evidence)
        assert "live tactical damage-scale lock equation" in " ".join(lock.evidence)

    for field in ("damageBoost", "damageBoostType", "damageBoostVsEx"):
        boost = one(inventory, f"provider-stat:cardstat:{field}")
        assert boost.classification == coverage.LOSSY_REEXPRESSION
        assert boost.absolute_owners == (
            "state:readiness", "state:threat", "terminal:attack_ev")
        assert boost.local_owners == (
            "common.deciders.board_build.BoardMixin._typed_boost_total",
            "common.deciders.lethal.LethalMixin._boost_lethal_tactical",
        )
        assert "shared damage context" in " ".join(boost.evidence)

    special = one(inventory, "provider-stat:cardstat:is_special_energy")
    assert special.classification == coverage.LOSSY_REEXPRESSION
    assert special.absolute_owners == ("state:readiness",)
    assert special.local_owners == ("common.deciders.attach.AttachMixin._attach_value",)
    assert special.runtime_callers == (
        "common.strategy.combat_math.energy:EnergyMixin._special_energy_groups@103",)

    for field in ("nextTurnPreventAll", "nextTurnReduction", "nextTurnSelfBonus"):
        transient = one(inventory, f"provider-stat:attackstat:{field}")
        assert transient.classification == coverage.LEAF_ONLY
        assert transient.absolute_owners == (
            "state:readiness", "state:survival", "state:threat", "terminal:attack_ev")
        assert not transient.local_owners
        assert "TransientTracker._grant_fields" in " ".join(transient.evidence)

    self_return = one(inventory, "provider-stat:attackstat:selfReturn")
    assert self_return.classification == coverage.LOCAL_ONLY
    assert not self_return.absolute_owners
    assert self_return.local_owners == (
        "common.deciders.tactical.TacticalMixin._self_return_escape_credit",)

    for field in ("ex", "megaEx", "is_ex_body"):
        ex_gate = one(inventory, f"provider-stat:cardstat:{field}")
        assert ex_gate.classification == coverage.LOSSY_REEXPRESSION
        assert ex_gate.absolute_owners == (
            "state:readiness", "state:survival", "state:threat", "terminal:attack_ev")
        assert "canonical" in " ".join(ex_gate.evidence)
    for field in ("holderNameFamily", "holderNoRuleBox"):
        holder_gate = one(inventory, f"provider-stat:cardstat:{field}")
        assert holder_gate.classification == coverage.LOSSY_REEXPRESSION
        assert "CardStat.applies_to_holder reads" in " ".join(holder_gate.evidence)
        assert "backing read collapsed" in " ".join(holder_gate.evidence)
    is_tool = one(inventory, "provider-stat:cardstat:is_tool")
    assert is_tool.absolute_owners == (
        "state:readiness", "state:survival", "state:threat", "terminal:attack_ev")
    is_energy = one(inventory, "provider-stat:cardstat:is_energy")
    assert is_energy.absolute_owners == ("state:readiness",)
    assert "unrelated state family" in " ".join(is_energy.evidence)
    assert one(inventory, "provider-stat:cardstat:is_item").absolute_owners == ()
    assert one(inventory, "provider-stat:cardstat:is_supporter").absolute_owners == (
        "state:readiness", "state:threat")
    stadium_class = one(inventory, "provider-stat:cardstat:is_stadium")
    assert stadium_class.absolute_owners == (
        "state:readiness", "state:survival", "state:threat")
    assert stadium_class.search_path == ("composer:_still_legal", "composer:state_value leaf")

    max_damage = one(inventory, "provider-stat:cardstat:maxDamage")
    hand_damage = one(inventory, "provider-stat:cardstat:handSizeDamage")
    assert max_damage.classification == coverage.LOSSY_REEXPRESSION
    assert hand_damage.classification == coverage.LOSSY_REEXPRESSION
    assert coverage.DUPLICATE_CONFLICT not in {
        max_damage.classification, hand_damage.classification}
    assert set(max_damage.absolute_owners) < {
        *(f"state:{name}" for name in state_value.FAMILIES), "terminal:attack_ev"}
    assert hand_damage.absolute_owners == ("state:survival",)

    scale = one(inventory, "provider-stat:attackstat:scaleFilter")
    scale_field = next(field for field in ledger
                       if (field.class_name, field.field_name) == ("AttackStat", "scaleFilter"))
    assert (scale_field.observed_sites, scale_field.override_sites) == (0, 2)
    assert scale.exposure.cards == 0
    assert scale.exposure.mechanic_sites == 2
    assert "card/deck/corpus exposure unmeasured" in " ".join(scale.evidence)

    shared = {
        record.mechanic_key for record in inventory.records
        if record.classification == coverage.SHARED_EXACT
    }
    assert shared == {
        "equation:common-state-model-myside-forward-payoff",
        "equation:common-state-model-myside-role-worth-of",
        "equation:common-state-model-sidebase-attack-payoff",
        "equation:common-strategy-combat-math-budget-budget-realising-p",
        "equation:common-strategy-combat-math-harvest-harvestmixin-snipe-ko-prizes",
        "equation:common-strategy-combat-math-harvest-harvestmixin-spread-ko-prizes",
        "equation:common-strategy-combat-math-reach-reachmixin-readiness-p",
    }


def test_equation_ast_population_is_dispositioned_and_drift_gated(inventory):
    candidates = inventory.equation_candidates
    assert len(candidates) == dict(inventory.populations)["equation_candidates"] == 693
    assert collections.Counter(candidate.disposition for candidate in candidates) == {
        "excluded": 433, "owner": 187, "consumer": 73}
    assert {candidate.disposition for candidate in candidates} == {"owner", "consumer", "excluded"}
    assert all(candidate.reason for candidate in candidates)
    assert all(candidate.classification in coverage.CLASSIFICATIONS
               for candidate in candidates if candidate.disposition != "excluded")
    assert all(not candidate.classification
               for candidate in candidates if candidate.disposition == "excluded")
    emitted = (*records(inventory, "local-equation"), *records(inventory, "value-consumer"))
    assert len(emitted) == sum(candidate.disposition != "excluded" for candidate in candidates)
    assert all(record.classification in coverage.CLASSIFICATIONS[:-1] for record in emitted)
    assert not [candidate for candidate in candidates
                if "shared model/combat/search consumer" in candidate.reason
                or "required-scope supporting helper" in candidate.reason]
    assert coverage._digest(candidate.key for candidate in candidates) == (
        coverage.EQUATION_BASELINE_SHA256)
    definitions, _calls, _providers = coverage._source_index()
    required = {
        definition.key for definition in definitions
        if coverage._required_equation_scope(definition) or coverage._named_equation(definition)
    }
    assert {candidate.key for candidate in candidates} == required


def test_equation_semantics_and_qualified_callers_are_pinned(inventory):
    by_key = {candidate.key: candidate for candidate in inventory.equation_candidates}
    expected = {
        "common.retreat_cost:effective_retreat_cost": (
            "owner", coverage.LOCAL_ONLY, (),
            ("common.board_choice:_retreat_space@327",
             "common.deciders.promote:PromoteRetreatMixin._effective_retreat_cost@323")),
        "common.deciders.heal:HealMixin._heal_bounce_cost": (
            "owner", coverage.LOSSY_REEXPRESSION,
            ("state:readiness", "terminal:attack_ev"),
            ("common.deciders.heal:HealMixin._heal_target_tactical@95",)),
        "common.strategy.combat_math.clocks:ClockMixin.survival_clock": (
            "consumer", coverage.LEAF_ONLY, ("state:survival",),
            ("common.state_model:TheirSide.survival_clock@1104",
             "common.strategy.combat_math.clocks:ClockMixin.turns_to_ko_me@190")),
        "common.strategy.combat_math.energy:EnergyMixin._attack_slots": (
            "consumer", coverage.LEAF_ONLY, ("state:readiness", "terminal:attack_ev"),
            ("common.strategy.combat_math.energy:EnergyMixin.matched_slots@319",
             "common.strategy.combat_math.energy:EnergyMixin.reachable_attach@233",
             "common.strategy.combat_math.energy:EnergyMixin.reachable_attach_p@254",
             "common.strategy.combat_math.reach:ReachMixin.attack_realising_p@123",
             "common.strategy.combat_math.reach:ReachMixin.best_affordable_ko_value@158")),
        "common.strategy.combat_math.reach:ReachMixin.best_affordable_ko_value": (
            "owner", coverage.LOSSY_REEXPRESSION, ("terminal:attack_ev",),
            ("common.deciders.lethal:LethalMixin._best_affordable_ko_value@230",)),
        "common.deciders.deny:DenyMixin._lock_sequence_cost": (
            "owner", coverage.LOSSY_REEXPRESSION, ("terminal:attack_ev",),
            ("common.deciders.tactical:TacticalMixin._copied_attack_tactical@119",
             "common.deciders.tactical:TacticalMixin._tactical@49")),
        "common.strategy.planning.leaf:LeafValueMixin._leaf_value": (
            "owner", coverage.LOSSY_REEXPRESSION,
            ("state:development", "state:prize_race", "state:readiness", "state:survival",
             "state:threat", "terminal:attack_ev"),
            ("common.strategy.planning.ladder:GoalLadderMixin._ko_for_prizes_lines@204",
             "common.strategy.planning.ladder:GoalLadderMixin._ko_key_threat_lines@268")),
        "common.strategy.combat_math.reach:ReachMixin.readiness_p": (
            "owner", coverage.SHARED_EXACT, ("state:readiness",),
            ("common.state_model:MySide.readiness_p@852",)),
        "common.state_model:MySide.readiness_p": (
            "consumer", coverage.LEAF_ONLY, ("state:readiness",),
            ("common.state_value:_readiness_odds@793",)),
        "common.state_model:MySide._forward_payoff": (
            "owner", coverage.SHARED_EXACT, ("state:development",),
            ("common.state_model:MySide.forward_payoff@916",)),
        "common.state_model:MySide.forward_payoff": (
            "consumer", coverage.LEAF_ONLY, ("state:development",),
            ("common.state_value:_development_legs@855",)),
        "common.strategy.combat_math.forward:ForwardLineMixin.forward_payoff_terms": (
            "owner", coverage.LOCAL_ONLY, (),
            ("common.state_model:TheirSide.forward_payoff@1140",
             "common.strategy.doctrines.doctrine_gust:GustMixin._gust_forward_denial@137")),
    }
    for key, (disposition, classification, owners, callers) in expected.items():
        candidate = by_key[key]
        assert (candidate.disposition, candidate.classification) == (disposition, classification)
        assert candidate.absolute_owners == owners
        assert candidate.runtime_callers == callers

    build = by_key["common.deciders.attach:AttachMixin._attach_build_delta"]
    assert build.runtime_callers == (
        "common.deciders.attach:AttachMixin._accel_routed_value@168",
        "common.deciders.attach:AttachMixin._attach_value@282",
    )
    tool = by_key["common.deciders.attach:AttachMixin._tool_attach_value"]
    assert tool.classification == coverage.LOCAL_ONLY
    assert not tool.absolute_owners
    assert "ADR-0135" in tool.reason
    assert not [owner for candidate in by_key.values() for owner in candidate.absolute_owners
                if owner in {"state:semantic-counterpart", "state:shared",
                             "state:registered-family", "state:composed-score"}]

    assert by_key["common.deciders.attach:AttachMixin._line_payoff_stat"].disposition == "excluded"
    assert by_key[
        "common.deciders.lines:LineMixin._payoff_immediate_preevo_available"
    ].disposition == "excluded"
    for key in (
        "common.deciders.lethal:LethalMixin._best_affordable_ko_value",
        "common.deciders.order:OrderMixin._score_order",
    ):
        assert by_key[key].disposition == "excluded"
        assert not by_key[key].local_owners
    for key in (
        "common.deciders.attach:AttachMixin._attach_progress",
        "common.deciders.heal:HealMixin._heal_target_tactical",
    ):
        assert by_key[key].disposition == "consumer"
        assert by_key[key].classification == coverage.LOSSY_REEXPRESSION
        assert not by_key[key].local_owners


def test_live_numeric_equations_close_across_required_modules(inventory):
    by_key = {candidate.key: candidate for candidate in inventory.equation_candidates}
    expected = {
        # Reach: printed local maximum versus the two registry-owned threat gates.
        "common.strategy.combat_math.reach:ReachMixin.best_reachable_damage": (
            "owner", coverage.LOCAL_ONLY, (),
            ("common.deciders.attach:AttachMixin._attach_value@316",
             "common.state_model:MySide.best_reachable_damage._make@818")),
        "common.strategy.combat_math.reach:ReachMixin.best_reachable_damage_vs": (
            "consumer", coverage.LEAF_ONLY, ("state:threat",),
            ("common.state_model:MySide.best_reachable_damage_vs@831",)),
        "common.strategy.combat_math.reach:ReachMixin.best_reachable_bench_damage": (
            "consumer", coverage.LEAF_ONLY, ("state:threat",),
            ("common.state_model:MySide.best_reachable_bench_damage@843",)),
        "common.strategy.combat_math.reach:ReachMixin.best_affordable_damage": (
            "owner", coverage.LOCAL_ONLY, (),
            ("common.deciders.lethal:LethalMixin._best_affordable_damage@241",)),
        # Harvest: the integer prize oracles are direct shared edges; heuristic bonuses are not.
        "common.strategy.combat_math.harvest:HarvestMixin.snipe_ko_prizes": (
            "owner", coverage.SHARED_EXACT, ("terminal:attack_ev",),
            ("common.deciders.tactical:TacticalMixin._snipe_ko_prizes@150",
             "common.state_model:StateModel._attack_profile@1379")),
        "common.strategy.combat_math.harvest:HarvestMixin.spread_ko_prizes": (
            "owner", coverage.SHARED_EXACT, ("terminal:attack_ev",),
            ("common.deciders.tactical:TacticalMixin._spread_ko_prizes@156",
             "common.state_model:StateModel._attack_profile@1380")),
        "common.strategy.combat_math.harvest:HarvestMixin.bench_snipe_bonus": (
            "owner", coverage.LOSSY_REEXPRESSION, ("terminal:attack_ev",),
            ("common.deciders.tactical:TacticalMixin._bench_snipe_bonus@195",
             "common.strategy.combat_math.reach:ReachMixin.best_affordable_ko_value@182")),
        # Clock/Energy values reach registered families but change units/horizon, hence LOSSY.
        "common.strategy.combat_math.clocks:ClockMixin.incoming": (
            "owner", coverage.LOSSY_REEXPRESSION, ("state:survival",),
            ("common.state_model:TheirSide.incoming@1004",
             "common.strategy.combat_math.clocks:ClockMixin.doomed_incoming@31",
             "common.strategy.combat_math.clocks:ClockMixin.reachable_incoming@38",
             "common.strategy.combat_math.clocks:ClockMixin.survival_clock@223")),
        "common.strategy.combat_math.clocks:ClockMixin.turns_to_ko": (
            "owner", coverage.LOCAL_ONLY, (),
            ("common.deciders.snipe:SnipeMixin._snipe_relevance_terms@216",
             "common.deciders.snipe:SnipeMixin._snipe_relevance_terms@219",
             "common.strategy.objectives:ObjectivesMixin._my_turns_to_ko@226")),
        "common.strategy.combat_math.clocks:ClockMixin.turns_to_afford": (
            "owner", coverage.LOSSY_REEXPRESSION, ("state:readiness",),
            ("common.state_model:MySide.turns_to_afford@866",
             "common.state_model:TheirSide.turns_to_afford@1035")),
        "common.strategy.combat_math.energy:EnergyMixin.reachable_attach_p": (
            "owner", coverage.LOSSY_REEXPRESSION, ("state:readiness",),
            ("common.deciders.evolve:EvolveMixin._evolve_income_delta@107",
             "common.strategy.combat_math.reach:ReachMixin.readiness_p@107",
             "common.strategy.combat_math.reach:ReachMixin.readiness_p@112")),
        "common.strategy.combat_math.energy:EnergyMixin.matched_slots": (
            "owner", coverage.LOSSY_REEXPRESSION, ("state:readiness",),
            ("common.deciders.attach:AttachMixin._build_standing@122",
             "common.strategy.combat_math.clocks:ClockMixin.turns_to_afford@177")),
        # Previously hidden by the blanket unnamed-function fallback.
        "common.deciders.tactical:TacticalMixin._tactical": (
            "owner", coverage.LOSSY_REEXPRESSION, ("terminal:attack_ev",),
            ("common.pilot:Pilot._option_trace@541",)),
        "common.deciders.lethal:LethalMixin._grab_enabler_lethal_tactical": (
            "owner", coverage.LOSSY_REEXPRESSION, ("terminal:attack_ev",),
            ("common.pilot:Pilot._option_trace@564",)),
        "common.deciders.lethal:LethalMixin._grab_retreat_tool_lethal_tactical": (
            "owner", coverage.LOSSY_REEXPRESSION, ("terminal:attack_ev",),
            ("common.pilot:Pilot._option_trace@565",)),
        "common.deciders.evolve:EvolveMixin._evolve_income_delta": (
            "owner", coverage.LOSSY_REEXPRESSION, ("state:readiness",),
            ("common.deciders.evolve:EvolveMixin._evolve_decision@129",
             "common.deciders.evolve:EvolveMixin._evolve_decision@130")),
    }
    for key, wanted in expected.items():
        candidate = by_key[key]
        assert (candidate.disposition, candidate.classification, candidate.absolute_owners,
                candidate.runtime_callers) == wanted

    # A boolean damage/cost gate is not promoted merely because its identifiers look economic.
    gate = by_key["common.strategy.combat_math.reach:ReachMixin.can_ko_affordable"]
    assert gate.disposition == "excluded"
    assert not gate.classification
    for key in (
        "common.board_choice:deferred_target",
        "common.board_expectation:closed_form_transition",
        "common.board_expectation:_source",
        "common.board_expectation:_revealed",
        "common.board_expectation:_cost_indices",
        "common.board_expectation:_bench_room",
        "common.board_expectation:window_classes",
    ):
        assert by_key[key].disposition == "excluded"
        assert "call reach is not scalar value ownership" in by_key[key].reason

    for leaf in (
        "_grab_lethal_tactical", "_attach_retreat_tool_lethal_tactical",
        "_attach_lethal_tactical", "_retreat_to_lethal_tactical", "_boost_lethal_tactical",
    ):
        lethal = by_key[f"common.deciders.lethal:LethalMixin.{leaf}"]
        assert lethal.disposition == "owner"
        assert lethal.classification == coverage.LOSSY_REEXPRESSION
        assert lethal.absolute_owners == ("terminal:attack_ev",)
    promote_ko = by_key[
        "common.deciders.promote:PromoteRetreatMixin._promote_ko_tactical"]
    assert promote_ko.disposition == "consumer"
    assert not promote_ko.local_owners


def test_source_complete_term_tactical_and_expectation_equations_are_pinned(inventory):
    by_key = {candidate.key: candidate for candidate in inventory.equation_candidates}
    expected = {
        "common.deciders.hand:HandMixin._refresh_swing": (
            ("state:hand", "state:threat"),
            ("common.deciders.hand:HandMixin._grab_refresh_value@144",
             "common.deciders.hand:HandMixin._refresh_swing_tactical@81")),
        "common.strategy.refresh:net_change": (
            ("state:hand", "state:threat"),
            ("common.deciders.hand:HandMixin._refresh_swing@86",)),
        "common.evolve_value:EvolveBody.deploy": (
            ("state:development", "state:readiness", "state:survival"),
            ("common.evolve_value:evolve_value@91",)),
        "common.promote_retreat_value:PromoteBody.fatal": (
            ("state:prize_race", "terminal:attack_ev"),
            ("common.promote_retreat_value:promote_value@156",)),
        "common.needs:set_keep_v2": (
            ("state:hand",),
            ("common.deciders.hand:HandMixin._refresh_shed_keepcost@163",
             "common.needs:Resolution.set_keep@330", "common.needs:removal_score@376")),
        "common.deciders.tactical:TacticalMixin._copied_attack_tactical": (
            ("terminal:attack_ev",),
            ("common.deciders.tactical:TacticalMixin._copy_top_tactical@112",)),
        "common.strategy.objectives:ObjectivesMixin._race_attack_tactical": (
            ("terminal:attack_ev",),
            ("common.deciders.tactical:TacticalMixin._tactical@64",)),
        "common.strategy.objectives:prize_paths": (
            ("state:prize_race", "terminal:attack_ev"),
            ("common.strategy.objectives:ObjectivesMixin._bench_path_delta@478",
             "common.strategy.objectives:ObjectivesMixin._path_signals@357",
             "common.strategy.objectives:ObjectivesMixin._path_signals@360",
             "common.strategy.objectives:_sticky_path_from@174")),
        "common.strategy.doctrines.doctrine_gust:GustMixin._gust_tactical": (
            ("terminal:attack_ev",), ("common.pilot:Pilot._option_trace@553",)),
    }
    for key, (owners, callers) in expected.items():
        candidate = by_key[key]
        assert (candidate.disposition, candidate.classification) == (
            "owner", coverage.LOSSY_REEXPRESSION)
        assert candidate.absolute_owners == owners
        assert candidate.runtime_callers == callers

    all_state = tuple(sorted(f"state:{name}" for name in state_value.FAMILIES))
    for method, callers in {
        "best": ("common.apply_option:Expectation.ordering@405",
                 "common.composer:_one_ply@845", "common.composer:_one_ply@879"),
        "expected": ("common.apply_option:Expectation.ordering@405",
                     "common.composer:_one_ply@846", "common.composer:_one_ply@880"),
    }.items():
        candidate = by_key[f"common.apply_option:Expectation.{method}"]
        assert candidate.absolute_owners == all_state
        assert candidate.runtime_callers == callers
    ordering = by_key["common.apply_option:Expectation.ordering"]
    assert ordering.disposition == "consumer"
    assert ordering.absolute_owners == all_state
    assert ordering.runtime_callers == (
        "common.composer:_one_ply@844", "common.composer:_one_ply@881")

    mobility = by_key["common.retreat_cost:attached_retreat_delta"]
    assert (mobility.disposition, mobility.classification, mobility.absolute_owners) == (
        "owner", coverage.LOCAL_ONLY, ())
    assert "ADR-0135" in mobility.reason
    mobility_adapter = by_key[
        "common.deciders.promote:PromoteRetreatMixin._attached_retreat_delta"]
    assert (mobility_adapter.disposition, mobility_adapter.classification,
            mobility_adapter.absolute_owners) == ("consumer", coverage.LOCAL_ONLY, ())

    exact_owners = {
        "common.card_worth:role_value": (
            "state:development", "state:hand", "state:readiness"),
        "common.strategy.objectives:plan_confidence": (
            "state:prize_race", "state:survival"),
        "common.strategy.combat_math.clocks:ClockMixin._reach_form_damage": (
            "state:survival",),
        # These two are generic formulas: the assertions pin nearest reviewed-boundary traversal.
        "common.currency:prize_to_damage": ("state:survival",),
        "common.needs:turns_to_ready": ("state:readiness",),
    }
    for key, owners in exact_owners.items():
        assert by_key[key].absolute_owners == owners
        assert by_key[key].classification == coverage.LOSSY_REEXPRESSION

    exact_exclusions = {
        "common.apply_option:Expectation.total_probability",
        "common.board_delta:stadium_hp_delta",
        "common.deck_tracker:OwnCardModel._prizes_after_logged_takes",
        "common.opponent_resources:OpponentResourceModel.hand_size_delta",
        "common.scouting.forward_index:_ForwardIndex.max_forward_damage",
    }
    assert all(by_key[key].disposition == "excluded" for key in exact_exclusions)


def test_corpus_exposure_loader_fails_closed(monkeypatch):
    from train.blunder import store

    def fail(_root):
        raise OSError("missing corpus")

    monkeypatch.setattr(store, "load_corrections", fail)
    with pytest.raises(coverage.CoverageError, match="could not load corpus exposure"):
        coverage._load_corpus_corrections()


def test_source_index_resolves_nested_callers_without_bare_name_conflation():
    _definitions, calls, _providers = coverage._source_index()
    assert calls["common.board_expectation:_draw_window_expectation.delivered"] == (
        "common.board_expectation:_draw_window_expectation@448",
        "common.board_expectation:_draw_window_expectation@456",
    )
    assert calls["common.strategy.combat_math.budget:_pay_best_p.assign"] == (
        "common.strategy.combat_math.budget:_pay_best_p.assign@151",
        "common.strategy.combat_math.budget:_pay_best_p@158",
    )
    assert calls["common.strategy.combat_math.budget:_can_pay.assign"] == (
        "common.strategy.combat_math.budget:_can_pay.assign@189",
        "common.strategy.combat_math.budget:_can_pay@193",
    )
    assert calls["common.deciders.hand:HandMixin._grab_refresh_value"] == (
        "common.pilot:Pilot._option_trace@545",
    )
    assert calls["common.deciders.lines:LineMixin._wincon_prize_value"] == (
        "common.deciders.board_build:BoardMixin._board@138",
    )
    assert calls["common.deciders.lines:LineMixin._bench_wincon_prize_value"] == (
        "common.deciders.board_build:BoardMixin._board@169",
    )
    assert calls["common.deciders.promote:PromoteRetreatMixin._retreat_option_value"] == (
        "common.deciders.attach:AttachMixin._tool_attach_value@363",
        "common.deciders.attach:AttachMixin._tool_attach_value@364",
    )


def test_composer_search_surfaces_join_derived_search_loss_without_invention(inventory):
    search = records(inventory, "composer-search-consumer")
    assert len(search) == len(coverage.COMPOSER_SEARCH_CONSUMERS) == 14
    assert all("static search surface" in " ".join(record.evidence) for record in search)
    overlays = [record for record in inventory.records if record.search_overlay]
    assert [(record.mechanic_key, record.search_overlay) for record in overlays] == [
        ("search-consumer:structural-ordering", coverage.SEARCH_LOSS)]
    assert "sensitivity_summary_sha256=" in " ".join(overlays[0].evidence)
    assert "qualifying_search_losses=1" in " ".join(overlays[0].evidence)
    proof_text = next(item for item in overlays[0].evidence
                      if item.startswith("sensitivity named proof mega_starmie_wally_attach="))
    proof = json.loads(proof_text.split("=", 1)[1])
    assert proof["root_one_ply"]["wally"]["rank"] == 2
    assert proof["root_one_ply"]["attach_mega_starmie"]["rank"] == 4
    assert proof["orders"]["wally_then_attach"]["after_total_prizes"] == pytest.approx(
        1.342164743076)
    assert proof["orders"]["attach_then_wally"]["after_total_prizes"] == pytest.approx(
        1.330721383701)
    assert not [owner for record in search for owner in record.absolute_owners
                if owner == "state:composed-score"]
    for record in search:
        if record.classification == coverage.DELIBERATE_ZERO:
            assert record.source_symbol_or_site.split(" ", 1)[0] in coverage.SEARCH_ZERO_RULINGS
            assert "ADR-" in record.deliberate_ruling or "Issue" in record.deliberate_ruling

    stop = one(inventory, "search-consumer:stop-here-terminal-zero")
    assert stop.classification == coverage.DELIBERATE_ZERO
    assert "ADR-0129" in stop.deliberate_ruling
    assert not stop.absolute_owners


def test_search_loss_is_an_evidence_gated_overlay_not_a_replacement_class(inventory):
    energy = one(inventory, "state-dimension:attached_energy")
    proved = coverage.with_search_loss(
        energy,
        "controlled probe mega-starmie: beam_loss_frequency=0.25",
    )
    assert proved.classification == coverage.LOSSY_REEXPRESSION
    assert proved.search_overlay == coverage.SEARCH_LOSS
    assert coverage._measured_factor(proved, "beam_loss_frequency") == 0.25
    with pytest.raises(ValueError, match="probe evidence"):
        coverage.with_search_loss(energy, "manual assertion")


def test_ranked_findings_are_unique_aggregate_mechanics_with_measured_factors(inventory):
    findings = coverage._ranked_findings(inventory)
    keys = [row[3] for row in findings]
    assert len(keys) == len(set(keys))
    assert all(len(row) == 4 for row in findings)
    assert not [key for key in keys if key.startswith(("card-site:", "terminal-attack:",
                                                        "passive-ability:"))]

    energy = next(row for row in findings if row[3] == "state-dimension:attached_energy")
    energy_record = one(inventory, "state-dimension:attached_energy")
    measured_gap = coverage._measured_factor(energy_record, "local_leaf_disagreement")
    assert measured_gap is not None and measured_gap > 0
    assert energy == (
        (1, 29, 5, 380, measured_gap, "unmeasured", 2),
        coverage.LOSSY_REEXPRESSION,
        "#495",
        "state-dimension:attached_energy",
    )
    assert any("unmeasured" in row[0] for row in findings)

    wincon_key = "equation:common-deciders-lines-linemixin-wincon-prize-value"
    wincon = one(inventory, wincon_key)
    assert wincon.exposure == coverage.Exposure(
        cards=3, mechanic_sites=3, decks=3, deck_copies=9,
        meta_builds=20, meta_copies=1.295057, corpus_frames=306)
    wincon_rank = next(row for row in findings if row[3] == wincon_key)
    assert wincon_rank[0][:4] == (1, 3, 3, 306)

    ko_key = "equation:common-strategy-combat-math-reach-reachmixin-best-affordable-ko-value"
    ko = one(inventory, ko_key)
    assert ko.exposure.mechanic_sites == dict(inventory.populations)["terminal_attacks"] == 1556
    assert "terminal-attack=1556" in " ".join(ko.evidence)

    boost_key = "equation:common-deciders-board-build-boardmixin-typed-boost-total"
    boost = one(inventory, boost_key)
    assert boost.exposure.cards == 5
    assert boost.exposure.mechanic_sites == 9  # damageBoost / Type / VsEx = 5 / 1 / 3
    assert "provider=9" in " ".join(boost.evidence)

    for impact_key in (
        "equation:common-deciders-deploy-deploymixin-deploy-exposure-prizes",
        "equation:common-needs-line-prize-advance",
        "equation:common-apply-option-expectation-best",
        "equation:common-apply-option-expectation-expected",
        "equation:common-apply-option-expectation-ordering",
    ):
        impact = next(row for row in findings if row[3] == impact_key)
        assert impact[0][0] == 1
        assert coverage._measured_factor(one(inventory, impact_key),
                                         "terminal_win_prize_impact") == 1.0
    for impact_key in (
        "equation:common-state-value-prize-race",
        "equation:common-state-value-state-value",
    ):
        assert coverage._measured_factor(one(inventory, impact_key),
                                         "terminal_win_prize_impact") == 1.0
    impact_wrapper_key = "equation:common-deciders-promote-promoteretreatmixin-retreat-option-value"
    no_impact = next(row for row in findings if row[3] == impact_wrapper_key)
    assert no_impact[0][0] == 1

    damage_rank = next(row for row in findings
                       if row[3] == "provider-stat:attackstat:damage")
    assert damage_rank[0][1:4] == (1181, "unmeasured", "unmeasured")

    unmeasured_key = "equation:common-board-choice-rank-retreat"
    unmeasured = next(row for row in findings if row[3] == unmeasured_key)
    assert unmeasured[0][1:4] == ("unmeasured", "unmeasured", "unmeasured")


def test_inventory_is_deterministic_and_valid(inventory):
    again = coverage.build_inventory()
    assert again == inventory
    assert coverage.validate_inventory(inventory) == ()
    encoded = json.dumps(inventory.as_dict(), ensure_ascii=False, sort_keys=True)
    assert json.loads(encoded)["schema_version"] == coverage.SCHEMA_VERSION
    identities = [(record.mechanic_key, record.source_kind, record.source_symbol_or_site)
                  for record in inventory.records]
    assert len(identities) == len(set(identities))
    assert inventory.source_sha == coverage.AUDIT_BASE_SHA == (
        "848c2dce77737c77e0e2e78cd504252efbc58417")


def test_sensitivity_summary_join_fails_closed_on_malformed_schema(inventory, monkeypatch):
    from train import composer_sensitivity

    monkeypatch.setattr(composer_sensitivity, "diagnostic_summary", lambda **_kwargs: {})
    with pytest.raises(coverage.CoverageError, match="incomplete schema"):
        coverage._load_sensitivity_summary(inventory)


def test_sensitivity_named_proofs_are_required_and_joined(inventory, monkeypatch):
    from train import composer_sensitivity

    summary = composer_sensitivity.diagnostic_summary(inventory=inventory)
    malformed = dict(summary, proofs={})
    monkeypatch.setattr(composer_sensitivity, "diagnostic_summary", lambda **_kwargs: malformed)
    with pytest.raises(coverage.CoverageError, match="required named proofs"):
        coverage._load_sensitivity_summary(inventory)

    energy = one(inventory, "state-dimension:attached_energy")
    identity_text = next(item for item in energy.evidence
                         if item.startswith(
                             "sensitivity named proof identity_independent_attach="))
    identity = json.loads(identity_text.split("=", 1)[1])
    assert identity["identity_independent"] is True
    assert identity["original"]["local_delta_damage"] == pytest.approx(23.333333333333)
    assert identity["clone"]["leaf_delta_prizes"] == pytest.approx(0.003922119141)


def test_strategy_filter_tracks_every_executed_strategy_module():
    filters = (ROOT / ".github" / "filters.yml").read_text(encoding="utf-8")
    ci = (ROOT / "docs" / "ci.md").read_text(encoding="utf-8")
    assert "- 'src/agents/*/strategy.py'" in filters
    assert "`src/agents/*/strategy.py`" in ci
    assert "executable `STRATEGY.roles` maps" in ci


def test_report_has_exact_numbered_order_and_lf_safe_regeneration(inventory, tmp_path):
    report = tmp_path / "coverage.md"
    report.write_bytes(b"authored before\r\n\r\n<!-- BEGIN GENERATED: tools/composer_value_coverage.py -->\r\nold\r\n<!-- END GENERATED -->\r\n\r\nauthored after\r\n")
    coverage.write_report(report, inventory)
    raw = report.read_bytes()
    assert b"\r" not in raw
    text = raw.decode("utf-8")
    assert text.startswith("authored before") and text.rstrip().endswith("authored after")
    headings = [line for line in text.splitlines() if line.startswith("## ")]
    assert [heading.split(".", 1)[0] for heading in headings] == [f"## {n}" for n in range(1, 11)]
    assert coverage.check_report(report, inventory)
    assert "mega_starmie_wally_attach" in text
    assert "identity_independent_attach" in text
    assert "1.342164743076" in text and "1.330721383701" in text
    digest = next(item for item in one(
        inventory, "search-consumer:structural-ordering").evidence
                  if item.startswith("sensitivity_summary_sha256="))
    report.write_text(text.replace(digest, "sensitivity_summary_sha256=" + "0" * 64, 1),
                      encoding="utf-8", newline="\n")
    assert not coverage.check_report(report, inventory)
    coverage.write_report(report, inventory)
    raw = report.read_bytes()

    report.write_bytes(raw.replace(b"All shipped apply sites", b"STALE shipped apply sites", 1))
    assert not coverage.check_report(report, inventory)

    coverage.write_report(report, inventory)
    raw = report.read_bytes()
    report.write_bytes(raw.replace(b"All shipped apply sites", b"All shipped apply sites ", 1))
    assert not coverage.check_report(report, inventory)

    report.unlink()
    assert not coverage.check_report(report, inventory)


def test_cli_out_check_and_json_contract(inventory, tmp_path, monkeypatch):
    monkeypatch.setattr(coverage, "build_inventory", lambda: inventory)
    report = tmp_path / "coverage.md"
    data = tmp_path / "coverage.json"
    assert coverage.main(["--out", str(report)]) == 0
    assert coverage.main(["--check", str(report)]) == 0
    assert coverage.main(["--json", str(data)]) == 0
    payload = json.loads(data.read_text(encoding="utf-8"))
    assert payload["schema_version"] == coverage.SCHEMA_VERSION
    assert payload["source_sha"] == inventory.source_sha
    assert len(payload["records"]) == len(inventory.records)


def test_committed_report_exists_and_is_fresh(inventory):
    assert coverage.DEFAULT_OUT.exists(), "durable report was deleted"
    assert coverage.check_report(coverage.DEFAULT_OUT, inventory), (
        "docs/plans/composer-valuation-coverage.md is stale; rerun the coverage tool")
