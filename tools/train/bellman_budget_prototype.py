"""PROTOTYPE TUI for the Mega Starmie hard-budget corpus experiment.

Run: python tools/train/bellman_budget_prototype.py
Question: which 5/7/10/15-second hard budget retains the recent correction choices without allowing
root probing to pause or restart the decision clock?
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from train.bellman_corpus import sweep_corrections  # noqa: E402
from train.blunder.store import load_corrections  # noqa: E402


BUDGETS = (5.0, 7.0, 10.0, 15.0)


def recent_corrections():
    rows = []
    for store in sorted((REPO / "data" / "corrections").glob("mega_starmie_2026081*")):
        rows.extend(c for c in load_corrections(store) if c.agent == "mega_starmie")
    return rows


def run_budget(seconds: float, workers: int) -> dict:
    started = time.perf_counter()
    payload = sweep_corrections(recent_corrections(), workers=workers, max_seconds=seconds)
    return {
        "budget_seconds": seconds,
        "wall_seconds": time.perf_counter() - started,
        "records": payload["records"],
        "exact": payload["exact"],
        "agrees": payload["agrees"],
        "misses": payload["misses"],
        "decision_seconds": payload["decision_seconds"],
        "max_decision_seconds": payload["max_decision_seconds"],
        "rows": payload["rows"],
    }


def render(results: dict[float, dict]) -> None:
    print("\033[2J\033[H", end="")
    print("\033[1mMega Starmie hard-budget prototype\033[0m")
    print("\033[2mRecent Aug 11-13 correction corpus; fair root slices; one never-reset clock.\033[0m\n")
    print(f"\033[1mCorpus\033[0m  {len(recent_corrections())} corrections")
    for budget in BUDGETS:
        result = results.get(budget)
        if result is None:
            print(f"\033[1m{budget:g}s\033[0m  pending")
        else:
            print(f"\033[1m{budget:g}s\033[0m  agrees {result['agrees']}/{result['records']}  "
                  f"exact {result['exact']}  max {result['max_decision_seconds']:.2f}s  "
                  f"wall {result['wall_seconds']:.1f}s")
    print("\n\033[1m[5]\033[0m 5s  \033[1m[7]\033[0m 7s  \033[1m[0]\033[0m 10s  "
          "\033[1m[1]\033[0m 15s  \033[1m[a]\033[0m all  \033[1m[q]\033[0m quit")


def write_results(path: Path | None, results: dict[float, dict]) -> None:
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({str(k): v for k, v in results.items()}, indent=2) + "\n",
                        encoding="utf-8")


def run_all(workers: int, output: Path | None) -> int:
    results = {}
    for budget in BUDGETS:
        print(f"running {budget:g}s budget", flush=True)
        results[budget] = run_budget(budget, workers)
        write_results(output, results)
        row = results[budget]
        print(f"{budget:g}s: agrees={row['agrees']}/{row['records']} "
              f"exact={row['exact']} max={row['max_decision_seconds']:.2f}s "
              f"wall={row['wall_seconds']:.1f}s", flush=True)
    return 0


def interactive(workers: int, output: Path | None) -> int:
    results = {}
    keys = {"5": 5.0, "7": 7.0, "0": 10.0, "1": 15.0}
    while True:
        render(results)
        key = input("> ").strip().lower()
        if key == "q":
            return 0
        selected = BUDGETS if key == "a" else ((keys[key],) if key in keys else ())
        for budget in selected:
            results[budget] = run_budget(budget, workers)
            write_results(output, results)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    workers = max(1, args.workers)
    return run_all(workers, args.output) if args.all else interactive(workers, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
