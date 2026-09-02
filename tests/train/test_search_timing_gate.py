from copy import deepcopy
from dataclasses import asdict
import json

import pytest

from cgpy.experiment import TeacherSearchConfiguration, TeacherExecutionConfiguration
from train import search_timing, search_timing_gate


BASELINE = search_timing.REPO / "data/benchmarks/search_timing/teacher_live_ci_baseline.json"


def _baseline():
    return {
        "schema": "cgpy-search-timing-baseline", "schema_version": 1,
        "corpus_id": "fixed-corpus", "method": "teacher_exhaustive",
        "search_configuration": asdict(TeacherSearchConfiguration(time_cap_seconds=120)),
        "execution": asdict(TeacherExecutionConfiguration(workers=1, root_timeout_seconds=140)),
        "repetitions": 3,
        "limits": {"median_time_multiplier": 2.0, "minimum_median_seconds": 0.25,
                   "batch_time_multiplier": 2.0},
        "measurement": {"batch_elapsed_seconds": 10.0, "run_schema_version": 2},
        "roots": [{
            "root_id": "test-root", "reference_target_id": "fixed-target",
            "reference_target": {
                "root_state_key": "root", "preferred_action": {"kind": "end", "parts": []},
                "selected_policy": [{"state_key": "root", "expected_value": 8.73356856142241}],
                "leaves": [{"state_key": "leaf", "value": 8.73356856142241, "probability": 1.0}],
                "best_full_sequence": [{"kind": "end", "parts": []}],
            },
            "elapsed_seconds": [1.0, 1.1, 0.9],
            "work": {name: (0 if name == "cycles" else 10)
                     for name in search_timing_gate.WORK_COUNTERS},
        }],
    }


def _passing_run(baseline):
    return {
        "schema": search_timing.RUN_SCHEMA, "schema_version": search_timing.RUN_SCHEMA_VERSION,
        "run_id": "test-run",
        "generated_at": "2026-09-02T00:00:00Z", "host": {"python": "test"},
        "source_identity": {"commit": "test-commit", "dirty": False},
        "method_identity": baseline.get("method_identity", "test-teacher"),
        **{key: deepcopy(baseline[key]) for key in (
            "corpus_id", "method", "search_configuration", "execution")},
        "summary": {"batch_elapsed_seconds": 10.0},
        "results": [{
            "root_id": root["root_id"], "repetition": repetition,
            "worker_status": "completed", "coverage": "complete", "stop_reason": "complete",
            "failure": None, "reference_ready": True,
            "reference_target": {**deepcopy(root["reference_target"]),
                                 "target_id": root["reference_target_id"]},
            "elapsed_seconds": elapsed, "statistics": dict(root["work"]),
            "search_configuration": root.get("search_configuration", baseline["search_configuration"]),
            "search_configuration_identity": root.get("search_configuration_identity", "test-config"),
        } for root in baseline["roots"]
            for repetition, elapsed in enumerate(root["elapsed_seconds"], 1)],
    }


def test_committed_limits_cover_the_immutable_corpus_and_preserve_measurement_provenance():
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    corpus = json.loads((search_timing.DEFAULT_CORPUS / "manifest.json").read_text(encoding="utf-8"))

    assert baseline["corpus_id"] == corpus["corpus_id"]
    assert {root["root_id"] for root in baseline["roots"]} == {
        case["root_id"] for case in corpus["cases"]}
    assert baseline["execution"]["workers"] == 2
    assert baseline["execution"]["parallelism_scope"] == "root_actions"
    assert baseline["execution"]["latency_scope"] == "decision_wall"
    assert baseline["repetitions"] == 3
    assert baseline["measurement"]["source_identity"]["dirty"] is False
    assert baseline["measurement"]["run_id"]
    assert baseline["measurement"]["host"]["python"]
    assert search_timing_gate.check_run(_passing_run(baseline), baseline)["passed"]


def test_historical_worker_only_baseline_remains_readable_but_rejects_live_latency():
    baseline = json.loads(BASELINE.with_name("teacher_ci_baseline.json").read_text(encoding="utf-8"))
    run = _passing_run(baseline)
    assert not search_timing_gate.check_run(run, baseline)["passed"]
    run["schema_version"] = 1
    assert search_timing_gate.check_run(run, baseline)["passed"]


def test_gate_allows_less_compute_and_one_timing_outlier_with_identical_results():
    baseline = _baseline()
    run = _passing_run(baseline)
    run["results"][0]["elapsed_seconds"] = 5.0
    for row in run["results"]:
        row["statistics"]["nodes_visited"] -= 1

    report = search_timing_gate.check_run(run, baseline)

    assert report["passed"]
    assert report["roots"][0]["median_seconds"] == 1.1
    assert report["roots"][0]["maximum_seconds"] == 5.0
    assert report["roots"][0]["maximum_median_seconds"] == 2.0
    assert "test-root" in search_timing_gate.render_report(report)


