"""Issue #305 — measure where a TRIGGERED Ability's effect is posed, and commit the evidence.

Drives `probe_cards.probe_triggered_ability` over one subject per trigger kind and writes the
observed select sequences to `tests/fixtures/triggered_ability_selects.json`. The shape test
re-drives the same probes against the live engine, so a build that moved the effect onto its own
`_ABILITY` option fails there rather than silently invalidating the apply-seam census.

Every recorded field is shuffle-invariant GIVEN A FULL SEARCH, and that clause is load-bearing: a
long drive can exhaust the searched pool, either partially (a short accept-mode search) or totally
(`deckCount == 0`, where the gate is never posed at all). Both were CI's ~1-in-2 flake here, and
`search_ceiling` retries on a fresh shuffle rather than shipping a board-dependent record.

Usage:
    python -m meta_tracker.probe_triggered_ability [--out PATH]"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from meta_tracker.cards import load_cards
from meta_tracker.probe_cards import probe_triggered_ability

_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = _ROOT / "tests" / "fixtures" / "triggered_ability_selects.json"

#: ``triggered-ability-selects/N`` — bumped when the RECORD's shape changes, so a stale fixture
#: fails on its schema rather than on a confusing field-by-field diff.
SCHEMA = "triggered-ability-selects/1"

#: One subject per trigger kind, both from shipped decks. EVERY key here except
#: ``search_ceiling`` is SERIALIZED into the fixture, so editing a ``why`` reddens the shape test.
SUBJECTS: tuple[dict, ...] = (
    {"card_id": 648, "trigger": "on_evolve", "ability": "Punk Up", "deck": "grimmsnarl_ex",
     "search_ceiling": 5,
     "why": "3 copies in a shipped deck, clauses already ruled `covers: full`, and its effect "
            "(attach up to 5 Basic {D} from deck) is loud enough to read straight off the selects"},
    {"card_id": 1071, "trigger": "on_play", "ability": "Last-Ditch Catch", "deck": "mega_starmie",
     "search_ceiling": None,
     "why": "3 copies in a shipped deck; the deploy trigger is measured separately from the evolve "
            "trigger rather than assumed to match it"},
)

#: Both modes are driven per subject. Declining is the STRONGER half: a clean decline with no
#: `_ABILITY` option on any later menu rules out one merely offered alongside the option.
MODES = ("accept", "decline")

#: The option each trigger kind rides — the ONE definition of that correspondence, which the test
#: bridges to `apply_seam_coverage.sites_for`'s `_PLAY` / `_EVOLVE` keying.
TRIGGER_OPTION = {"on_evolve": "EVOLVE", "on_play": "PLAY"}


def capture(cards: dict[int, dict] | None = None) -> dict:
    """Drive every subject in both modes and return the fixture payload. Shared by the CLI and the
    test, so the committed fixture and the live re-run cannot be built by two definitions."""
    cards = load_cards() if cards is None else cards
    subjects = []
    for spec in SUBJECTS:
        card = cards[spec["card_id"]]
        # `search_ceiling` is a DRIVE parameter (retry policy), not a fact the fixture records; folding
        # the whole spec into `row` would leak it into every subject's committed shape.
        meta = {k: v for k, v in spec.items() if k != "search_ceiling"}
        row = dict(meta, name=card.get("name"), stage=card.get("stage"))
        for mode in MODES:
            rec = probe_triggered_ability(spec["card_id"], cards, decline=(mode == "decline"),
                                          search_ceiling=spec["search_ceiling"])
            if rec is None:
                raise RuntimeError(
                    f"{row['name']} ({spec['card_id']}) never reached its "
                    f"{spec['trigger']} option — probe harness regression?")
            row[mode] = rec
        subjects.append(row)
    answer = "rider" if not any(s[m]["ability_option_seen"] for s in subjects for m in MODES) \
        else "own_ability_option"
    return {"schema": SCHEMA, "answer": answer, "subjects": subjects}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    payload = capture()
    # Binary write with explicit "\n": the repo is developed on Windows and this fixture is compared
    # byte-for-byte by the test, so `write_text` rewriting LF to CRLF would be a spurious diff.
    args.out.write_bytes((json.dumps(payload, indent=2) + "\n").encode("utf-8"))
    print(f"answer: {payload['answer']}  ->  {args.out}")
    for s in payload["subjects"]:
        for mode in MODES:
            r = s[mode]
            ctxs = [e["context"] for e in r["effect_selects"]]
            print(f"  {s['name']:<26} {mode:<8} {r['option_taken']:<7} "
                  f"gate ctx={r['gate_select']['context']} effect ctx={ctxs} "
                  f"ability_option_seen={r['ability_option_seen']}")
    return 0


if __name__ == "__main__":                                          # pragma: no cover - CLI
    raise SystemExit(main())
