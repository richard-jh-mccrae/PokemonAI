"""The Ledger's training loop: nudge general coefficients, keep the best, adopt clean gains.

The plan's §7 method (nudge / keep-best-so-far / adoption gate), re-pointed at the Ledger's
Valuation Configuration. Each candidate is a full corpus sweep through the live brain; a candidate is
adopted only when the generality floor (worst deck, never the average) does not drop, total
agreement rises, and NO frame that agreed under the best-so-far vector flips to a miss — the
zero-regressions half of the plan's done bar, enforced per nudge. Greedy passes repeat until
a full pass adopts nothing. The adopted values are printed and reported; committing them
means editing the Feature Catalog defaults.

    python tools/train/ledger_tune.py --lever zone.in_hand=0.55,0.75
        --lever combat.attack_now=0.30,0.40 [--decks ...] [--workers N]
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from common.ledger import ValuationConfiguration  # noqa: E402
from train.ledger_corpus import DECKS, sweep  # noqa: E402

DEFAULT_REPORT_DIR = REPO / "docs" / "tuning" / "runs"


def _agree_sets(result: dict) -> tuple[dict, set]:
    per_deck: dict[str, int] = {}
    agreed: set[tuple[str, str]] = set()             # (deck, id): ids only bind within a deck
    for row in result["rows"]:
        if row["graded"] and row["agrees"]:
            per_deck[row["deck"]] = per_deck.get(row["deck"], 0) + 1
            agreed.add((row["deck"], row["id"]))
    return per_deck, agreed


def _score(result: dict) -> tuple[float, int]:
    floor = result["generality_floor"] or 0.0
    return floor, sum(1 for row in result["rows"] if row["graded"] and row["agrees"])


def _fmt(overrides: dict) -> str:
    return ", ".join(f"{key}={value}" for key, value in sorted(overrides.items())) or "(none)"


def run(*, levers: dict[str, list[float]], store, decks=DECKS, workers: int = 1,
        max_passes: int = 4, log=print) -> dict:
    """Greedy coordinate nudging. Returns {"adopted": overrides, "baseline": …, "best": …,
    "trials": […]} — every trial is recorded, adopted or not, so the report is the audit."""
    ValuationConfiguration.general().with_values(
        {name: values[0] for name, values in levers.items()})
    baseline = sweep(store=store, decks=decks, workers=workers)
    best, best_score = baseline, _score(baseline)
    _, best_agreed = _agree_sets(baseline)
    adopted: dict[str, float] = {}
    trials: list[dict] = []
    log(f"baseline floor {best_score[0]:.4f} agrees {best_score[1]}")

    for tuning_pass in range(1, max_passes + 1):
        improved = False
        for lever, values in levers.items():
            for value in values:
                if adopted.get(lever) == value:
                    continue
                candidate = {**adopted, lever: value}
                result = sweep(store=store, decks=decks, workers=workers,
                               weight_overrides=candidate)
                score = _score(result)
                _, agreed = _agree_sets(result)
                regressions = sorted(best_agreed - agreed)
                verdict = "rejected"
                # The gate: strictly better on (floor, total) AND nothing already-right lost.
                if not regressions and score > best_score:
                    best, best_score, best_agreed = result, score, agreed
                    adopted = candidate
                    verdict = "ADOPTED"
                    improved = True
                trials.append({"pass": tuning_pass, "lever": lever, "value": value,
                               "floor": score[0], "agrees": score[1],
                               "regressions": len(regressions), "verdict": verdict})
                log(f"[pass {tuning_pass}] {lever}={value}: floor {score[0]:.4f} "
                    f"agrees {score[1]} regressions {len(regressions)} -> {verdict}")
        if not improved:
            break
    return {"adopted": adopted, "baseline": baseline, "best": best, "trials": trials}


def render_report(outcome: dict, levers: dict) -> str:
    base_floor, base_agrees = _score(outcome["baseline"])
    best_floor, best_agrees = _score(outcome["best"])
    _, base_set = _agree_sets(outcome["baseline"])
    _, best_set = _agree_sets(outcome["best"])
    fixed = sorted(f"{deck}:{row_id}" for deck, row_id in best_set - base_set)
    lines = [
        "# Ledger tuning round",
        "",
        f"Ran {datetime.now(timezone.utc).isoformat()} over levers: "
        f"{', '.join(sorted(levers))}.",
        "",
        f"- baseline: floor {base_floor:.4f}, agrees {base_agrees}",
        f"- best:     floor {best_floor:.4f}, agrees {best_agrees}",
        f"- adopted:  {_fmt(outcome['adopted'])}",
        f"- frames fixed ({len(fixed)}): " + (", ".join(f"`{f}`" for f in fixed) or "-"),
        "",
        "Adoption means editing the Feature Catalog defaults to the adopted values.",
        "Zero-regression gate enforced per nudge.",
        "",
        "| pass | lever | value | floor | agrees | regressions | verdict |",
        "|---|---|---|---|---|---|---|",
    ]
    lines += [f"| {t['pass']} | {t['lever']} | {t['value']} | {t['floor']:.4f} | "
              f"{t['agrees']} | {t['regressions']} | {t['verdict']} |"
              for t in outcome["trials"]]
    return "\n".join(lines) + "\n"


def _parse_lever(text: str) -> tuple[str, list[float]]:
    name, _, values = text.partition("=")
    if not values:
        raise argparse.ArgumentTypeError(f"lever {text!r} needs =v1[,v2,...]")
    return name.strip(), [float(value) for value in values.split(",")]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lever", type=_parse_lever, action="append", required=True,
                        metavar="NAME=V1[,V2,...]",
                        help="candidate values for one weight (dotted tier keys allowed)")
    parser.add_argument("--store", default=str(REPO / "data" / "corrections"))
    parser.add_argument("--decks", nargs="+", default=list(DECKS))
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--max-passes", type=int, default=4)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    levers = dict(args.lever)
    outcome = run(levers=levers, store=args.store, decks=tuple(args.decks),
                  workers=max(1, args.workers), max_passes=args.max_passes)
    report = args.report or (DEFAULT_REPORT_DIR
                             / f"ledger_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.md")
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(render_report(outcome, levers), encoding="utf-8", newline="\n")
    print(f"adopted: {_fmt(outcome['adopted'])}")
    print(f"report: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
