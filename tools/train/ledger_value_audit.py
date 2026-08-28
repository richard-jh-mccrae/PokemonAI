from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from train.value_audit import build_value_audit


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    rows = []
    for path in args.inputs:
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows.extend(payload.get("rows", ()) if isinstance(payload, dict) else payload)
    artifact = build_value_audit(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(artifact["summary"], sort_keys=True))
    if not args.check:
        return 0
    return int(bool(artifact["summary"]["incomplete"]
                    or artifact["summary"]["violated_preferences"]))


if __name__ == "__main__":
    raise SystemExit(main())
