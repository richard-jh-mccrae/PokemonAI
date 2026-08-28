from train.value_audit import _component_differences, build_value_audit
import json
from pathlib import Path
import subprocess
import sys


def _candidate(selection, value, activation, *, status="complete", path=("play",)):
    coefficient = 0.5
    return {
        "action": f"action-{selection[0]}",
        "selection": selection,
        "status": status,
        "decision_delta": value,
        "search_value": 10.0 + value,
        "features": {"option.draw": activation},
        "components": [{
            "feature": "option.draw", "activation": activation,
            "coefficient": coefficient,
            "contribution": activation * coefficient,
            "provenance": ["me.hand"],
        }],
        "successors": [{
            "probability": 1.0, "ended": False, "status": status,
            "position_key": f"p-{selection[0]}", "action_path": list(path),
        }],
        "gaps": [],
    }


def _row(*, ruled_status="complete"):
    return {
        "deck": "mega_starmie", "episode_id": 44, "key": "44-10", "id": "corr",
        "scope": "decision", "context": 0, "category": "sequencing", "graded": True,
        "chosen": [2], "recorded_chosen": [0], "correct": [1], "acceptable": [[1]],
        "rationale": "Fetch the attacker.", "gaps": [],
        "candidates": [
            _candidate([0], 1.0, 1.0, path=("play", "discard", "fetch")),
            _candidate([1], 1.5, 2.0, status=ruled_status,
                       path=("play", "discard", "fetch")),
            _candidate([2], 1.2, 1.4),
        ],
    }


def test_audit_sums_owner_split_components_before_comparison():
    ruled = {"components": [
        {"feature": "option.draw", "activation": 1.0, "coefficient": 0.5,
         "contribution": 0.5, "provenance": ["first"]},
        {"feature": "option.draw", "activation": 2.0, "coefficient": 0.5,
         "contribution": 1.0, "provenance": ["second"]},
    ]}
    committed = {"components": [
        {"feature": "option.draw", "activation": 1.0, "coefficient": 0.5,
         "contribution": 0.5, "provenance": ["base"]},
    ]}

    assert _component_differences(ruled, committed) == [{
        "feature": "option.draw", "activation_delta": 2.0,
        "coefficient": 0.5, "contribution_delta": 1.0,
        "provenance": ["base", "first", "second"],
    }]


def test_audit_finds_a_duplicate_card_through_its_equivalent_selection():
    row = _row()
    row["correct"] = [4]
    row["acceptable"] = [[4]]
    row["candidates"][1]["equivalent_selections"] = [[1], [4]]

    audit = build_value_audit([row])["audits"][0]

    assert audit["ruled"]["selection"] == [1]
    assert audit["gradeable"] is True


def test_value_audit_compares_the_ruled_and_original_committed_paths_at_the_locus():
    artifact = build_value_audit([_row()])
    audit = artifact["audits"][0]

    assert audit["locus"] == {"episode_id": 44, "frame": 10, "context": 0,
                               "scope": "decision"}
    assert audit["current_selection"] == [2]
    assert audit["committed"]["selection"] == [0]
    assert audit["ruled"]["selection"] == [1]
    assert audit["margin"]["compound"] == 0.5
    assert audit["margin"]["atomic"] == 0.5
    assert audit["contribution_differences"][0]["activation_delta"] == 1.0
    assert audit["calibration_proposal"]["auto_apply"] is False


def test_incomplete_candidate_is_excluded_from_grading():
    row = _row(ruled_status="estimated")
    row.update(graded=False, grading_exclusion="search_incomplete")
    audit = build_value_audit([row])["audits"][0]

    assert audit["gradeable"] is False
    assert audit["cause"] == "search_completeness"
    assert audit["margin"] == {"atomic": None, "compound": None}


def test_successor_coverage_gap_precedes_search_completeness():
    row = _row(ruled_status="estimated")
    row["candidates"][1]["successors"][0]["gaps"] = [
        "me.hand: incomplete card coverage 99"]

    audit = build_value_audit([row])["audits"][0]
    assert audit["cause"] == "coverage"
    assert audit["calibration_proposal"]["changes"] == []


