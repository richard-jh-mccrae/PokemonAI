"""Freeze the manually corrected one-ply Ledger as an immutable Baseline."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys
import tempfile


REPO = Path(__file__).resolve().parents[2]
DEFAULT_ROOT = REPO / "data" / "ledger-baselines"


def _identity(manifest: dict) -> str:
    import hashlib

    body = json.dumps({**manifest, "baseline_id": None}, sort_keys=True,
                      separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def _source(path: str | Path) -> Path:
    path = Path(path)
    return path if path.is_absolute() else REPO / path


def publish_pack(baseline: dict, *, out_root: Path) -> Path:
    import hashlib
    from common.ledger.baseline import validate_baseline

    out_root.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".baseline-", dir=out_root))
    evidence = stage / "evidence"
    evidence.mkdir()
    report = baseline["certification"]["report"]
    for gate in report["gates"]:
        command = gate["command"].replace(sys.executable, "python")
        gate["command"] = command.replace(
            str(REPO) + "\\", "").replace(str(REPO) + "/", "").replace("\\", "/")

    def copy_path(container: dict, key: str) -> None:
        source = _source(container[key])
        target = evidence / source.name
        shutil.copyfile(source, target)
        container[key] = f"evidence/{target.name}"
        sha_key = key.replace("path", "sha256")
        if sha_key in container:
            container[sha_key] = hashlib.sha256(target.read_bytes()).hexdigest()

    copy_path(report["manual_review"], "artifact_path")
    for gate in report["gates"]:
        copy_path(gate, "output_path")
        if gate.get("artifact_path"):
            copy_path(gate, "artifact_path")
    for key in ("before_path", "after_path", "semantic_flips_path"):
        if report["regressions"].get(key):
            copy_path(report["regressions"], key)
    certification_copy = evidence / "certification.json"
    certification_copy.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    baseline["certification"] = {
        "path": "evidence/certification.json",
        "sha256": hashlib.sha256(certification_copy.read_bytes()).hexdigest(),
        "report": report,
    }
    baseline["baseline_id"] = _identity(baseline)
    validate_baseline(baseline)
    output = out_root / baseline["baseline_id"]
    if output.exists():
        raise ValueError(f"immutable Ledger Baseline already exists: {output}")
    (stage / "manifest.json").write_text(
        json.dumps(baseline, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    stage.rename(output)
    return output / "manifest.json"


def main(argv=None) -> int:
    sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]
    from sim.run_identity import git_source_identity
    from train.baseline import build_baseline
    from train.blunder.store import jsonl_files

    parser = argparse.ArgumentParser(description="Freeze a certified one-ply Ledger Baseline")
    parser.add_argument("--run", action="append", type=Path, required=True,
                        help="completed Correction Run directory; repeatable")
    parser.add_argument("--corpus", action="append", type=Path, required=True,
                        help="historical Correction JSONL or directory; repeatable")
    parser.add_argument("--reviewed-corrections", type=Path, required=True)
    parser.add_argument("--tuning-correction", action="append", type=Path, default=[])
    parser.add_argument("--certification", type=Path, required=True,
                        help="passed review JSON bound to run, bundle, source, and behavior IDs")
    parser.add_argument("--known-weakness", action="append", default=[])
    parser.add_argument("--created-at")
    parser.add_argument("--out-root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args(argv)

    correction_files = [path for source in args.corpus for path in jsonl_files(source)]
    if not correction_files:
        raise ValueError("no Correction JSONL files found")
    baseline = build_baseline(
        correction_runs=args.run, correction_corpus=args.corpus,
        reviewed_corrections=args.reviewed_corrections,
        tuning_corrections=args.tuning_correction,
        certification=args.certification, known_weaknesses=args.known_weakness,
        current_source_identity=git_source_identity(
            REPO, allow_dirty=False,
            exclude_paths=(*args.run, *correction_files, args.reviewed_corrections,
                           args.certification, args.out_root)),
        created_at=args.created_at or datetime.now(timezone.utc).isoformat())
    output = publish_pack(baseline, out_root=args.out_root)
    print(f"froze {baseline['baseline_id']} -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
