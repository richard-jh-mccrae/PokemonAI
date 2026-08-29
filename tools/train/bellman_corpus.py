"""Unfiltered per-deck correction sweep for Bellman development.

This reader never consults ``reviewed.json`` to exclude a record.  It preserves every rationale and
reports exact/equivalent agreement separately, so later M8 adjudication can treat prose as the primary
human ruling without erasing historical labels.

``--deck`` selects which agent's corrections are swept and which ``src/agents/<deck>`` declarations
replay them.  A sweep is only sound within one deck: a correction replayed through another deck's
decklist is off-policy, so the deck name filters the store and names the baseline file together.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import replace
from datetime import datetime, timezone
import importlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO), str(REPO / "tools"), str(REPO / "src")]

from common.option_equivalence import option_equivalence  # noqa: E402
from common.engine import CgpyTransitionProvider  # noqa: E402 - offline diagnostic only
from deprecated.bellman.planner import DEFAULT_PRODUCTION_LIMITS  # noqa: E402
from deprecated.bellman import build_teacher_runtime  # noqa: E402
from deprecated.bellman.telemetry import to_record  # noqa: E402
from train.blunder.store import load_corrections  # noqa: E402
from train.blunder.decode import option_label  # noqa: E402


DEFAULT_DECK = "mega_starmie"


def default_output(deck: str) -> Path:
    return REPO / "docs" / "plans" / f"{deck.replace('_', '-')}-live-corpus-baseline.json"


DEFAULT_OUTPUT = default_output(DEFAULT_DECK)


def _build_runtime(max_seconds: float | None = None, deck_name: str = DEFAULT_DECK):
    agent_dir = REPO / "src" / "agents" / deck_name
    spec = importlib.util.spec_from_file_location("_bellman_corpus_strategy",
                                                  agent_dir / "strategy.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    deck = [int(value) for value in (agent_dir / "deck.csv").read_text().splitlines()
            if value.strip()]
    # The correction corpus contains historical observation fixtures.  Replay them only with the
    # offline cgpy diagnostic provider; the shipped Kaggle runtime always uses native cg.
    limits = (None if max_seconds is None else
              replace(DEFAULT_PRODUCTION_LIMITS, max_seconds=float(max_seconds)))
    return build_teacher_runtime(module.STRATEGY, deck, provider_factory=CgpyTransitionProvider,
                         limits=limits)


def _satisfies_human(chosen, correct, equivalence) -> bool:
    if chosen is None or correct is None:
        return False
    if not correct:
        return not chosen
    from common.option_equivalence import selection_covers_equivalently
    return selection_covers_equivalently(chosen, correct, equivalence)


def _retest(correction, runtime) -> dict:
    if correction.obs is None:
        return {"after": None, "chosen_after": None}
    started = time.perf_counter()
    decision = runtime.decide(correction.obs)
    elapsed = time.perf_counter() - started
    after = to_record(decision, opponent=runtime.opponent_snapshot)
    return {"after": after, "chosen_after": after["chosen"], "elapsed_seconds": elapsed}


def _frame(correction) -> int:
    return int((correction.decision or {}).get("frame", -1))


def _episode(correction) -> int:
    return -1 if correction.episode_id is None else int(correction.episode_id)


def _sweep_episode(corrections, max_seconds: float | None = None,
                   deck_name: str = DEFAULT_DECK) -> list[dict]:
    runtime = _build_runtime(max_seconds, deck_name)
    rows = []
    for c in corrections:
        result = _retest(c, runtime)
        obs = c.obs or {}
        equivalence = option_equivalence(((obs.get("select") or {}).get("option") or []), obs)
        chosen = result["chosen_after"]
        exact = chosen == list(c.correct or ())
        agrees = _satisfies_human(chosen, list(c.correct or ()), equivalence)
        select = obs.get("select") or {}
        options = select.get("option") or []
        current = obs.get("current") or {}
        labels = [option_label(options[index], current, select=select)
                  for index in chosen if 0 <= index < len(options)]
        correct_labels = [option_label(options[index], current, select=select)
                          for index in c.correct if 0 <= index < len(options)]
        row = {
            "episode": _episode(c),
            "frame": _frame(c),
            "scope": c.scope,
            "context": (c.decision or {}).get("select_context"),
            "category": c.category,
            "chosen": chosen,
            "correct": list(c.correct or ()),
            "exact": bool(exact),
            "agrees": bool(agrees),
            "chosen_label": ", ".join(labels),
            "correct_label": ", ".join(correct_labels),
            "rationale": c.rationale,
            "elapsed_seconds": result.get("elapsed_seconds", 0.0),
        }
        if not agrees:
            after = result.get("after") or {}
            diagnostics = after.get("diagnostics") or {}
            row["bellman"] = {
                "action": after.get("action"),
                "value": after.get("value"),
                "complete": after.get("complete"),
                "diagnostics": diagnostics,
            }
        rows.append(row)
    return rows


def _payload(rows: list[dict], deck_name: str = DEFAULT_DECK) -> dict:
    rows.sort(key=lambda row: (row["episode"], row["frame"]))
    contexts = Counter(str(row["context"]) for row in rows)
    return {
        "schema": 2,
        "deck": deck_name,
        "git_rev": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO,
                                            text=True).strip(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "excluded": 0,
        "records": len(rows),
        "exact": sum(row["exact"] for row in rows),
        "agrees": sum(row["agrees"] for row in rows),
        "misses": sum(not row["agrees"] for row in rows),
        "decision_seconds": sum(row.get("elapsed_seconds", 0.0) for row in rows),
        "max_decision_seconds": max((row.get("elapsed_seconds", 0.0) for row in rows), default=0.0),
        "contexts": dict(sorted(contexts.items())),
        "rows": rows,
    }


def _write_payload(path: Path, rows: list[dict], deck_name: str = DEFAULT_DECK) -> None:
    temporary = path.with_suffix(path.suffix + ".partial")
    rendered = json.dumps(_payload(list(rows), deck_name), indent=2, ensure_ascii=False) + "\n"
    temporary.write_text(rendered, encoding="utf-8")
    for attempt in range(20):
        try:
            temporary.replace(path)
            break
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.05 * (attempt + 1))


def sweep_corrections(corrections, *, workers: int = 1,
                      checkpoint: Path | None = None,
                      max_seconds: float | None = None,
                      deck: str = DEFAULT_DECK) -> dict:
    corrections = [c for c in corrections if c.agent == deck]
    corrections.sort(key=lambda c: (_episode(c), _frame(c), c.id))
    # One frame per task prevents a hard episode from retaining native search graphs for every
    # later correction assigned to the same worker. It is isolation, never corpus filtering.
    groups = [[correction] for correction in corrections]
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_sweep_episode, group, max_seconds, deck): group[0]
                       for group in groups}
            rows = []
            for completed, future in enumerate(as_completed(futures), start=1):
                rows.extend(future.result())
                if checkpoint is not None:
                    _write_payload(checkpoint, rows, deck)
                correction = futures[future]
                print(f"[{completed}/{len(groups)}] {_episode(correction)}-{_frame(correction)}",
                      flush=True)
    else:
        rows = []
        for completed, group in enumerate(groups, start=1):
            rows.extend(_sweep_episode(group, max_seconds, deck))
            if checkpoint is not None:
                _write_payload(checkpoint, rows, deck)
            print(f"[{completed}/{len(groups)}] {_episode(group[0])}-{_frame(group[0])}", flush=True)

    return _payload(rows, deck)


def sweep(*, store, limit: int | None = None, workers: int = 1,
          checkpoint: Path | None = None, max_seconds: float | None = None,
          deck: str = DEFAULT_DECK) -> dict:
    corrections = [c for c in load_corrections(store) if c.agent == deck]
    if limit is not None:
        corrections = corrections[:limit]
    return sweep_corrections(corrections, workers=workers, checkpoint=checkpoint,
                             max_seconds=max_seconds, deck=deck)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", default=str(REPO / "data" / "corrections"))
    parser.add_argument("--deck", default=DEFAULT_DECK)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--max-seconds", type=float)
    args = parser.parse_args(argv)
    if args.output is None:
        args.output = default_output(args.deck)
    checkpoint = args.output if args.limit is None else None
    payload = sweep(store=args.store, limit=args.limit, workers=max(1, args.workers),
                    checkpoint=checkpoint, max_seconds=args.max_seconds, deck=args.deck)
    rendered = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if args.limit is None:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        # Option labels carry card-text glyphs (arrows, accents) that a cp1252 console cannot
        # encode; write the bytes rather than let `print` pick the console codec.
        sys.stdout.buffer.write(rendered.encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
