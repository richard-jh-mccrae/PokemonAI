from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from train.blunder.store import (DEFAULT_ROOT, dedup_corrections, jsonl_files,
                                 load_corrections)  # noqa: E402
from train.ledger_corpus import sweep  # noqa: E402
from train.value_audit import build_value_audit  # noqa: E402


ONE_PLY_LEDGER_FIRST_RUN = "20260828-111914_ad58ab7d_mega_starmie"
EXACT_SELECTION_FIRST_RUN = "20260830-082433_d00f93d6_mega_starmie"
PUCT_ATTRIBUTION = "puct_search"


def is_one_ply_ledger_correction(correction) -> bool:
    return correction.attribution != PUCT_ATTRIBUTION


def ledger_correction_sources(root: Path | str = DEFAULT_ROOT) -> tuple[Path, ...]:
    return tuple(path for path in jsonl_files(root)
                 if path.parent.name >= ONE_PLY_LEDGER_FIRST_RUN
                 and path.parent.name[:1].isdigit())


def correction_gate_findings(report: dict, audit: dict, *,
                             correction_count: int) -> tuple[str, ...]:
    rows = report.get("rows", ())
    exact_ids = {
        row.get("id") for row in rows
        if row.get("agent_build", "") >= EXACT_SELECTION_FIRST_RUN}
    replayed = len(rows) + len(report.get("retired", ()))
    findings = []
    if not correction_count:
        findings.append("no one-ply Ledger corrections selected")
    if replayed != correction_count:
        findings.append(f"replayed {replayed} of {correction_count} corrections")
    structural = sum(row.get("grading_exclusion") is not None
                     and row.get("id") in exact_ids for row in rows)
    if structural:
        findings.append(f"{structural} correction replays are structurally incomplete")
    repeated = sum(bool(
        row.get("graded")
        and not row.get("agrees")
        and row.get("chosen") is not None
        and row.get("chosen") == row.get("recorded_chosen")
        and row.get("id") in exact_ids)
        for row in rows)
    if repeated:
        findings.append(f"{repeated} correction replays repeat the recorded blunder")
    different_wrong = sum(bool(
        row.get("graded")
        and not row.get("agrees")
        and row.get("chosen") is not None
        and row.get("chosen") != row.get("recorded_chosen")
        and row.get("agent_build", "") >= EXACT_SELECTION_FIRST_RUN)
        for row in rows)
    if different_wrong:
        findings.append(f"{different_wrong} correction replays choose outside the ruling")
    incomplete = sum(
        item.get("correction_id") in exact_ids and not item["gradeable"]
        for item in audit.get("audits", ()))
    if incomplete:
        findings.append(f"{incomplete} pairwise value audits are incomplete")
    conflicts = sum(
        bool(set(group) & exact_ids)
        for group in audit.get("minimal_conflict_sets", ()))
    if conflicts:
        findings.append(f"{conflicts} correction conflict sets remain")
    unresolved = sum(
        item["gradeable"]
        and item.get("correction_id") in exact_ids
        and not item["satisfied_by_committed"]
        and item["current_selection"] not in item["acceptable_selections"]
        and item["margin"]["atomic"] <= 0
        for item in audit.get("audits", ()))
    if unresolved:
        findings.append(f"{unresolved} correction preferences are violated")
    fallbacks = sum(bool(row.get("fallback")) and row.get("id") in exact_ids
                    for row in rows)
    if fallbacks:
        findings.append(f"{fallbacks} correction replays used a fallback")
    return tuple(findings)


def run_gate(*, root: Path | str = DEFAULT_ROOT, workers: int = 1) -> dict:
    sources = ledger_correction_sources(root)
    corrections = dedup_corrections([
        correction for source in sources
        for correction in load_corrections(source, dedup=False)
        if is_one_ply_ledger_correction(correction)
    ])
    report = sweep(
        store=sources,
        workers=workers,
        correction_filter=is_one_ply_ledger_correction,
    )
    audit = build_value_audit(report["rows"])
    findings = correction_gate_findings(
        report, audit, correction_count=len(corrections))
    return {"passed": not findings, "findings": list(findings),
            "correction_count": len(corrections), "sources": [str(path) for path in sources],
            "report": report, "value_audit": audit}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Gate every one-ply Ledger correction")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--workers", type=int,
                        default=max(1, (os.cpu_count() or 2) - 1))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = run_gate(root=args.root, workers=max(1, args.workers))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                               encoding="utf-8")
    print(json.dumps({key: result[key] for key in (
        "passed", "correction_count", "findings")}, sort_keys=True))
    return 0 if result["passed"] else 1


__all__ = ("EXACT_SELECTION_FIRST_RUN", "ONE_PLY_LEDGER_FIRST_RUN",
           "correction_gate_findings",
           "is_one_ply_ledger_correction", "ledger_correction_sources", "run_gate")


if __name__ == "__main__":
    raise SystemExit(main())