def test_reference_values_allow_only_the_existing_search_noise_tolerance():
    baseline = _baseline()
    run = _passing_run(baseline)
    target = run["results"][0]["reference_target"]
    target["target_id"] = "different-raw-float-fingerprint"
    target["selected_policy"][0]["expected_value"] = 8.733568561422414
    target["leaves"][0]["value"] = 8.733568561422414

    assert search_timing_gate.check_run(run, baseline)["passed"]
    target["leaves"][0]["value"] += 1e-8
    assert not search_timing_gate.check_run(run, baseline)["passed"]


def test_equivalent_integer_and_float_json_probabilities_compare_exactly():
    baseline = _baseline()
    baseline["roots"][0]["reference_target"]["leaves"][0]["probability"] = 1
    run = _passing_run(baseline)
    run["results"][0]["reference_target"]["leaves"][0]["probability"] = 1.0

    assert search_timing_gate.check_run(run, baseline)["passed"]


@pytest.mark.parametrize("field,value", [
    ("probability", 1.0 - 1e-14), ("state_key", "other-leaf"),
    ("value", float("nan")), ("value", float("inf")),
])
def test_reference_tolerance_never_hides_structural_probability_or_invalid_value_changes(field, value):
    baseline = _baseline()
    run = _passing_run(baseline)
    run["results"][0]["reference_target"]["leaves"][0][field] = value

    assert not search_timing_gate.check_run(run, baseline)["passed"]


@pytest.mark.parametrize("field", ["preferred_action", "best_full_sequence", "selected_policy"])
def test_reference_policy_and_sequence_remain_exact(field):
    baseline = _baseline()
    run = _passing_run(baseline)
    run["results"][0]["reference_target"][field] = None

    assert not search_timing_gate.check_run(run, baseline)["passed"]


@pytest.mark.parametrize("counter", search_timing_gate.WORK_COUNTERS)
def test_gate_rejects_any_compute_growth_in_even_one_repetition(counter):
    baseline = _baseline()
    run = _passing_run(baseline)
    run["results"][0]["statistics"][counter] += 1

    report = search_timing_gate.check_run(run, baseline)

    assert not report["passed"]
    assert any(counter in failure for failure in report["failures"])


def test_gate_rejects_median_slowdown_even_when_other_root_is_faster():
    baseline = _baseline()
    second = deepcopy(baseline["roots"][0])
    second["root_id"] = "second-root"
    baseline["roots"].append(second)
    run = _passing_run(baseline)
    for row in run["results"]:
        row["elapsed_seconds"] = 2.01 if row["root_id"] == "test-root" else 0.1

    report = search_timing_gate.check_run(run, baseline)

    assert not report["passed"]
    assert any("test-root: median" in failure for failure in report["failures"])


def test_tiny_roots_use_absolute_timing_floor():
    baseline = _baseline()
    baseline["roots"][0]["elapsed_seconds"] = [0.01] * 3
    run = _passing_run(baseline)
    for row in run["results"]:
        row["elapsed_seconds"] = 0.25

    assert search_timing_gate.check_run(run, baseline)["passed"]
    for row in run["results"]:
        row["elapsed_seconds"] = 0.251
    assert not search_timing_gate.check_run(run, baseline)["passed"]


@pytest.mark.parametrize("field,value", [
    ("schema_version", 2), ("repetitions", 2), ("repetitions", 4), ("roots", []),
])
def test_invalid_baseline_cannot_silently_disable_assertions(field, value):
    baseline = _baseline()
    run = _passing_run(baseline)
    baseline[field] = value

    with pytest.raises(ValueError):
        search_timing_gate.check_run(run, baseline)


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), 0, -1])
def test_invalid_timing_ceiling_is_rejected(invalid):
    baseline = _baseline()
    run = _passing_run(baseline)
    baseline["limits"]["median_time_multiplier"] = invalid

    with pytest.raises(ValueError):
        search_timing_gate.check_run(run, baseline)


@pytest.mark.parametrize("field,value", [
    ("worker_status", "unavailable"), ("coverage", "incomplete"),
    ("stop_reason", "time_cap"), ("failure", "failed"), ("reference_ready", False),
    ("reference_target", None), ("reference_target", {"target_id": "changed-target"}),
    ("elapsed_seconds", None), ("elapsed_seconds", float("nan")),
    ("elapsed_seconds", float("inf")), ("elapsed_seconds", -1),
    ("statistics", None), ("statistics", {"nodes_visited": float("nan")}),
])
def test_gate_fails_closed_on_incomplete_changed_or_missing_evidence(field, value):
    baseline = _baseline()
    run = _passing_run(baseline)
    run["results"][0][field] = value

    assert not search_timing_gate.check_run(run, baseline)["passed"]


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "extra", "wrong-repetition"])
def test_gate_requires_every_root_and_repetition_exactly_once(mutation):
    baseline = _baseline()
    run = _passing_run(baseline)
    if mutation == "missing":
        run["results"].pop()
    elif mutation == "duplicate":
        run["results"].append(deepcopy(run["results"][0]))
    elif mutation == "extra":
        extra = deepcopy(run["results"][0])
        extra["root_id"] = "unexpected"
        run["results"].append(extra)
    else:
        run["results"][0]["repetition"] = 0

    assert not search_timing_gate.check_run(run, baseline)["passed"]


