"""Unfiltered Mega Starmie correction sweep for Bellman development.

This reader never consults ``reviewed.json`` to exclude a record.  It preserves every rationale and
reports exact/equivalent agreement separately, so later M8 adjudication can treat prose as the primary
human ruling without erasing historical labels.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
import importlib
import json
from pathlib import Path
import subprocess
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from common.option_equivalence import option_equivalence  # noqa: E402
from train.blunder.store import load_corrections  # noqa: E402
from train.gates import satisfies_human  # noqa: E402
from train.tuner.retest import retest  # noqa: E402


DEFAULT_OUTPUT = REPO / "docs" / "plans" / "mega-starmie-live-corpus-baseline.json"


def _build_pilot():
    return importlib.import_module("train.tune")._build_pilot("mega_starmie")[0]


def _frame(correction) -> int:
    return int((correction.decision or {}).get("frame", -1))


def _episode(correction) -> int:
    return -1 if correction.episode_id is None else int(correction.episode_id)


def _sweep_episode(corrections) -> list[dict]:
    pilot = _build_pilot()
    rows = []
    for c in corrections:
        result = retest(c, pilot)
        obs = c.obs or {}
        equivalence = option_equivalence(((obs.get("select") or {}).get("option") or []), obs)
        chosen = result["chosen_after"]
        exact = chosen == list(c.correct or ())
        agrees = satisfies_human(chosen, list(c.correct or ()), equiv=equivalence)
        rows.append({
            "episode": _episode(c),
            "frame": _frame(c),
            "scope": c.scope,
            "context": (c.decision or {}).get("select_context"),
            "category": c.category,
            "chosen": chosen,
            "correct": list(c.correct or ()),
            "exact": bool(exact),
            "agrees": bool(agrees),
            "chosen_label": c.chosen_label,
            "correct_label": c.correct_label,
            "rationale": c.rationale,
        })
    return rows


def sweep(*, store, limit: int | None = None, workers: int = 1) -> dict:
    corrections = [c for c in load_corrections(store) if c.agent == "mega_starmie"]
    corrections.sort(key=lambda c: (_episode(c), _frame(c), c.id))
    if limit is not None:
        corrections = corrections[:limit]
    groups = []
    for correction in corrections:
        if not groups or groups[-1][0].episode_id != correction.episode_id:
            groups.append([])
        groups[-1].append(correction)
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            rows = [row for batch in pool.map(_sweep_episode, groups) for row in batch]
    else:
        rows = [row for group in groups for row in _sweep_episode(group)]

    contexts = Counter(str(row["context"]) for row in rows)
    return {
        "schema": 1,
        "deck": "mega_starmie",
        "git_rev": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO,
                                            text=True).strip(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "excluded": 0,
        "records": len(rows),
        "exact": sum(row["exact"] for row in rows),
        "agrees": sum(row["agrees"] for row in rows),
        "misses": sum(not row["agrees"] for row in rows),
        "contexts": dict(sorted(contexts.items())),
        "rows": rows,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", default=str(REPO / "data" / "corrections"))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args(argv)
    payload = sweep(store=args.store, limit=args.limit, workers=max(1, args.workers))
    rendered = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if args.limit is None:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
