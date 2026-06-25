"""Flag popular meta cards whose function tags look wrong/incomplete (double verification).

Ranks cards by real usage in the meta_tracker DB (Elite/High bands weighted), then cross-checks
the top-N against their rules **text** (function_audit) — surfacing the staples that decide games
where the probe tags disagree with the text. The motivating case: Munkidori ships as `status`,
but its Adrena-Brain ("move damage counters from your Pokémon to your opponent's") is heal+spread,
which the probe can't reach.

**Flag-only**: a review worklist, prioritised by how much each card actually shows up. Confirmed
corrections go in ``tools/meta_tracker/function_overrides.json`` *by hand* (the probe stays the
default; overrides are the curated escape hatch).

Usage:
    python tools/verify_meta_cards.py [--top 60] [--table PATH]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))                          # meta_tracker
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))   # cg (lazy)

from meta_tracker.cards import load_cards                  # noqa: E402
from meta_tracker.function_audit import audit_card         # noqa: E402
from meta_tracker.meta_usage import rank_card_usage        # noqa: E402
from meta_tracker.store import connect, load_episodes      # noqa: E402

DEFAULT_TABLE = (Path(__file__).resolve().parents[1]
                 / "src" / "common" / "card_functions.json")
_BAND_WEIGHTS = {"Elite": 3, "High": 2, "Mid": 1}   # weight the meta-defining tiers


def _card_texts() -> dict[int, tuple[str, str]]:
    """``{cardId: (name, text)}`` — every skill + attack text joined, from the engine."""
    from cg.api import all_attack, all_card_data
    atk = {a.attackId: (a.text or "") for a in all_attack()}
    out: dict[int, tuple[str, str]] = {}
    for c in all_card_data():
        parts = [s.text or "" for s in c.skills] + [atk.get(aid, "") for aid in c.attacks]
        out[c.cardId] = (c.name, " ".join(p for p in parts if p))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--top", type=int, default=120, help="verify the N most-played cards")
    ap.add_argument("--table", default=str(DEFAULT_TABLE))
    args = ap.parse_args()

    cards = load_cards()
    energy = {cid for cid, c in cards.items() if c.get("category") == "basic_energy"}
    episodes = load_episodes(connect())
    counts = rank_card_usage(episodes, band_weights=_BAND_WEIGHTS, exclude_ids=energy)
    table = {int(k): v for k, v in json.loads(Path(args.table).read_text(encoding="utf-8")).items()}
    texts = _card_texts()

    ranked = counts.most_common(args.top)
    flagged = []
    for rank, (cid, n) in enumerate(ranked, 1):
        name, text = texts.get(cid, (cards.get(cid, {}).get("name", str(cid)), ""))
        if not text:
            continue                              # a vanilla card has nothing to cross-check
        unsupported, missing = audit_card(table.get(cid, []), text)
        if unsupported or missing:
            flagged.append((rank, n, name, table.get(cid, []), missing, unsupported))

    print(f"Verified the top {len(ranked)} most-played cards across {len(episodes)} episodes. "
          f"Flagged {len(flagged)} for review:\n")
    for rank, n, name, tags, missing, unsupported in flagged:
        bits = []
        if missing:
            bits.append("MISSING " + "+".join(missing))
        if unsupported:
            bits.append("UNSUPPORTED " + "+".join(unsupported))
        print(f"  #{rank:<3} used {n:>5}  {name:<26} {str(tags):<34} -> {'; '.join(bits)}")
    print("\nFlag-only — review each; add confirmed fixes to "
          "tools/meta_tracker/function_overrides.json by hand.")


if __name__ == "__main__":
    main()
