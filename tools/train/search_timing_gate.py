"""Compare search cost only while roots, budgets, coverage, and results stay fixed."""
from __future__ import annotations

from collections import Counter
import math
import statistics


WORK_COUNTERS = (
    "nodes_visited", "leaf_evaluations", "chance_nodes", "chance_branches",
    "memo_entries", "cycles",
)


def _positive_finite(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def _validate_baseline(baseline: dict) -> None:
    if baseline.get("schema") != "cgpy-search-timing-baseline" or baseline.get("schema_version") != 1:
        raise ValueError("unsupported Search Timing Baseline schema")
    repetitions = baseline["repetitions"]
    if type(repetitions) is not int or repetitions < 3 or repetitions % 2 == 0:
        raise ValueError("timing baseline requires an odd number of at least three repetitions")
    roots = baseline["roots"]
    if not roots or len({root["root_id"] for root in roots}) != len(roots):
        raise ValueError("timing baseline requires unique roots")
    limits = baseline["limits"]
    for key in ("median_time_multiplier", "batch_time_multiplier", "minimum_median_seconds"):
        if not _positive_finite(limits[key]):
            raise ValueError(f"invalid timing baseline limit: {key}")
    if min(limits["median_time_multiplier"], limits["batch_time_multiplier"]) < 1:
        raise ValueError("timing multipliers cannot reject the baseline itself")
    if not _positive_finite(baseline["measurement"]["batch_elapsed_seconds"]):
        raise ValueError("invalid baseline batch timing")
    for root in roots:
        if len(root["elapsed_seconds"]) != repetitions or not all(
                _positive_finite(value) for value in root["elapsed_seconds"]):
            raise ValueError(f"invalid timing samples for {root['root_id']}")
        if not root["reference_target_id"] or set(root["work"]) != set(WORK_COUNTERS):
            raise ValueError(f"missing result or compute evidence for {root['root_id']}")
        if any(type(value) is not int or value < 0 for value in root["work"].values()):
            raise ValueError(f"invalid compute baseline for {root['root_id']}")


def _root_report(rows: list[dict], baseline: dict, limits: dict) -> dict:
    failures = []
    timings = []
    observed = {name: [] for name in WORK_COUNTERS}
    root_id = baseline["root_id"]
    for row in rows:
        label = f"{root_id} repetition {row.get('repetition')}"
        if any(row.get(key) != value for key, value in (
                ("worker_status", "completed"), ("coverage", "complete"),
                ("stop_reason", "complete"), ("failure", None))) or row.get("reference_ready") is not True:
            failures.append(f"{label}: incomplete/uncertified search ({row.get('stop_reason')}; {row.get('failure')})")
        target = row.get("reference_target") or {}
        if target.get("target_id") != baseline["reference_target_id"]:
            failures.append(f"{label}: reference result changed")
        elapsed = row.get("elapsed_seconds")
        if not _positive_finite(elapsed):
            failures.append(f"{label}: missing/invalid elapsed_seconds")
        else:
            timings.append(elapsed)
        counters = row.get("statistics") or {}
        for name, maximum in baseline["work"].items():
            value = counters.get(name)
            if type(value) is not int or value < 0:
                failures.append(f"{label}: missing/invalid {name}")
                continue
            observed[name].append(value)
            if value > maximum:
                failures.append(f"{label}: {name} {value} > {maximum}")
    baseline_median = statistics.median(baseline["elapsed_seconds"])
    maximum_median = max(limits["minimum_median_seconds"],
                         baseline_median * limits["median_time_multiplier"])
    median = statistics.median(timings) if timings else None
    if median is not None and median > maximum_median:
        failures.append(f"{root_id}: median {median:.3f}s > {maximum_median:.3f}s")
    return {
        "root_id": root_id, "samples": len(rows), "median_seconds": median,
        "maximum_seconds": max(timings) if timings else None,
        "baseline_median_seconds": baseline_median,
        "maximum_median_seconds": maximum_median,
        "median_ratio": None if median is None else median / baseline_median,
        "work": {name: max(values) if values else None for name, values in observed.items()},
        "maximum_work": baseline["work"], "failures": failures,
    }


def check_run(run: dict, baseline: dict) -> dict:
    _validate_baseline(baseline)
    failures = []
    if run.get("schema") != "cgpy-search-timing-run" or run.get("schema_version") != 1:
        failures.append("unsupported Search Timing Run schema")
    for key in ("corpus_id", "method", "search_configuration", "execution"):
        if run.get(key) != baseline[key]:
            failures.append(f"{key} differs from the performance baseline")
    rows = run.get("results") or []
    expected = Counter((root["root_id"], repetition)
                       for root in baseline["roots"]
                       for repetition in range(1, baseline["repetitions"] + 1))
    actual = Counter((row.get("root_id"), row.get("repetition")) for row in rows)
    if actual != expected:
        failures.append("root/repetition inventory differs: missing, duplicate, or unexpected samples")
    roots = [_root_report([row for row in rows if row.get("root_id") == root["root_id"]],
                          root, baseline["limits"]) for root in baseline["roots"]]
    for root in roots:
        failures.extend(root["failures"])
    batch = (run.get("summary") or {}).get("batch_elapsed_seconds")
    maximum_batch = (baseline["measurement"]["batch_elapsed_seconds"]
                     * baseline["limits"]["batch_time_multiplier"])
    if not _positive_finite(batch):
        failures.append("missing/invalid batch_elapsed_seconds")
        batch = None
    elif batch > maximum_batch:
        failures.append(f"batch elapsed {batch:.3f}s > {maximum_batch:.3f}s")
    return {
        "schema": "cgpy-search-timing-gate", "schema_version": 1,
        "run_id": run.get("run_id"), "corpus_id": baseline["corpus_id"],
        "baseline_measurement": baseline["measurement"], "limits": baseline["limits"],
        "passed": not failures, "failures": failures, "roots": roots,
        "batch_elapsed_seconds": batch, "maximum_batch_seconds": maximum_batch,
    }


def render_report(report: dict) -> str:
    def seconds(value):
        return "missing" if value is None else f"{value:.3f}"

    lines = [
        f"## Search timing: {'PASS' if report['passed'] else 'FAIL'}", "",
        "Work is observed / ceiling. Time is median / ceiling in seconds.", "",
        "| Root | Median / limit | Nodes | Leaf evaluations | Chance branches |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for root in report["roots"]:
        work = [f"{root['work'][name]} / {root['maximum_work'][name]}"
                for name in ("nodes_visited", "leaf_evaluations", "chance_branches")]
        lines.append(f"| {root['root_id']} | {seconds(root['median_seconds'])} / "
                     f"{seconds(root['maximum_median_seconds'])} | {' | '.join(work)} |")
    lines.extend(["", f"Batch: {seconds(report['batch_elapsed_seconds'])} / "
                  f"{seconds(report['maximum_batch_seconds'])} seconds.", ""])
    lines.extend(f"- {failure}" for failure in report["failures"])
    return "\n".join(lines) + "\n"
