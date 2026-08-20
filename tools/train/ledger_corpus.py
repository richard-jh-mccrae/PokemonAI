"""The Ledger's training dashboard: every correction frame, every deck, one sweep.

Replays each human-ruled frame through the LIVE runtime (the Ledger brain) with the offline
cgpy provider and reports, per deck: agreement with the ruling, every miss WITH ITS RATIONALE
beside the Ledger's own price list (the rationale is context — some old rulings deserve a
second look, not a weight nudge), a coverage-gap census counted per affected decision, and —
against a prior baseline file — the frames that used to agree and no longer do. Frames with no
`correct` ruling assert nothing and are counted `ungraded`, never as misses. A sweep is only
sound within one deck (a frame replayed through another decklist is off-policy), so frames are
grouped by their recording agent throughout. Honesty rules (ADR-0147): frames archived without
the live shell's `own_prizes` anchor get one stamped before replay, and rulings dispositioned
in `reviewed.json` are RETIRED — listed in their own section, never graded.

    python tools/train/ledger_corpus.py [--decks mega_starmie ...] [--workers N]
        [--baseline docs/plans/ledger-corpus-dashboard.json] [--limit N]
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from common.option_equivalence import class_of, option_equivalence  # noqa: E402
from common.engine import CgpyTransitionProvider, stamp_own_prizes  # noqa: E402 - offline replay only
from common.runtime import build_runtime  # noqa: E402
from train.blunder.store import load_corrections  # noqa: E402
from train.blunder.decode import option_label  # noqa: E402
from train.blunder.reviewed import load_reviewed, partition_reviewed  # noqa: E402


DECKS = ("mega_starmie", "mega_lucario", "dragapult_ex")
DEFAULT_OUTPUT = REPO / "docs" / "plans" / "ledger-corpus-dashboard.json"


def _build_runtime(deck_name: str, weight_overrides=None):
    agent_dir = REPO / "src" / "agents" / deck_name
    spec = importlib.util.spec_from_file_location("_ledger_corpus_strategy",
                                                  agent_dir / "strategy.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    deck = [int(value) for value in (agent_dir / "deck.csv").read_text().splitlines()
            if value.strip()]
    ledger_weights = None
    if weight_overrides:
        from common.ledger import LedgerWeights

        ledger_weights = LedgerWeights().resolve(weight_overrides)
    return build_runtime(module.STRATEGY, deck, provider_factory=CgpyTransitionProvider,
                         ledger_weights=ledger_weights)


def _satisfies_one(chosen, correct, equivalence) -> bool:
    if chosen is None or correct is None:
        return False
    if not correct:
        return not chosen
    picked = frozenset(chosen)
    return all(bool(class_of(equivalence, wanted) & picked) for wanted in correct)


def _satisfies_human(chosen, correction, equivalence) -> bool:
    """The primary ruling OR any recorded equally-acceptable alternative satisfies."""
    rulings = [list(correction.correct or ())]
    rulings += [list(alt or ()) for alt in (correction.correct_alternatives or ())]
    return any(_satisfies_one(chosen, ruling, equivalence) for ruling in rulings)


def _labels(obs, indices) -> str:
    select = obs.get("select") or {}
    options = select.get("option") or []
    current = obs.get("current") or {}
    return ", ".join(option_label(options[index], current, select=select)
                     for index in indices or () if 0 <= index < len(options))


def _replay_one(deck_name: str, correction, weight_overrides=None) -> dict:
    """One frame through a fresh runtime: isolation, matching the live shell exactly —
    including the own-prize anchor the live shell stamps before every decide."""
    runtime = _build_runtime(deck_name, weight_overrides)
    obs = correction.obs
    stamped = stamp_own_prizes(obs, runtime.deck)
    started = time.perf_counter()
    decision = runtime.decide(obs)
    elapsed = time.perf_counter() - started
    chosen = list(decision.chosen)
    correct = list(correction.correct or ())
    graded = bool(correction.correct) or correction.correct == []
    equivalence = option_equivalence(((obs.get("select") or {}).get("option") or []), obs)
    agrees = _satisfies_human(chosen, correction, equivalence) if graded else None
    diagnostics = decision.diagnostics or {}
    row = {
        "deck": deck_name,
        "key": f"{correction.episode_id}-{(correction.decision or {}).get('frame', -1)}",
        "id": correction.id,
        # Not always "ledger": a shell fallback (exception, forced selection) names itself
        # here, so brainless answers stay visible in the dashboard instead of hiding as misses.
        "backend": diagnostics.get("backend"),
        "scope": correction.scope,
        "context": (correction.decision or {}).get("select_context"),
        "category": correction.category,
        "graded": graded,
        "chosen": chosen,
        "correct": correct,
        "exact": bool(graded and chosen == correct),
        "agrees": agrees,
        "chosen_label": _labels(obs, chosen),
        "correct_label": _labels(obs, correct),
        "rationale": correction.rationale,
        "gaps": sorted(set(diagnostics.get("gaps", ()))),
        "stamped_prizes": stamped,
        "elapsed_seconds": elapsed,
    }
    if diagnostics.get("fallback"):                # a crashed brain must be visible, not a miss
        row["fallback"] = diagnostics["fallback"]
    if graded and not agrees:
        row["ledger"] = {"value": decision.value, "backend": diagnostics.get("backend"),
                         "weights": diagnostics.get("weights"),
                         "prices": list(diagnostics.get("prices", ()))[:5]}
    return row


def _deck_summary(rows: list[dict]) -> dict:
    graded = [row for row in rows if row["graded"]]
    agrees = sum(1 for row in graded if row["agrees"])
    gap_census: Counter = Counter()
    for row in rows:
        for gap in set(row["gaps"]):
            gap_census[gap] += 1                    # decisions affected, never mentions
    return {
        "records": len(rows),
        "graded": len(graded),
        "agrees": agrees,
        "misses": len(graded) - agrees,
        "agreement": round(agrees / len(graded), 4) if graded else None,
        "ungraded": len(rows) - len(graded),
        "decision_seconds": round(sum(row["elapsed_seconds"] for row in rows), 2),
        "gap_decisions": sum(1 for row in rows if row["gaps"]),
        "gap_census": dict(gap_census.most_common()),
        # A crashed brain that happened to pick the ruled action is NOT a success.
        "fallbacks": sum(1 for row in rows if row.get("fallback")),
    }


def payload(rows: list[dict], *, retired: list[dict] | None = None,
            baseline: dict | None = None) -> dict:
    rows.sort(key=lambda row: (row["deck"], row["key"], row["id"]))
    retired = sorted(retired or (), key=lambda row: (row["deck"], row["key"]))
    decks = {}
    for deck_name in sorted({row["deck"] for row in rows}
                            | {row["deck"] for row in retired}):
        decks[deck_name] = _deck_summary([row for row in rows if row["deck"] == deck_name])
        decks[deck_name]["retired"] = sum(1 for row in retired if row["deck"] == deck_name)
    agreements = [summary["agreement"] for summary in decks.values()
                  if summary["agreement"] is not None]
    regressions = []
    if baseline is not None:
        held = {(row["deck"], row["id"]) for row in baseline.get("rows", ())
                if row.get("agrees")}
        regressions = [row["id"] for row in rows
                       if (row["deck"], row["id"]) in held and row["agrees"] is False]
    return {
        "schema": 1,
        "git_rev": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO,
                                           text=True).strip(),
        # An empty regressions list only means something beside the baseline it was measured
        # against; None here says "never compared", not "zero regressions".
        "baseline_git_rev": (baseline or {}).get("git_rev"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "decks": decks,
        # The generality bar: the GENERAL weights must clear every deck, so the headline is
        # the worst deck, never the average.
        "generality_floor": min(agreements) if agreements else None,
        "regressions": regressions,
        "retired": retired,
        "rows": rows,
    }


def render_markdown(result: dict) -> str:
    lines = ["# Ledger corpus dashboard", "",
             f"Generated {result['generated_at']} at `{result['git_rev'][:12]}`.", ""]
    lines.append("| deck | graded | agrees | agreement | ungraded | retired | "
                 "gap-affected decisions | fallbacks |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for deck_name, summary in result["decks"].items():
        agreement = ("-" if summary["agreement"] is None
                     else f"{summary['agreement'] * 100:.1f}%")
        lines.append(f"| {deck_name} | {summary['graded']} | {summary['agrees']} | "
                     f"{agreement} | {summary['ungraded']} | {summary.get('retired', 0)} | "
                     f"{summary['gap_decisions']} | {summary.get('fallbacks', 0)} |")
    floor = result["generality_floor"]
    lines += ["", f"**Generality floor (worst deck): "
                  f"{'-' if floor is None else f'{floor * 100:.1f}%'}**", ""]
    if result["regressions"]:
        lines += [f"## Regressions ({len(result['regressions'])})", ""]
        lines += [f"- `{row_id}`" for row_id in result["regressions"]] + [""]
    if result.get("retired"):
        lines += [f"## Retired rulings ({len(result['retired'])}) — dispositioned in "
                  "reviewed.json, not graded", ""]
        lines += [f"- {row['deck']} `{row['key']}`: {row['disposition']}"
                  + (f" ({row['round']})" if row.get("round") else "")
                  for row in result["retired"]] + [""]
    crashed = [row for row in result["rows"] if row.get("fallback")]
    if crashed:
        lines += [f"## Crashed decisions ({len(crashed)}) — fix the bug, ignore the grade", ""]
        for row in crashed:
            error = (row["fallback"].get("error") or {})
            lines.append(f"- {row['deck']} `{row['key']}`: {row['fallback'].get('cause')}"
                         + (f" — {error.get('type')}: {error.get('message')}"
                            if error else ""))
        lines.append("")
    lines += ["## Misses (the triage queue: read the rationale first)", ""]
    for row in result["rows"]:
        if not row["graded"] or row["agrees"]:
            continue
        lines += [f"### {row['deck']} `{row['key']}` ({row['context']}, {row['category']})",
                  "",
                  f"- Ledger chose `{row['chosen']}` {row['chosen_label']}",
                  f"- ruling was `{row['correct']}` {row['correct_label']}",
                  f"- rationale: {row['rationale']}"]
        for price in (row.get("ledger") or {}).get("prices", ())[:3]:
            lines.append(f"- priced {price['swing']:+.4f} {price['action']}")
        lines.append("")
    return "\n".join(lines)


def _retired_row(correction, entry) -> dict:
    return {"deck": correction.agent,
            "key": f"{correction.episode_id}-{(correction.decision or {}).get('frame', -1)}",
            "id": correction.id,
            "disposition": entry.get("disposition"),
            "round": entry.get("round")}


def sweep(*, store, decks=DECKS, limit=None, workers: int = 1,
          baseline: dict | None = None, reviewed: dict | None = None,
          weight_overrides: dict | None = None) -> dict:
    swept = [correction for correction in load_corrections(store)
             if correction.agent in decks and correction.obs is not None]
    # A ruling the owner already dispositioned (refuted, fixed, covered…) is retired: grading
    # it would score the brain against a verdict that no longer stands (the ADR-0082 drift).
    active, dispositioned = partition_reviewed(
        swept, load_reviewed() if reviewed is None else reviewed)
    retired = [_retired_row(correction, entry) for correction, entry in dispositioned]
    tasks = [(correction.agent, correction) for correction in active]
    tasks.sort(key=lambda pair: (pair[0], pair[1].id))
    if limit is not None:
        tasks = tasks[:limit]
    rows = []
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_replay_one, deck_name, correction, weight_overrides)
                       for deck_name, correction in tasks]
            for completed, future in enumerate(as_completed(futures), start=1):
                rows.append(future.result())
                print(f"[{completed}/{len(tasks)}]", flush=True)
    else:
        for completed, (deck_name, correction) in enumerate(tasks, start=1):
            rows.append(_replay_one(deck_name, correction, weight_overrides))
            print(f"[{completed}/{len(tasks)}] {deck_name} {correction.id}", flush=True)
    return payload(rows, retired=retired, baseline=baseline)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", default=str(REPO / "data" / "corrections"))
    parser.add_argument("--decks", nargs="+", default=list(DECKS))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args(argv)
    baseline = (json.loads(args.baseline.read_text(encoding="utf-8"))
                if args.baseline and args.baseline.exists() else None)
    result = sweep(store=args.store, decks=tuple(args.decks), limit=args.limit,
                   workers=max(1, args.workers), baseline=baseline)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                           encoding="utf-8")
    args.output.with_suffix(".md").write_text(render_markdown(result) + "\n",
                                              encoding="utf-8")
    floor = result["generality_floor"]
    print(f"generality floor {floor} | regressions {len(result['regressions'])} "
          f"| written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
