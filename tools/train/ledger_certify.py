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
GATES = {
    "cross_deck_regressions": ("tests/ledger", "tests/cards/test_pokemon_store.py"),
    "native_full_games": ("tests/sim/test_battle.py", "-k", "full_game"),
    "twin_full_games": ("tests/ledger/test_full_game_smoke.py",),
}


def _load_corpus_report(path: Path, *, label: str) -> dict:
    report = json.loads(Path(path).read_text(encoding="utf-8"))
    if report.get("schema") != 1 or not report.get("git_rev") \
            or not isinstance(report.get("rows"), list) or not report["rows"] \
            or not isinstance(report.get("generality_floor"), (int, float)):
        raise ValueError(f"{label} is not a reproducible Ledger corpus report")
    return report


def build_certification(*, correction_runs, reviewed_decisions: int,
                        corrections, before_report: Path, evidence_dir: Path,
                        runner=subprocess.run) -> dict:
    from train.baseline import certification_inventory, correction_artifacts

    inventory = certification_inventory(correction_runs)
    artifacts, _records = correction_artifacts(corrections)
    if not artifacts:
        raise ValueError("certification requires manual Corrections")
    corrections_identity = hashlib.sha256(json.dumps(
        artifacts, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False).encode("utf-8")).hexdigest()
    if int(reviewed_decisions) != inventory["evidence"]["tuning_ledger_decisions"]:
        raise ValueError("reviewed decision count must equal every tuning Ledger decision")
    before_report = Path(before_report)
    before = _load_corpus_report(before_report, label="before report")
    evidence_dir = Path(evidence_dir)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    gate_results = []
    historical = evidence_dir / "historical-corrections.json"
    selections = {
        "historical_corrections": (
            str(REPO / "tools" / "train" / "ledger_corpus.py"),
            "--output", str(historical), "--baseline", str(before_report),
            "--workers", str(max(1, (os.cpu_count() or 2) - 1)),
            *(value for source in corrections for value in ("--store", str(source)))),
        **GATES,
    }
    for name, selection in selections.items():
        command = ([sys.executable, *selection] if name == "historical_corrections" else
                   [sys.executable, "-m", "pytest", *selection, "-q", "--tb=short"])
        environment = dict(os.environ)
        if name == "native_full_games":
            environment.pop("CG_ENGINE", None)
        completed = runner(command, cwd=REPO, capture_output=True, text=True,
                           check=False, env=environment)
        output = (completed.stdout or "") + (completed.stderr or "")
        artifact = historical if name == "historical_corrections" else None
        gate_results.append({
            "name": name, "command": " ".join(command),
            "passed": completed.returncode == 0 and (artifact is None or artifact.is_file()),
            "output_sha256": hashlib.sha256(output.encode("utf-8")).hexdigest(),
            **({"artifact_path": str(artifact), "artifact_sha256": hashlib.sha256(
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
        "corrections_identity": corrections_identity,
        "manual_review": {
            "completed": True, "reviewed_decisions": int(reviewed_decisions),
            "episode_ids": inventory["tuning_episode_ids"],
        },
        "heldout": {"passed": passed, "episode_ids": inventory["heldout_episode_ids"]},
        "tuning_target": target,
        "regressions": {
            "passed": regression_passed, "unreported": unreported,
            "before_path": str(before_report),
            "before_sha256": hashlib.sha256(before_report.read_bytes()).hexdigest(),
            "after_path": str(historical),
            "after_sha256": hashlib.sha256(historical.read_bytes()).hexdigest(),
        },
        "evidence": inventory["evidence"],
    }


def main(argv=None) -> int:
    sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]
    parser = argparse.ArgumentParser(description="Certify the final three-deck Ledger Baseline")
    parser.add_argument("--run", action="append", type=Path, required=True)
    parser.add_argument("--reviewed-decisions", type=int, required=True)
    parser.add_argument("--corrections", action="append", type=Path, required=True)
    parser.add_argument("--before-report", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    report = build_certification(
        correction_runs=args.run, reviewed_decisions=args.reviewed_decisions,
        corrections=args.corrections,
        before_report=args.before_report,
        evidence_dir=args.evidence_dir)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{'passed' if report['passed'] else 'failed'} -> {args.out}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
