"""Record a blunder Correction as **reviewed** so blunder-busting won't re-surface it.

    python tools/train/review_correction.py <episode>-<frame> <disposition> "<reason>"
    python tools/train/review_correction.py --list
    python tools/train/review_correction.py --remove <episode>-<frame>

``disposition`` is one of: refuted (a bad correction — e.g. it forgoes a Knock Out; also dropped
from the weight fit), deferred (an evidenced capability-gap ONLY — the fix is a designed-but-unbuilt
roadmap layer, with a fixture + docs/todo definition-of-done; a missing signal is built, not
deferred), covered (already handled by an existing rule). Edits ``data/corrections/reviewed.json``
in place, preserving the ``_note`` and existing entries. See ``tools/train/blunder/reviewed.py``.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools")]

from train.blunder.reviewed import DEFAULT_REVIEWED, DISPOSITIONS  # noqa: E402


def _load_raw(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")          # reasons carry em-dashes -> cp1252 would crash
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="Record a Correction as reviewed (exclude from blunder-busting)")
    ap.add_argument("key", nargs="?", help="correction id: '<episode_id>-<frame>'")
    ap.add_argument("disposition", nargs="?", choices=DISPOSITIONS, help="refuted | deferred | covered")
    ap.add_argument("reason", nargs="?", default="", help="one-line why")
    ap.add_argument("--round", default=date.today().isoformat(), help="round/date tag (default: today)")
    ap.add_argument("--list", action="store_true", help="print the ledger and exit")
    ap.add_argument("--remove", metavar="KEY", help="delete an entry (un-review a correction)")
    ap.add_argument("--path", default=str(DEFAULT_REVIEWED))
    args = ap.parse_args(argv)
    path = Path(args.path)
    data = _load_raw(path)

    if args.list:
        for k, v in data.items():
            if not k.startswith("_"):
                print(f"{k:>16}  {v.get('disposition', '?'):8}  {v.get('reason', '')}")
        return 0

    if args.remove:
        if data.pop(args.remove, None) is None:
            print(f"no ledger entry for {args.remove}")
            return 1
        _save(path, data)
        print(f"removed {args.remove}")
        return 0

    if not (args.key and args.disposition):
        ap.error("provide '<episode>-<frame> <disposition> [reason]', or --list / --remove")
    data[args.key] = {"disposition": args.disposition, "reason": args.reason, "round": args.round}
    _save(path, data)
    print(f"recorded {args.key} [{args.disposition}] -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
