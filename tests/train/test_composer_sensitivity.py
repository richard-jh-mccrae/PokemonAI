"""Issue #493's controlled transition/value/search probes.

These tests pin the instrument and its positive controls, not a new runtime policy.  Synthetic card
ids are deliberately irrelevant; the identity metamorphic case makes that explicit.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from common import apply_option as ao
from common import composer as cp
from train import composer_sensitivity as lab

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "tests" / "fixtures" / "composer_sensitivity" / "ms_wally_attach_f69.json"


@pytest.fixture(scope="module")
def report():
    """One sweep shared by the assertions: f69 runs the real shipped Pilot and Composer."""
    return lab.build_report()


@pytest.fixture(scope="module")
def cases(report):
    return {row["case"]: row for row in report["cases"]}


@pytest.mark.req("REQ-COMPOSERSENS-0001")
def test_case_population_covers_every_locked_control():
    assert set(lab.case_names()) == {
        "energy-typed-match", "energy-typed-mismatch", "energy-partial-cost",
        "energy-multi-attack", "energy-removal", "evolution-retains-attachments",
        "evolution-bounces-attachments", "healing-crosses-threshold",
        "healing-not-across-threshold", "mobility-retreat-tool",
        "mobility-retreat-enables-modeled-retreat",
        "hand-spend-retires-demand", "hand-spend-unrepresented-demand",
        "information-ordering", "equivalent-identities", "refused-effect",
        "mega-starmie-wally-attach",
    }


@pytest.mark.req("REQ-COMPOSERSENS-0001")
def test_report_and_case_schema_are_stable(report):
    assert set(report) == {"schema_version", "source_sha", "seed", "command", "cases",
                           "diagnostic_summary"}
    assert report["schema_version"] == lab.SCHEMA_VERSION
    assert report["seed"] == 493
    assert len(report["source_sha"]) == 40
    assert report["command"] == (
        "python tools/train/composer_sensitivity.py --all --out reports/composer-sensitivity.json")

    case_keys = {"case", "key", "source", "seed", "command", "before", "actions", "after",
                 "deltas", "local", "search", "unknown", "positive_control"}
    action_keys = {"ordinal", "index", "option", "fate", "changed_dimensions",
                   "declared_reads", "declared_writes", "footprint_complete", "detail"}
    for row in report["cases"]:
        assert set(row) == case_keys
        assert set(row["source"]) == {"kind", "fixture", "provenance"}
        assert set(row["before"]) == set(row["after"]) == {"total", "workings", "legs"}
        assert set(row["before"]["workings"]) == set(row["after"]["workings"]) == set(lab.FAMILIES)
        assert set(row["deltas"]) == {"total", "families", "legs"}
        assert set(row["deltas"]["families"]) == set(lab.FAMILIES)
        assert set(row["local"]) == {"owner", "unit", "before", "after", "delta", "working"}
        assert set(row["search"]) == {"status", "k", "epsilon", "depth", "one_ply",
                                      "candidate_presence", "chosen", "gaps"}
        assert set(row["unknown"]) == {"dimensions", "unread_dimensions", "reasons"}
        assert row["actions"] and all(set(action) == action_keys for action in row["actions"])
        assert isinstance(row["positive_control"]["passed"], bool)
    summary = report["diagnostic_summary"]
    assert set(summary) == {"schema_version", "source_sha", "inventory", "counts", "findings",
                            "proofs", "beam_loss_frequency"}
    assert summary["schema_version"] == lab.SUMMARY_SCHEMA_VERSION
    assert summary["counts"]["cases"] == len(report["cases"])


@pytest.mark.req("REQ-COMPOSERSENS-0002")
def test_every_negative_result_has_a_live_positive_control(cases):
    failed = {name: row["positive_control"] for name, row in cases.items()
              if not row["positive_control"]["passed"]}
    assert failed == {}
    refused = cases["refused-effect"]
    assert refused["actions"][0]["fate"] == ao.REFUSED
    assert refused["actions"][0]["declared_writes"]
    assert refused["actions"][0]["detail"]["scope"] == "nondeterminism"
    assert refused["actions"][0]["detail"]["clauses_cover"] is False
    assert refused["local"]["working"]["clauses_cover"] is False
    assert refused["source"]["provenance"]["card_id"] == 1153
    assert refused["unknown"]["dimensions"]
    placeholder = refused["search"]["candidate_presence"][0]
    assert placeholder["generated_as_prefix"] is True
    assert placeholder["faithful_generated_as_prefix"] is False
    assert placeholder["survived_terminal_dominance"] is False
    assert placeholder["refused_gap_placeholder_only"] is True
    assert placeholder["coverage_gaps"]
    assert placeholder["matching_candidates"][0]["retained_for_diagnostics"] is True
    assert placeholder["matching_candidates"][0]["survived_terminal_dominance"] is False
    assert cases["energy-typed-match"]["actions"][0]["fate"] == ao.MODELLED
    controls = {
        "energy-typed-match": "energy-partial-cost",
        "energy-typed-mismatch": "energy-typed-match",
        "energy-removal": "energy-partial-cost",
        "evolution-bounces-attachments": "evolution-retains-attachments",
        "healing-not-across-threshold": "healing-crosses-threshold",
        "mobility-retreat-tool": "mobility-retreat-enables-modeled-retreat",
        "hand-spend-retires-demand": "hand-spend-unrepresented-demand",
        "refused-effect": "energy-typed-match",
    }
    for negative, positive in controls.items():
        assert cases[negative]["positive_control"]["case"] == positive
        assert cases[positive]["positive_control"]["passed"]


@pytest.mark.req("REQ-COMPOSERSENS-0003")
def test_energy_controls_separate_type_progress_unlock_and_inverse(cases):
    match = cases["energy-typed-match"]
    mismatch = cases["energy-typed-mismatch"]
    partial = cases["energy-partial-cost"]
    multi = cases["energy-multi-attack"]
    removal = cases["energy-removal"]

    assert match["local"]["working"]["attack_shape"] == "single"
    assert match["local"]["delta"] == 120.0
    assert match["deltas"]["total"] == 0.0
    assert match["local"]["working"]["single_attack_fully_unlocked"] is True
    assert match["positive_control"]["case"] == "energy-partial-cost"
    assert match["positive_control"]["positive_total_delta"] > 0
    assert mismatch["local"]["working"]["attack_shape"] == "single"
    assert mismatch["local"]["delta"] == mismatch["deltas"]["total"] == 0.0
    assert mismatch["positive_control"]["positive_local_delta"] == 120.0
    assert partial["local"]["working"]["attack_shape"] == "partial"
    assert partial["local"]["delta"] == pytest.approx(23.333333333333)
    assert partial["local"]["working"]["partial_progress_without_unlock"] is True
    assert partial["deltas"]["families"]["readiness"] > 0
    catalog = {entry["attack_id"]: entry for entry in multi["local"]["working"]["attack_catalog"]}
    assert catalog[multi["local"]["working"]["cheaper_attack_id"]]["damage"] == 120
    assert catalog[multi["local"]["working"]["larger_attack_id"]]["damage"] == 210
    assert (multi["local"]["working"]["leaf_payoff_attack_before"]
            == multi["local"]["working"]["larger_attack_id"])
    assert (multi["local"]["working"]["leaf_payoff_attack_after"]
            == multi["local"]["working"]["larger_attack_id"])
    assert multi["local"]["working"]["cheaper_attack_fully_unlocked"]
    assert multi["local"]["working"]["best_reachable_damage_before"] == 0.0
    assert multi["local"]["working"]["best_reachable_damage_after"] == 120.0
    assert multi["local"]["working"]["larger_attack_still_selected_by_readiness"]
    assert multi["local"]["working"]["classification"] == "LOSSY-REEXPRESSION"
    assert multi["local"]["working"]["delta_prizes_equivalent"] > multi["deltas"]["total"] > 0
    assert "allowance_energy_attached" not in match["unknown"]["unread_dimensions"]
    assert removal["deltas"]["total"] < 0
    assert removal["deltas"]["total"] == -removal["positive_control"]["forward_total_delta"]
    assert removal["local"]["delta"] == -partial["local"]["delta"]


@pytest.mark.req("REQ-COMPOSERSENS-0004")
def test_evolution_heal_mobility_and_hand_controls(cases):
    retain = cases["evolution-retains-attachments"]
    bounce = cases["evolution-bounces-attachments"]
    assert retain["local"]["owner"] == "common.evolve_value.evolve_value"
    assert retain["local"]["working"]["substitution_owner"] == (
        "common.deciders.evolve.EvolveMixin._evolve_substitution")
    assert retain["local"]["before"] == -93.75
    assert retain["local"]["after"] == 0.0
    assert retain["local"]["delta"] == 93.75
    assert retain["local"]["working"]["isolated_from_same_evolution"] is True
    assert retain["local"]["working"]["retained_energy_serials"] == [100]
    equation = retain["local"]["working"]["equation"]
    assert equation["retained_result_raw"]["energyCards"][0]["serial"] == 100
    assert equation["bounced_result_raw"]["energyCards"] == []
    assert equation["retained_result"]["arm"] == 2
    assert equation["bounced_result"]["arm"] == 3
    assert equation["retained_value"]["total"] == 0.0
    assert equation["bounced_value"]["total"] == -93.75
    assert retain["local"]["working"]["retained_vs_bounced_local_delta"] == 93.75
    assert retain["local"]["working"]["retained_vs_bounced_leaf_delta"] == pytest.approx(
        0.003922119141)
    assert retain["local"]["working"]["retained_vs_bounced_leaf_delta"] != (
        retain["local"]["working"]["retained_vs_bounced_local_delta"])
    assert bounce["local"]["owner"] == "common.evolve_value.evolve_value"
    assert bounce["local"]["before"] == 0.0
    assert bounce["local"]["after"] == -93.75
    assert bounce["local"]["delta"] == -93.75
    assert bounce["local"]["working"]["isolated_from_same_evolution"] is True
    assert bounce["local"]["working"]["retained_energy_serials"] == [100]
    assert bounce["local"]["working"]["bounced_to_hand_serial"] == 100
    assert (bounce["local"]["working"]["retained_sequence_total"]
            > bounce["local"]["working"]["bounced_sequence_total"])
    assert "attached_energy" in bounce["actions"][0]["changed_dimensions"]
    assert not ({"damage_counters", "new_in_play"}
                & set(bounce["actions"][0]["changed_dimensions"]))

    cross = cases["healing-crosses-threshold"]
    no_cross = cases["healing-not-across-threshold"]
    assert cross["local"]["owner"] == "common.deciders.heal.HealMixin._heal_survival_gain"
    assert cross["local"]["working"]["equation_invoked"] == cross["local"]["owner"]
    assert cross["local"]["working"]["restored_hp"] == 40
    assert cross["local"]["working"]["effect_card_id"] == 1222
    assert cross["local"]["working"]["effect_clauses"] == [
        {"amount": 40, "each_of": True, "kind": "heal", "target": "any_pokemon"}]
    assert cross["local"]["working"]["doom_averted"] is True
    assert cross["local"]["working"]["doom_prize_damage"] == 100.0
    assert cross["local"]["delta"] == 140.0
    assert cross["deltas"]["families"]["survival"] > 0
    assert no_cross["local"]["delta"] == 40.0
    assert no_cross["local"]["working"]["doom_averted"] is False
    assert no_cross["local"]["working"]["doom_prize_damage"] == 0.0
    assert no_cross["deltas"]["total"] == 0.0
    assert no_cross["local"]["working"]["classification"] == "LOSSY-REEXPRESSION"

    mobility = cases["mobility-retreat-tool"]
    assert mobility["local"]["working"]["benefit"] == 2
    assert mobility["local"]["working"]["classification"] == "LOCAL-ONLY"
    assert mobility["deltas"]["total"] == 0.0
    assert mobility["unknown"]["unread_dimensions"] == ["attached_tools"]
    assert any("ADR-0135" in reason for reason in mobility["unknown"]["reasons"])
    enabled = cases["mobility-retreat-enables-modeled-retreat"]
    assert enabled["local"]["working"]["affordable_before"] is False
    assert enabled["local"]["working"]["affordable_after"] is True
    assert enabled["local"]["working"]["retreat_allowance_spent"] is True
    assert enabled["local"]["working"]["promoted_active_serial"] == 2
    assert enabled["local"]["working"]["retreat_leaf_delta"] > 0
    assert enabled["positive_control"]["observed_retreat_leaf_delta"] > 0
    assert enabled["deltas"]["total"] > 0
    assert mobility["positive_control"]["positive_retreat_leaf_delta"] == (
        enabled["positive_control"]["observed_retreat_leaf_delta"])
    assert [action["fate"] for action in enabled["actions"]] == [ao.MODELLED, ao.MODELLED]

    represented = cases["hand-spend-retires-demand"]
    unrepresented = cases["hand-spend-unrepresented-demand"]
    before = represented["local"]["working"]["before_legs"]
    after = represented["local"]["working"]["after_legs"]
    assert before["assignment_coverage"] == before["slot_demand"] == 8.0
    assert after["assignment_coverage"] == after["slot_demand"] == 0.0
    assert represented["local"]["working"]["equation"] == (
        "assignment_coverage + re_access + hand_worth - slot_demand")
    assert represented["local"]["owner"] == "common.state_value.hand"
    assert represented["local"]["unit"] == "prizes"
    assert represented["local"]["working"]["conversion_and_cap_invoked"] is True
    assert represented["local"]["before"] == represented["local"]["after"] == 0.0
    assert represented["local"]["delta"] == 0.0
    assert represented["local"]["working"]["hand_family_delta"] == 0.0
    assert represented["positive_control"]["case"] == "hand-spend-unrepresented-demand"
    assert represented["positive_control"]["positive_signal_magnitude"] > 0
    assert represented["positive_control"]["positive_local_delta"] == pytest.approx(
        unrepresented["local"]["delta"])
    assert represented["positive_control"]["positive_hand_family_delta"] == pytest.approx(
        unrepresented["deltas"]["families"]["hand"])
    assert unrepresented["local"]["working"]["classification"] == "unrepresented-bench-demand"
    assert unrepresented["local"]["working"]["before_legs"]["hand_worth"] == 8.0
    assert unrepresented["local"]["working"]["raw_signed_worth_before"] == 8.0
    assert unrepresented["local"]["working"]["raw_signed_worth_after"] == 0.0
    assert unrepresented["local"]["before"] == pytest.approx(0.066666666667)
    assert unrepresented["local"]["after"] == 0.0
    assert unrepresented["local"]["delta"] == pytest.approx(-0.066666666667)
    assert unrepresented["local"]["delta"] == pytest.approx(
        unrepresented["deltas"]["families"]["hand"])
    assert unrepresented["local"]["working"]["hand_family_delta"] < 0


@pytest.mark.req("REQ-COMPOSERSENS-0005")
def test_information_case_names_structural_owner_not_a_value_gap(cases):
    row = cases["information-ordering"]
    working = row["local"]["working"]
    assert working["same_final_state"] is True
    assert working["reveal_predicate"] is True
    assert working["structural_ordering_owner"] == "composer.canonical_tier:TIER_INFORMATIVE"
    assert row["local"]["before"] == cp.TIER_INFORMATIVE
    assert row["local"]["after"] == cp.TIER_COMMITMENT
    assert row["deltas"]["total"] == 0.0
    assert [a["fate"] for a in row["actions"]] == [ao.MODELLED, ao.MODELLED]
    finding = working["finding"]
    assert finding == {
        "chosen_sequence": [1, 0],
        "classification": "structural-ordering-owner",
        "commitment_first_present": True,
        "informative_first_present": False,
        "issue": 496,
        "qualifying_search_loss": True,
        "search_overlay": "SEARCH-LOSS",
        "valuation_gap": 0.0,
    }
    presence = {tuple(entry["sequence"]): entry for entry in row["search"]["candidate_presence"]}
    assert presence[(0, 1)]["faithful_generated_as_prefix"] is False
    assert presence[(1, 0)]["faithful_generated_as_prefix"] is True

    action_keys = {"ordinal", "index", "option", "fate", "changed_dimensions",
                   "declared_reads", "declared_writes", "footprint_complete", "detail"}
    contract_keys = {"label", "indices", "before", "actions", "after", "deltas", "local"}
    for order in working["ordered_sequences"]:
        assert set(order) == contract_keys
        assert set(order["before"]) == set(order["after"]) == {"total", "workings", "legs"}
        assert set(order["deltas"]) == {"total", "families", "legs"}
        assert set(order["local"]) == {"owner", "unit", "before", "after", "delta", "working"}
        assert len(order["actions"]) == 2
        assert all(set(action) == action_keys for action in order["actions"])


@pytest.mark.req("REQ-COMPOSERSENS-0006")
def test_equivalent_identity_has_the_same_mechanic_delta(cases):
    identity = cases["equivalent-identities"]
    assert identity["positive_control"]["original_total_delta"] == identity["deltas"]["total"]
    assert identity["local"]["working"]["original_body_id"] != identity["local"]["working"]["clone_body_id"]
    assert (identity["local"]["working"]["original_leaf_total_delta"]
            == identity["local"]["working"]["clone_leaf_total_delta"])
    assert (identity["local"]["working"]["original_local_damage_delta"]
            == identity["local"]["working"]["clone_local_damage_delta"])
    assert identity["local"]["working"]["mechanic_signature"] == {
        "attached_energy_type": 3, "attack_energy_types": [[3], [3, 0, 0]]}
    assert identity["local"]["before"] == identity["local"]["after"]
    assert identity["positive_control"]["original_local_delta"] == identity["local"]["before"]
    assert identity["positive_control"]["clone_local_delta"] == identity["local"]["after"]


@pytest.mark.req("REQ-COMPOSERSENS-0007")
def test_pr490_fixture_is_self_contained_and_both_orders_survive_as_evidence(cases):
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert fixture["provenance"]["pull_request"] == 490
    assert fixture["provenance"]["head_sha"] == "c74c45a8624aa8e6ba4e725cdfb3cb0da3b30a95"
    assert fixture["key"] == "91393371-69"
    assert fixture["action_indices"]["wally_then_attach"] == [1, 6]
    assert fixture["action_indices"]["attach_then_wally"] == [6, 1]
    assert len(fixture["obs"]["select"]["option"]) == 8

    row = cases["mega-starmie-wally-attach"]
    one_ply = {entry["index"]: entry for entry in row["search"]["one_ply"]}
    assert one_ply[1]["rank"] == 2 and one_ply[1]["admission_reason"] == "hard-top-k"
    assert one_ply[6]["rank"] == 4 and one_ply[6]["cutoff_margin"] == 0.0
    presence = {tuple(entry["sequence"]): entry for entry in row["search"]["candidate_presence"]}
    assert presence[(1, 6)]["generated_as_prefix"] is True
    assert presence[(6, 1)]["generated_as_prefix"] is False
    orders = row["local"]["working"]["ordered_sequences"]
    assert orders[0]["local"]["working"]["final_target_energy_serials"] == [63]
    assert orders[1]["local"]["working"]["final_target_energy_serials"] == []
    assert orders[0]["after"]["total"] > orders[1]["after"]["total"]
    assert orders[0]["local"]["delta"] == pytest.approx(23.333333333333)
    assert orders[1]["local"]["delta"] == 70.0
    assert all(len(order["actions"]) == 2 for order in orders)
    assert all(set(order["deltas"]) == {"total", "families", "legs"} for order in orders)
    isolated = row["local"]["working"]["isolated_attach_after_wally"]
    assert isolated["target_energy_serials_before"] == []
    assert isolated["target_energy_serials_after"] == [63]
    assert isolated["matches_full_forward_state"] is True
    assert isolated["leaf_delta"] == pytest.approx(0.002443359375)
    assert isolated["local_build_delta"] == pytest.approx(23.333333333333)
    assert row["deltas"]["total"] == pytest.approx(0.002443359375)
    assert row["local"]["delta"] == pytest.approx(23.333333333333)
    assert row["local"]["working"]["root_target_energy_serials"] == [71]
    assert row["local"]["working"]["root_attach_trace"]["build"] == 70.0


@pytest.mark.req("REQ-COMPOSERSENS-0008")
def test_single_case_cli_writes_deterministic_json(tmp_path):
    first, second = tmp_path / "first.json", tmp_path / "second.json"
    assert lab.main(["--case", "energy-typed-mismatch", "--out", str(first)]) == 0
    assert lab.main(["--case", "energy-typed-mismatch", "--out", str(second)]) == 0
    assert first.read_bytes() == second.read_bytes()
    payload = json.loads(first.read_text(encoding="utf-8"))
    assert [row["case"] for row in payload["cases"]] == ["energy-typed-mismatch"]


def test_complete_sweep_is_deterministic(report, tmp_path):
    rebuilt = lab.build_report()
    assert rebuilt == report
    first, second = tmp_path / "all-first.json", tmp_path / "all-second.json"
    lab._write_json(first, report)
    lab._write_json(second, rebuilt)
    assert first.read_bytes() == second.read_bytes()


def test_diagnostic_summary_is_derived_fail_closed_and_frequency_honest(report):
    summary = report["diagnostic_summary"]
    counts = summary["counts"]
    assert counts["controls_failed"] == 0
    assert counts["qualifying_search_losses"] == 1
    assert counts["coverage_gap_candidate_sequences"] == 1
    assert counts["refused_gap_placeholders"] == 1
    assert counts["ordered_sequences"] == 4
    assert summary["beam_loss_frequency"]["proven"] is False
    search = summary["findings"]["search_loss"]
    assert [(row["case"], row["issue"]) for row in search] == [("information-ordering", 496)]
    disagreements = {row["case"]: row
                     for row in summary["findings"]["local_leaf_disagreement"]}
    f69 = disagreements["mega-starmie-wally-attach"]
    assert f69["local_delta"] == pytest.approx(23.333333333333)
    assert f69["leaf_total_delta_prizes"] == pytest.approx(0.002443359375)
    assert "attached_energy" in f69["declared_writes"]
    joins = {entry["mechanic_key"]: entry for entry in f69["static_join"]}
    assert "state-dimension:attached_energy" in joins
    proofs = summary["proofs"]
    assert set(proofs) == {"mega_starmie_wally_attach", "identity_independent_attach"}
    mega = proofs["mega_starmie_wally_attach"]
    assert mega["case"] == "mega-starmie-wally-attach"
    assert mega["key"] == "91393371-69"
    assert mega["root_total_prizes"] == pytest.approx(1.017871774326)
    assert mega["root_one_ply"]["wally"] == {
        "index": 1, "rank": 2, "ranked": 7, "chosen_delta": 0.321849609375,
        "admitted": True, "in_beam": True, "admission_reason": "hard-top-k",
        "kth_delta": 0.00871875, "cutoff_margin": 0.313130859375,
        "margin_to_kth": 0.313130859375,
    }
    assert mega["root_one_ply"]["attach_mega_starmie"] == {
        "index": 6, "rank": 4, "ranked": 7, "chosen_delta": 0.00871875,
        "admitted": True, "in_beam": True, "admission_reason": "hard-top-k",
        "kth_delta": 0.00871875, "cutoff_margin": 0.0, "margin_to_kth": 0.0,
    }
    forward = mega["orders"]["wally_then_attach"]
    reverse = mega["orders"]["attach_then_wally"]
    assert forward["indices"] == [1, 6]
    assert forward["after_total_prizes"] == pytest.approx(1.342164743076)
    assert forward["total_delta_prizes"] == pytest.approx(0.32429296875)
    assert forward["target_water_serials"] == [63]
    assert forward["target_water_count"] == 1
    assert forward["faithful_generated_as_prefix"] is True
    assert reverse["indices"] == [6, 1]
    assert reverse["after_total_prizes"] == pytest.approx(1.330721383701)
    assert reverse["total_delta_prizes"] == pytest.approx(0.312849609375)
    assert reverse["target_water_serials"] == []
    assert reverse["target_water_count"] == 0
    assert reverse["faithful_generated_as_prefix"] is False
    isolated = mega["isolated_attach_after_wally"]
    assert isolated["local_delta_damage"] == pytest.approx(23.333333333333)
    assert isolated["leaf_delta_prizes"] == pytest.approx(0.002443359375)
    assert isolated["target_water_serials_before"] == []
    assert isolated["target_water_serials_after"] == [63]
    identity = proofs["identity_independent_attach"]
    assert identity["mechanic_signature"] == {
        "attached_energy_type": 3, "attack_energy_types": [[3], [3, 0, 0]]}
    assert identity["original"] == {
        "body_id": 990001, "local_delta_damage": 23.333333333333,
        "leaf_delta_prizes": 0.003922119141,
    }
    assert identity["clone"] == {
        "body_id": 990002, "local_delta_damage": 23.333333333333,
        "leaf_delta_prizes": 0.003922119141,
    }
    assert identity["local_delta_equal"] is True
    assert identity["leaf_delta_equal"] is True
    assert identity["identity_independent"] is True
    assert lab.diagnostic_summary(cases=report["cases"]) == summary