def test_structural_causes_cannot_emit_coefficient_proposals():
    for cause_setup in ("transition", "activation_equation", "portfolio_constraint"):
        row = _row()
        row["candidates"][1] = _candidate([1], 0.0, 2.0)
        if cause_setup == "transition":
            row["candidates"][1]["gaps"] = ["unsupported transition"]
        elif cause_setup == "activation_equation":
            row["candidates"][1]["components"] = row["candidates"][0]["components"]
        else:
            row["candidates"][1]["components"][0]["provenance"] = [
                "feasible_option_portfolio"]
        audit = build_value_audit([row])["audits"][0]
        assert audit["cause"] == cause_setup
        assert audit["calibration_proposal"]["required"] is False
        assert audit["calibration_proposal"]["changes"] == []


def test_portfolio_provenance_classifies_shared_resource_failures():
    row = _row()
    row["candidates"][1] = _candidate([1], 0.0, 2.0)
    row["candidates"][1]["components"][0]["provenance"] = [
        "feasible_option_portfolio"]

    assert build_value_audit([row])["audits"][0]["cause"] == "portfolio_constraint"


def test_plain_hand_option_difference_remains_a_coefficient_seed_cause():
    row = _row()
    row["candidates"][1] = _candidate([1], 0.0, 2.0)

    assert build_value_audit([row])["audits"][0]["cause"] == "coefficient_seed"


def test_committed_acceptable_alternative_is_not_a_violation():
    row = _row()
    row["acceptable"].append([0])
    audit = build_value_audit([row])

    assert audit["audits"][0]["margin"]["atomic"] == 0.0
    assert audit["summary"]["violated_preferences"] == 0
    assert audit["audits"][0]["cause"] == "resolved"
    assert audit["audits"][0]["calibration_proposal"]["required"] is False


def test_value_audit_artifact_is_deterministic_and_self_identifying():
    first = build_value_audit([_row()])
    second = build_value_audit([_row()])

    assert first == second
    assert first["schema"] == "ledger.value-audit"
    assert first["data_identity"]


def test_conflicts_are_minimal_pairs_and_incomplete_rows_do_not_block_proposals():
    violated = _row()
    violated["candidates"][1] = _candidate([1], 0.0, 2.0)
    conflict = _row()
    conflict.update(id="other", correct=[2], acceptable=[[2]])
    incomplete = _row(ruled_status="estimated")
    incomplete.update(id="incomplete", key="44-11")

    artifact = build_value_audit([violated, conflict, incomplete])
    proposal = next(audit["calibration_proposal"] for audit in artifact["audits"]
                    if audit["correction_id"] == "corr")

    assert artifact["minimal_conflict_sets"] == [["corr", "other"]]
    assert "corr" not in proposal["blocked_by"]
    assert "incomplete" not in proposal["blocked_by"]


def test_conflicts_include_minimal_three_way_empty_intersections():
    rows = []
    for correction_id, acceptable in (
            ("a", [[0], [1]]), ("b", [[1], [2]]), ("c", [[0], [2]])):
        row = _row()
        row.update(id=correction_id, acceptable=acceptable)
        rows.append(row)

    assert build_value_audit(rows)["minimal_conflict_sets"] == [["a", "b", "c"]]


def test_existing_violations_do_not_block_each_others_proposals():
    first = _row()
    first["candidates"][1] = _candidate([1], 0.0, 2.0)
    second = _row()
    second.update(id="second", key="44-11")
    second["candidates"][1] = _candidate([1], 0.0, 2.0)

    audits = build_value_audit([first, second])["audits"]

    assert all(not audit["calibration_proposal"]["blocked_by"] for audit in audits)


def test_value_audit_cli_writes_the_canonical_artifact(tmp_path):
    source = tmp_path / "dashboard.json"
    output = tmp_path / "audit.json"
    source.write_text(json.dumps({"rows": [_row()]}), encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, "tools/train/ledger_value_audit.py", source,
         "--output", output, "--check"],
        cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True)

    assert completed.returncode == 0, completed.stderr
    assert json.loads(output.read_text(encoding="utf-8")) == build_value_audit([_row()])


def test_real_correction_replay_reaches_a_gradeable_value_audit():
    from train.blunder.store import load_corrections
    from train.ledger_corpus import _replay_one

    store = (Path(__file__).resolve().parents[2] / "data" / "corrections"
             / "20260827-193427_b988daf9_mega_starmie")
    correction = next(record for record in load_corrections(store)
                      if record.id == "05342c0cc9a2")

    audit = build_value_audit([
        _replay_one("mega_starmie", correction)
    ])["audits"][0]

    assert audit["gradeable"] is True
    assert audit["committed"]["status"] == "complete"
    assert audit["ruled"]["status"] == "complete"
    assert isinstance(audit["margin"]["atomic"], float)