@pytest.mark.parametrize("field", ["corpus_id", "method", "search_configuration", "execution", "schema"])
def test_gate_rejects_uncomparable_runs(field):
    baseline = _baseline()
    run = _passing_run(baseline)
    run[field] = "changed"

    assert not search_timing_gate.check_run(run, baseline)["passed"]


@pytest.mark.parametrize("elapsed", [20.01, None, float("nan"), float("inf"), -1])
def test_batch_ceiling_also_catches_worker_startup_and_serialization_regressions(elapsed):
    baseline = _baseline()
    run = _passing_run(baseline)
    run["summary"]["batch_elapsed_seconds"] = elapsed

    assert not search_timing_gate.check_run(run, baseline)["passed"]


@pytest.mark.parametrize("fails", [False, True])
def test_cli_writes_gate_evidence_and_returns_nonzero_on_regression(tmp_path, monkeypatch, fails):
    baseline = _baseline()
    run = _passing_run(baseline)
    if fails:
        run["results"][0]["statistics"]["nodes_visited"] += 1
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
    output = tmp_path / "run.json"
    output.write_text(json.dumps(run), encoding="utf-8")
    monkeypatch.setattr(search_timing, "run_teacher", lambda *args, **kwargs: output)

    result = search_timing.main(["run", "--assert-baseline", str(baseline_path)])

    assert result == int(fails)
    assert json.loads(output.read_text(encoding="utf-8")) == run
    report = json.loads(output.with_suffix(".gate.json").read_text(encoding="utf-8"))
    assert report["passed"] is not fails
    assert "test-root" in output.with_suffix(".gate.md").read_text(encoding="utf-8")


def test_ci_runs_real_corpus_with_branch_workers_and_retains_gate_artifacts():
    import yaml

    workflow = yaml.safe_load((search_timing.REPO / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    job = workflow["jobs"]["test-performance"]
    assert job["env"]["PYTHONHASHSEED"] == "0"
    step = next(step for step in job["steps"] if "--assert-baseline" in step.get("run", ""))
    for option in ("--jobs 2", "--repetitions 3", "--time-cap 120", "--root-timeout 140"):
        assert option in step["run"]
    assert "--root " not in step["run"]
    upload = next(step for step in job["steps"] if step.get("uses", "").startswith("actions/upload-artifact@"))
    assert upload["if"] == "always()"


def test_freeze_baseline_pins_live_contract_and_rejects_incomplete_or_dirty_runs():
    baseline = _baseline()
    baseline["measurement"]["run_schema_version"] = 2
    run = _passing_run(baseline)
    frozen = search_timing_gate.baseline_from_run(run)
    assert frozen["measurement"]["run_id"] == run["run_id"]
    assert frozen["measurement"]["run_schema_version"] == 2
    assert frozen["roots"][0]["search_configuration"] == run["results"][0]["search_configuration"]
    assert search_timing_gate.check_run(run, frozen)["passed"]
    run["results"][0]["stop_reason"] = "time_cap"
    with pytest.raises(ValueError, match="cannot certify"):
        search_timing_gate.baseline_from_run(run)
    run["source_identity"]["dirty"] = True
    with pytest.raises(ValueError, match="clean checkout"):
        search_timing_gate.baseline_from_run(run)


def test_live_baseline_pins_method_and_each_resolved_deck_configuration():
    baseline = _baseline()
    baseline["measurement"]["run_schema_version"] = 2
    run = _passing_run(baseline)
    frozen = search_timing_gate.baseline_from_run(run)
    run["results"][0]["search_configuration_identity"] = "all-legal-instead-of-deck-policy"
    assert not search_timing_gate.check_run(run, frozen)["passed"]
    run = _passing_run(frozen)
    run["method_identity"] = "other-teacher"
    assert not search_timing_gate.check_run(run, frozen)["passed"]


def test_baseline_cli_preserves_existing_artifacts(tmp_path):
    run = _passing_run(_baseline())
    source = tmp_path / "run.json"
    source.write_text(json.dumps(run), encoding="utf-8")
    output = tmp_path / "baseline.json"
    args = ["baseline", "--run", str(source), "--out", str(output)]

    assert search_timing.main(args) == 0
    original = output.read_bytes()
    assert search_timing_gate.check_run(run, json.loads(original))["passed"]
    with pytest.raises(ValueError, match="already exists"):
        search_timing.main(args)
    assert output.read_bytes() == original
