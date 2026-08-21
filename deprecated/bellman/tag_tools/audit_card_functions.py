"""Audit the shipped card-function table against card text (see meta_tracker/function_audit.py).

An *independent* oracle: the tags come from probing, never from text, so cross-checking each tag
against the card's attack/skill text flags likely mistakes for review —

  * UNSUPPORTED — a behavioral tag with no supporting text cue (suspect false positive);
  * MISSING     — a strong, unambiguous text cue with no matching tag (suspect probe miss).

Lib-using (reads engine text via `cg`). Heuristic, not a gate — text is noisy (that's why we
probe), so a flag means "inspect", not "wrong".

Usage:
    python tools/audit_card_functions.py [--table PATH] [--show 15]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "src"))

from meta_tracker.function_audit import audit_card  # noqa: E402

DEFAULT_TABLE = Path(__file__).resolve().parent / "measured_functions.json"


def _card_texts() -> dict[int, tuple[str, str]]:
    """``{cardId: (name, text)}`` — every skill + attack text joined, from the engine."""
    from cg.api import all_attack, all_card_data
    atk = {a.attackId: (a.text or "") for a in all_attack()}
    out: dict[int, tuple[str, str]] = {}
    for c in all_card_data():
        parts = [s.text or "" for s in c.skills] + [atk.get(aid, "") for aid in c.attacks]
        out[c.cardId] = (c.name, " ".join(p for p in parts if p))
    return out


def _report(title: str, found: dict[str, list[str]], show: int) -> None:
    total = sum(len(v) for v in found.values())
    print(f"\n=== {title}: {total} flags ===")
    for tag, names in sorted(found.items(), key=lambda kv: -len(kv[1])):
        ex = ", ".join(sorted(set(names))[:show])
        print(f"  {tag:<16} {len(names):>4}  e.g. {ex}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--table", default=str(DEFAULT_TABLE))
    ap.add_argument("--show", type=int, default=15, help="examples to list per tag")
    args = ap.parse_args()

    table = {int(k): v for k, v in json.loads(Path(args.table).read_text(encoding="utf-8")).items()}
    texts = _card_texts()

    unsupported: dict[str, list[str]] = defaultdict(list)
    missing: dict[str, list[str]] = defaultdict(list)
    n_text = 0
    for cid, (name, text) in texts.items():
        if not text.strip():
            continue                       # vanilla card (no rules text) -> nothing to cross-check
        n_text += 1
        u, m = audit_card(table.get(cid, []), text)
        for tag in u:
            unsupported[tag].append(name)
        for tag in m:
            missing[tag].append(name)

    _report("UNSUPPORTED (tag present, no text cue -> maybe false positive)", unsupported, args.show)
    _report("MISSING (strong text cue, no tag -> maybe probe miss)", missing, args.show)
    print(f"\naudited {n_text} cards-with-text against {len(table)} tagged cards.")


if __name__ == "__main__":
    main()
