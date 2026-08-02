"""**Issue #305** — measure where a TRIGGERED Ability's effect is posed, and commit the evidence.

An Ability reading *"When you play this Pokemon from your hand to evolve 1 of your Pokemon / onto
your Bench, you may…"* fires as part of playing that card. The apply-seam coverage census
(`tools/apply_seam_coverage.py`, Issue #269) assumes the engine resolves it **inside** the `_PLAY` /
`_EVOLVE` option, so those 11 pool sites are `_PLAY` / `_EVOLVE` sites and refuse at OPTION_SCOPE
when unmodelled. The alternative — the engine posing the Ability as its own `_ABILITY` option on a
later menu — would move all 11 to the one kind `apply_option.ENGINE_ROUTE_KINDS` already routes to
the engine, and would shrink Issue #299's scope before that ruling is made.

**No corpus frame settles it.** All 17 `_ABILITY` options observed across the 372-frame diagnostic
corpus are *activated* ("Once during your turn") — Drakloak's Recon Directive and Lunatone's Lunar
Cycle — and not one frame contains a triggered Ability. So the answer has to be measured against the
live engine, which is what this module does.

It drives `meta_tracker.probe_cards.probe_triggered_ability` over one subject per trigger kind and
writes the observed select sequences to `tests/fixtures/triggered_ability_selects.json`. Every field
it records is shuffle-invariant (measured: 80/80 identical runs), so
`tests/strategy/test_triggered_ability_shape.py` re-drives the same probes and asserts the live
engine still matches — a future engine build that moved the effect onto its own option fails there
rather than silently invalidating the census.

Usage:
    python -m meta_tracker.probe_triggered_ability [--out PATH]
"""
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

#: One subject per trigger kind, both from shipped decks so the measurement is about cards we
#: actually play. Assuming the two triggers behave alike is the same class of assumption this
#: module exists to remove, so both are driven rather than one.
SUBJECTS: tuple[dict, ...] = (
    {"card_id": 648, "trigger": "on_evolve", "ability": "Punk Up", "deck": "grimmsnarl_ex",
     "why": "3 copies in a shipped deck, clauses already ruled `covers: full`, and its effect "
            "(attach up to 5 Basic {D} from deck) is loud enough to read straight off the selects"},
    {"card_id": 1071, "trigger": "on_play", "ability": "Last-Ditch Catch", "deck": "mega_starmie",
     "why": "3 copies in a shipped deck; the deploy trigger is measured separately from the evolve "
            "trigger rather than assumed to match it"},
)

#: Both modes are driven per subject. Declining is the STRONGER half of the question: an Ability the
#: engine merely *offered* alongside the option would still be offered after the rider was refused,
#: so a clean decline with no `_ABILITY` option on any later menu rules that out.
MODES = ("accept", "decline")


def capture(cards: dict[int, dict] | None = None) -> dict:
    """Drive every subject in both modes and return the fixture payload.

    Shared by the CLI and by the test, so the committed fixture and the live re-run can never be
    built by two different definitions of the measurement.
    """
    cards = load_cards() if cards is None else cards
    subjects = []
    for spec in SUBJECTS:
        card = cards[spec["card_id"]]
        row = dict(spec, name=card.get("name"), stage=card.get("stage"))
        for mode in MODES:
            rec = probe_triggered_ability(spec["card_id"], cards, decline=(mode == "decline"))
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
