"""Unfiltered Mega Starmie correction sweep for Bellman development.

This reader never consults ``reviewed.json`` to exclude a record.  It preserves every rationale and
reports exact/equivalent agreement separately, so later M8 adjudication can treat prose as the primary
human ruling without erasing historical labels.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
import importlib
import json
from pathlib import Path
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from common.option_equivalence import option_equivalence  # noqa: E402
from train.blunder.store import load_corrections  # noqa: E402
from train.blunder.decode import option_label  # noqa: E402
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
        }
        if not agrees:
            composer = (result.get("after") or {}).get("composer") or {}
            production = composer.get("production") or {}
            row["bellman"] = {
                "action": composer.get("action"),
                "value": composer.get("value"),
                "complete": composer.get("complete"),
                "ledger": composer.get("ledger"),
                "root_previews": production.get("root_previews"),
                "previewed": production.get("previewed"),
                "pruned": production.get("pruned"),
                "preview_caps": production.get("preview_caps"),
                "cap_reached": production.get("cap_reached"),
            }
        rows.append(row)
    return rows


def _payload(rows: list[dict]) -> dict:
    rows.sort(key=lambda row: (row["episode"], row["frame"]))
    contexts = Counter(str(row["context"]) for row in rows)
    return {
        "schema": 2,
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


def _write_payload(path: Path, rows: list[dict]) -> None:
    temporary = path.with_suffix(path.suffix + ".partial")
    rendered = json.dumps(_payload(list(rows)), indent=2, ensure_ascii=False) + "\n"
    temporary.write_text(rendered, encoding="utf-8")
    for attempt in range(20):
        try:
            temporary.replace(path)
            break
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.05 * (attempt + 1))


def sweep(*, store, limit: int | None = None, workers: int = 1,
          checkpoint: Path | None = None) -> dict:
    corrections = [c for c in load_corrections(store) if c.agent == "mega_starmie"]
    corrections.sort(key=lambda c: (_episode(c), _frame(c), c.id))
    if limit is not None:
        corrections = corrections[:limit]
    # One frame per task prevents a hard episode from retaining native search graphs for every
    # later correction assigned to the same worker. It is isolation, never corpus filtering.
    groups = [[correction] for correction in corrections]
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_sweep_episode, group): group[0] for group in groups}
            rows = []
            for completed, future in enumerate(as_completed(futures), start=1):
                rows.extend(future.result())
                if checkpoint is not None:
                    _write_payload(checkpoint, rows)
                correction = futures[future]
                print(f"[{completed}/{len(groups)}] {_episode(correction)}-{_frame(correction)}",
                      flush=True)
    else:
        rows = []
        for completed, group in enumerate(groups, start=1):
            rows.extend(_sweep_episode(group))
            if checkpoint is not None:
                _write_payload(checkpoint, rows)
            print(f"[{completed}/{len(groups)}] {_episode(group[0])}-{_frame(group[0])}", flush=True)

    return _payload(rows)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", default=str(REPO / "data" / "corrections"))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args(argv)
    checkpoint = args.output if args.limit is None else None
    payload = sweep(store=args.store, limit=args.limit, workers=max(1, args.workers),
                    checkpoint=checkpoint)
    rendered = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if args.limit is None:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
