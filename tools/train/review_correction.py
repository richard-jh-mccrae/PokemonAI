"""Record a blunder Correction as **reviewed** so blunder-busting won't re-surface it.

    python tools/train/review_correction.py <locator> <disposition> "<reason>"
    python tools/train/review_correction.py --list
    python tools/train/review_correction.py --remove <locator>

``disposition`` is one of: refuted (a bad correction — e.g. it forgoes a Knock Out; also dropped
from the weight fit), deferred (an evidenced capability-gap ONLY — the fix is a designed-but-unbuilt
roadmap layer, with a fixture + docs/todo definition-of-done; a missing signal is built, not
deferred), covered (already handled by an existing rule). Edits ``data/corrections/reviewed.json``
in place, preserving the ``_note`` and existing entries. See ``tools/train/blunder/reviewed.py``.

**A locator is RESOLVED against the corpus, never taken as the key** (ADR-TEMP-250, Issue #250).
Give it any of the four spellings `reviewed.resolve_locator` accepts — the canonical `review_key`,
the **Frame Key**, the ``Correction.id``, or the Anchor form the reports print — and the *canonical*
key is what gets written. A locator matching no committed Correction is REFUSED, non-zero, with
near-miss candidates; nothing is written.

That guard exists because this tool used to take the key as free text and check it against nothing,
which put two human rulings into the ledger ruling on **nothing**: `85046350-10` (wrong episode —
the record is ep 85045840 f10) and `86091435-119` (wrong key shape — the record is turn-scoped, so
its key is `86091435-t14s0`). The second was copied verbatim off a report that printed the Anchor
frame for every scope; that report now prints the ledger key, so the two surfaces agree.
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
from train.blunder.reviewed import near_misses, resolve_locator  # noqa: E402
from train.blunder.store import DEFAULT_ROOT  # noqa: E402


def _load_raw(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _resolve(locator: str, store) -> str | None:
    """The canonical ledger key ``locator`` names, or None — printing the refusal on the way out.

    The corpus is loaded HERE rather than at import, so `--list` never pays for it, and it is loaded
    through `gates.keyed_corrections` — THE Corpus Reader (ADR-0087 decision 1) — so this tool can
    never become the thirteenth thing with its own idea of what a record is.
    """
    from train.gates import keyed_corrections

    keyed = keyed_corrections(store)
    key = resolve_locator(locator, keyed)
    if key is not None:
        return key

    print(f"no committed Correction matches {locator!r} — nothing written.")
    suggestions = near_misses(locator, keyed)
    if suggestions:
        print("  did you mean:  " + "  ".join(suggestions))
    else:
        print("  no near-miss found; `--list` shows the ledger, and the reports print ledger keys.")
    return None


def _save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")          # reasons carry em-dashes -> cp1252 would crash
    except (AttributeError, ValueError):
        pass
    _LOCATOR_HELP = ("how to find the Correction — any of: its ledger key ('86091435-t14s0'), its "
                     "Frame Key ('86091435|0|turn|14'), its Correction id ('948537a24fb2'), or the "
                     "Anchor form the reports print ('86091435-119'). Resolved to the canonical "
                     "ledger key before anything is written.")
    ap = argparse.ArgumentParser(description="Record a Correction as reviewed (exclude from blunder-busting)")
    ap.add_argument("locator", nargs="?", help=_LOCATOR_HELP)
    ap.add_argument("disposition", nargs="?", choices=DISPOSITIONS, help="refuted | deferred | covered")
    ap.add_argument("reason", nargs="?", default="", help="one-line why")
    ap.add_argument("--round", default=date.today().isoformat(), help="round/date tag (default: today)")
    ap.add_argument("--list", action="store_true", help="print the ledger and exit")
    ap.add_argument("--remove", metavar="LOCATOR", help=f"delete an entry (un-review). {_LOCATOR_HELP}")
    ap.add_argument("--path", default=str(DEFAULT_REVIEWED))
    ap.add_argument("--store", default=str(DEFAULT_ROOT),
                    help="corrections corpus root a locator resolves against (default: the committed one)")
    args = ap.parse_args(argv)
    path = Path(args.path)
    data = _load_raw(path)

    # BEFORE the corpus load: `--list` prints the ledger's literal contents and is the audit surface
    # for the file itself, so it must stay instant and must not need a corpus to exist.
    if args.list:
        for k, v in data.items():
            if not k.startswith("_"):
                print(f"{k:>16}  {v.get('disposition', '?'):8}  {v.get('reason', '')}")
        return 0

    locator = args.remove or args.locator
    if not locator or not (args.remove or args.disposition):
        ap.error("provide '<locator> <disposition> [reason]', or --list / --remove")

    key = _resolve(locator, args.store)
    if key is None:
        return 1

    if args.remove:
        if data.pop(key, None) is None:
            print(f"no ledger entry for {key}"
                  + ("" if key == locator else f" (resolved from {locator!r})"))
            return 1
        _save(path, data)
        print(f"removed {key}")
        return 0

    data[key] = {"disposition": args.disposition, "reason": args.reason, "round": args.round}
    _save(path, data)
    print(f"recorded {key} [{args.disposition}] -> {path}"
          + ("" if key == locator else f"   (resolved from {locator!r})"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
