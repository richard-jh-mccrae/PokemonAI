"""Record a blunder Correction as **reviewed** so blunder-busting won't re-surface it.

    python tools/train/review_correction.py <locator> <disposition> "<reason>"
    python tools/train/review_correction.py --list
    python tools/train/review_correction.py --remove <locator>

``disposition`` is one of: refuted (a bad correction; also dropped from the weight fit), deferred
(an evidenced capability-gap ONLY — a missing signal is built, not deferred), covered (already
handled by an existing rule). Edits ``data/corrections/reviewed.json`` in place, preserving the
``_note`` and existing entries.

**A locator is RESOLVED against the corpus, never taken as the key** (ADR-0090, Issue #250): any of
the four spellings `reviewed.resolve_locator` accepts is fine, the *canonical* key is written, and a
locator matching no committed Correction is REFUSED non-zero with near-miss candidates.
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


#: Shared by the positional and by ``--remove``, so the two cannot document different vocabularies.
_LOCATOR_HELP = ("how to find the Correction — any of: its ledger key ('86091435-t14s0'), its "
                 "Frame Key ('86091435|0|turn|14'), its Correction id ('948537a24fb2'), or the "
                 "Anchor form the reports print ('86091435-119'). Resolved to the canonical "
                 "ledger key before anything is written.")


def _resolve_or_report(locator: str, store, *, quiet: bool = False) -> str | None:
    """``quiet`` is for ``--remove``, which has a ledger-key fallback and must not announce a failure
    it is about to recover from. The corpus loads HERE, so `--list` never pays for it."""
    from train.gates import keyed_corrections

    keyed = keyed_corrections(store)
    key = resolve_locator(locator, keyed)
    if key is not None or quiet:
        return key

    print(f"no committed Correction matches {locator!r} — nothing written.")
    suggestions = near_misses(locator, keyed)
    if suggestions:
        print("  did you mean:  " + "  ".join(suggestions))
    else:
        print("  no near-miss found; `--list` shows the ledger, and the reports print ledger keys.")
    return None


def _save(path: Path, data: dict) -> None:
    """Framed with the line ending the file ALREADY uses (a new one gets LF): the ledger is CRLF, and
    `Path.write_text` frames per the writing platform, so a four-entry edit rewrites the whole file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    newline = b"\r\n" if path.exists() and b"\r\n" in path.read_bytes() else b"\n"
    body = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    path.write_bytes(body.encode("utf-8").replace(b"\n", newline))


def _replacement_refused(existing: dict, new_disposition: str, *, supersede: bool) -> bool:
    from train.gates import voiding_disposition

    return (voiding_disposition(existing.get("disposition"))
            and not voiding_disposition(new_disposition)
            and not supersede)


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")          # reasons carry em-dashes -> cp1252 would crash
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="Record a Correction as reviewed (exclude from blunder-busting)")
    ap.add_argument("locator", nargs="?", help=_LOCATOR_HELP)
    ap.add_argument("disposition", nargs="?", choices=DISPOSITIONS, help="refuted | deferred | covered")
    ap.add_argument("reason", nargs="?", default="", help="one-line why")
    ap.add_argument("--round", default=date.today().isoformat(), help="round/date tag (default: today)")
    ap.add_argument("--list", action="store_true", help="print the ledger and exit")
    ap.add_argument("--remove", metavar="LOCATOR", help=f"delete an entry (un-review). {_LOCATOR_HELP}")
    ap.add_argument("--supersede", action="store_true",
                    help="allow replacing a voiding disposition with a non-voiding one; reason required")
    ap.add_argument("--path", default=str(DEFAULT_REVIEWED))
    ap.add_argument("--store", default=str(DEFAULT_ROOT),
                    help="corrections corpus root a locator resolves against (default: the committed one)")
    args = ap.parse_args(argv)
    path = Path(args.path)
    data = _load_raw(path)

    # BEFORE the corpus load: `--list` is the audit surface for the file itself, so it must stay
    # instant and must not need a corpus to exist.
    if args.list:
        for k, v in data.items():
            if not k.startswith("_"):
                print(f"{k:>16}  {v.get('disposition', '?'):8}  {v.get('reason', '')}")
        return 0

    locator = args.remove or args.locator
    if not locator or not (args.remove or args.disposition):
        ap.error("provide '<locator> <disposition> [reason]', or --list / --remove")
    if args.supersede and args.remove:
        ap.error("--supersede only applies when recording a disposition")
    if args.supersede and not args.reason.strip():
        ap.error("--supersede requires a non-empty reason")

    if args.remove:
        # The ledger's own keys are a necessary fallback: an ORPHAN entry resolves to no Correction
        # by definition, so corpus-only resolution makes the entry that most needs deleting undeletable.
        key = _resolve_or_report(locator, args.store, quiet=True) or locator
        if data.pop(key, None) is None:
            print(f"no ledger entry for {key}"
                  + ("" if key == locator else f" (resolved from {locator!r})"))
            return 1
        _save(path, data)
        print(f"removed {key}")
        return 0

    # RECORDING, by contrast, admits no fallback: accepting a key the corpus cannot reach is the
    # free-text writer this build exists to remove, orphan-in-place "corrections" included.
    key = _resolve_or_report(locator, args.store)
    if key is None:
        return 1

    existing = data.get(key)
    if existing is not None:
        print(f"replacing {key} [{existing.get('disposition', '?')}] from round "
              f"{existing.get('round', '?')}")
        if _replacement_refused(existing, args.disposition, supersede=args.supersede):
            print(f"refusing to replace voiding disposition {existing.get('disposition')!r} with "
                  f"non-voiding disposition {args.disposition!r}; pass --supersede with a reason "
                  f"to override. Nothing written.")
            return 1

    data[key] = {"disposition": args.disposition, "reason": args.reason, "round": args.round}
    _save(path, data)
    print(f"recorded {key} [{args.disposition}] -> {path}"
          + ("" if key == locator else f"   (resolved from {locator!r})"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
