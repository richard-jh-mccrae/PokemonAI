"""Train the Automatic Value Model and write the shipped artifact (ADR-0042).

    python tools/train/value/train.py <agent> [--replays <dir> ...] [--holdout 0.2]

Mines labelled states from the replay corpus (default: ``data/replays/selfplay``), fits the pure-
Python logistic (`logistic.fit`), reports train/holdout log-loss + the fitted per-feature weights
(the legibility payoff — "race deficit dominates"), and writes
``src/common/value/value_model.json``. Build order general → matchup-conditioned → per-deck
(ADR-0007) is a future ``--conditioned`` split; v1 trains one general model.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def _build():
    sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]
    from train.tune import _build_pilot
    from train.value.extract import extract_dataset
    from train.value.logistic import fit, standardize, log_loss
    from common.value.features import FEATURE_NAMES
    from meta_tracker.parse import load_replay
    return _build_pilot, extract_dataset, fit, standardize, log_loss, FEATURE_NAMES, load_replay


def train(agent: str, replay_dirs, *, holdout: float = 0.2, out: Path | None = None) -> dict:
    """Mine → fit → write. Returns the model dict (also written to ``out``). Deterministic holdout
    split (every ``k``-th row, k from the ratio) so the generalization read is reproducible."""
    (_build_pilot, extract_dataset, fit, standardize, log_loss,
     FEATURE_NAMES, load_replay) = _build()
    pilot, _ = _build_pilot(agent)
    replays = []
    for d in replay_dirs:
        for p in sorted(Path(d).rglob("*.json")):
            try:
                replays.append(load_replay(p))
            except Exception:
                continue
    rows, labels = extract_dataset(pilot, replays)
    if len(rows) < 50:
        raise SystemExit(f"too few labelled states ({len(rows)}) — generate a larger corpus first")

    k = max(2, round(1 / holdout)) if holdout else 0
    tr_rows, tr_lab, ho_rows, ho_lab = [], [], [], []
    for idx, (r, y) in enumerate(zip(rows, labels)):
        if k and idx % k == 0:
            ho_rows.append(r); ho_lab.append(y)
        else:
            tr_rows.append(r); tr_lab.append(y)
    mean, std = standardize(tr_rows)
    weights = fit(tr_rows, tr_lab, mean=mean, std=std)
    model = {
        "features": list(FEATURE_NAMES),
        "weights": weights, "mean": mean, "std": std,
        "meta": {
            "agent": agent, "rows": len(rows), "positives": round(sum(labels) / len(labels), 3),
            "train_log_loss": round(log_loss(weights, tr_rows, tr_lab, mean, std), 4),
            "holdout_log_loss": (round(log_loss(weights, ho_rows, ho_lab, mean, std), 4)
                                 if ho_rows else None),
        },
    }
    out = out or (REPO / "src" / "common" / "value" / "value_model.json")
    out.write_text(json.dumps(model, indent=2), encoding="utf-8")
    return model


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Train the Automatic Value Model (ADR-0042).")
    ap.add_argument("agent", nargs="?", default="mega_starmie")
    ap.add_argument("--replays", nargs="*", default=[str(REPO / "data" / "replays" / "selfplay")])
    ap.add_argument("--holdout", type=float, default=0.2)
    args = ap.parse_args(argv)
    model = train(args.agent, args.replays, holdout=args.holdout)
    m = model["meta"]
    print(f"value model: {m['rows']} states, {m['positives']:.0%} wins, "
          f"train logloss {m['train_log_loss']}, holdout {m['holdout_log_loss']}")
    top = sorted(zip(model["features"], model["weights"]), key=lambda t: -abs(t[1]))[:6]
    print("top weights: " + ", ".join(f"{n}={w:+.2f}" for n, w in top))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
