"""Run the fixed Issue #601 gates and bind their results to Correction Run evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


REPO = Path(__file__).resolve().parents[2]
PYTEST = (sys.executable, "-m", "pytest")
GATES = {
    "cross_deck_regressions": (*PYTEST, "tests/ledger", "tests/cards/test_pokemon_store.py"),
    "native_full_games": (*PYTEST, "tests/sim/test_battle.py", "-k", "full_game"),
    "twin_full_games": (*PYTEST, "tests/ledger/test_full_game_smoke.py"),
    "source_contracts": (*PYTEST, "tests/observation", "tests/cards", "tests/common",
                         "tests/ledger", "tests/parity", "tests/scouting", "tests/blunder",
                         "tests/train", "tests/test_import_hygiene.py",
                         "tests/test_source_reachability.py",
                         "--ignore=tests/ledger/test_real_engine_timing.py"),
    "documentation": (*PYTEST, "tests/test_adr_index.py", "tests/test_comment_budget.py",
                      "tests/test_doc_links_resolve.py", "tests/test_line_endings_policy.py",
                      "tests/test_prose_policy.py"),
    "correction_ci": (sys.executable, "tools/train/ledger_correction_gate.py",
                      "--workers", "2"),
    "readiness": (sys.executable, "tools/train/ledger_readiness.py", "--json",
                  "--warnings-as-errors", "--decks", "mega_starmie", "mega_lucario",
                  "dragapult_ex"),
    "performance": (*PYTEST, "tests/ledger/test_real_engine_timing.py"),
}


def _load_corpus_report(path: Path, *, label: str) -> dict:
    report = json.loads(Path(path).read_text(encoding="utf-8"))
    if report.get("schema") != 1 or not report.get("git_rev") \
            or not isinstance(report.get("rows"), list) or not report["rows"] \
            or not isinstance(report.get("generality_floor"), (int, float)):
        raise ValueError(f"{label} is not a reproducible Ledger corpus report")
    return report


def _portable(path: Path) -> str:
    path = Path(path).resolve()
    try:
        return path.relative_to(REPO).as_posix()
    except ValueError:
        return str(path)


def _load_review(path: Path, inventory: dict) -> tuple[dict, list[dict], list[dict]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema") != "ledger.baseline-review" \
            or document.get("schema_version") != 1 \
            or document.get("source_identity") != inventory["evidence"]["source_identity"] \
            or document.get("correction_runs") != inventory["evidence"]["correction_runs"]:
        raise ValueError("review artifact does not bind the Baseline Candidate")
    rows = document.get("rows")
    if not isinstance(rows, list):
        raise ValueError("review artifact rows are missing")
    expected = {(partition, row["record_id"])
                for partition, decisions in inventory["review_decisions"].items()
                for row in decisions}
    actual = [(row.get("partition"), row.get("record_id")) for row in rows]
    if len(actual) != len(set(actual)) or set(actual) != expected:
        raise ValueError("review artifact must cover every candidate decision exactly once")
    tuning = [row for row in rows if row["partition"] == "tuning"]
    heldout = [row for row in rows if row["partition"] == "heldout"]
    if any(row.get("verdict") != "pass" for row in rows):
        raise ValueError("review artifact contains a failed decision")
    return document, tuning, heldout


def build_certification(*, correction_runs, review: Path,
                        correction_corpus, reviewed_corrections: Path,
                        tuning_corrections=(), before_report: Path, evidence_dir: Path,
                        runner=subprocess.run) -> dict:
    from train.baseline import (certification_inventory, correction_artifacts,
                                correction_corpus_artifacts)

    inventory = certification_inventory(correction_runs)
    corpus_artifacts, _records = correction_corpus_artifacts(
        correction_corpus, reviewed_corrections)
    tuning_artifacts, _tuning_records = correction_artifacts(tuning_corrections)
    corpus_identity = hashlib.sha256(json.dumps(
        corpus_artifacts, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False).encode("utf-8")).hexdigest()
    tuning_identity = hashlib.sha256(json.dumps(
        tuning_artifacts, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False).encode("utf-8")).hexdigest()
    review = Path(review)
    _review_document, tuning_review, heldout_review = _load_review(review, inventory)
    before_report = Path(before_report)
    before = _load_corpus_report(before_report, label="before report")
    evidence_dir = Path(evidence_dir)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    gate_results = []
    historical = evidence_dir / "historical-corrections.json"
    selections = {
        "historical_corrections": (
            sys.executable, str(REPO / "tools" / "train" / "ledger_corpus.py"),
            "--output", str(historical), "--baseline", str(before_report),
            "--workers", str(max(1, (os.cpu_count() or 2) - 1)),
            *(value for source in correction_corpus for value in ("--store", str(source)))),
        **GATES,
    }
    for name, selection in selections.items():
        command = [*selection]
        if command[1:3] == ["-m", "pytest"]:
            command.extend(("-q", "--tb=short"))
        environment = dict(os.environ)
        if name == "native_full_games":
            environment.pop("CG_ENGINE", None)
        completed = runner(command, cwd=REPO, capture_output=True, text=True,
                           check=False, env=environment)
        output = (completed.stdout or "") + (completed.stderr or "")
        output_path = evidence_dir / f"{name}.log"
        output_path.write_text(output, encoding="utf-8")
        artifact = historical if name == "historical_corrections" else None
        gate_results.append({
            "name": name, "command": " ".join(command),
            "passed": completed.returncode == 0 and (artifact is None or artifact.is_file()),
            "output_sha256": hashlib.sha256(output.encode("utf-8")).hexdigest(),
            "output_path": _portable(output_path),
            **({"artifact_path": _portable(artifact), "artifact_sha256": hashlib.sha256(
                artifact.read_bytes()).hexdigest()} if artifact is not None and artifact.is_file()
               else {}),
        })
    after = _load_corpus_report(historical, label="generated after report")
    if after.get("baseline_git_rev") != before["git_rev"] \
            or after.get("baseline_generality_floor") != before["generality_floor"]:
        raise ValueError("generated report does not bind the before report")
    unreported = after.get("unexplained_regressions")
    regression_passed = unreported == [] and after.get("generality_floor_retained") is True
    target = {"name": "generality_floor", "before": float(before["generality_floor"]),
              "after": float(after["generality_floor"])}
    passed = (all(gate["passed"] for gate in gate_results)
              and regression_passed and target["after"] > target["before"])
    return {
        "passed": passed, "gates": gate_results,
        "correction_corpus_identity": corpus_identity,
        "tuning_corrections_identity": tuning_identity,
        "manual_review": {
            "completed": True, "reviewed_decisions": len(tuning_review),
            "episode_ids": inventory["tuning_episode_ids"],
            "artifact_path": _portable(review),
            "artifact_sha256": hashlib.sha256(review.read_bytes()).hexdigest(),
        },
        "heldout": {
            "passed": bool(heldout_review),
            "episode_ids": inventory["heldout_episode_ids"],
            "reviewed_decisions": len(heldout_review),
        },
        "tuning_target": target,
        "regressions": {
            "passed": regression_passed, "unreported": unreported,
            "before_path": _portable(before_report),
            "before_sha256": hashlib.sha256(before_report.read_bytes()).hexdigest(),
            "after_path": _portable(historical),
            "after_sha256": hashlib.sha256(historical.read_bytes()).hexdigest(),
        },
        "evidence": inventory["evidence"],
    }


def main(argv=None) -> int:
    sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]
    parser = argparse.ArgumentParser(description="Certify the final three-deck Ledger Baseline")
    parser.add_argument("--run", action="append", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--corpus", action="append", type=Path, required=True)
    parser.add_argument("--reviewed-corrections", type=Path, required=True)
    parser.add_argument("--tuning-correction", action="append", type=Path, default=[])
    parser.add_argument("--before-report", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    report = build_certification(
        correction_runs=args.run, review=args.review,
        correction_corpus=args.corpus, reviewed_corrections=args.reviewed_corrections,
        tuning_corrections=args.tuning_correction,
        before_report=args.before_report,
        evidence_dir=args.evidence_dir)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{'passed' if report['passed'] else 'failed'} -> {args.out}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
