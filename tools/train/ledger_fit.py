from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "src")]

from common.ledger.training import (build_artifact, examples_from_rows, fit_calibration,
                                    fit_pairwise, pairwise_metrics, split_examples)


def load_rows(paths) -> list[dict]:
    rows = []
    for path in paths:
        path = Path(path)
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".jsonl":
            rows.extend(json.loads(line) for line in text.splitlines() if line.strip())
        else:
            payload = json.loads(text)
            rows.extend(payload.get("rows", ()) if isinstance(payload, dict) else payload)
    return rows


def fit_rows(rows, *, epochs=None, learning_rate=None, l2=None) -> dict:
    examples = examples_from_rows(rows)
    splits = split_examples(examples)
    kwargs = {key: value for key, value in (
        ("epochs", epochs), ("learning_rate", learning_rate), ("l2", l2))
              if value is not None}
    weights = fit_pairwise(splits["train"], **kwargs)
    metrics = {name: pairwise_metrics(values, weights)
               for name, values in splits.items()}
    calibration = fit_calibration(splits["validation"] or splits["train"], weights)
    return build_artifact(rows, weights, splits, metrics, calibration)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--epochs", type=int)
    parser.add_argument("--learning-rate", type=float)
    parser.add_argument("--l2", type=float)
    args = parser.parse_args(argv)
    artifact = fit_rows(load_rows(args.inputs), epochs=args.epochs,
                        learning_rate=args.learning_rate, l2=args.l2)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
