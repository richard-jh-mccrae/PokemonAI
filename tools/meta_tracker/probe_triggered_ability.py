"""**Issue #305** — measure where a TRIGGERED Ability's effect is posed, and commit the evidence.

An Ability reading *"When you play this Pokemon from your hand to evolve 1 of your Pokemon / onto
your Bench, you may…"* fires as part of playing that card. The apply-seam coverage census
(`tools/apply_seam_coverage.py`, Issue #269) assumes the engine resolves it **inside** the `_PLAY` /
`_EVOLVE` option, so those 11 pool sites are `_PLAY` / `_EVOLVE` sites and refuse at OPTION_SCOPE
when unmodelled. The alternative — the engine posing the Ability as its own `_ABILITY` option on a
later menu — would have moved all 11 to the one kind `apply_option.ENGINE_ROUTE_KINDS` then routed to
the engine, and would have shrunk Issue #299's scope before that ruling was made. (Issue #299 has
since ruled that the engine route is open per-option to every declared non-terminal kind, so
`ENGINE_ROUTE_KINDS` no longer gates; what this probe measures still decides which OPTION the census
files these sites under.)

**No corpus frame settles it.** All 17 `_ABILITY` options observed across the 372-frame diagnostic
corpus are *activated* ("Once during your turn") — Drakloak's Recon Directive and Lunatone's Lunar
Cycle — and not one frame contains a triggered Ability. So the answer has to be measured against the
live engine, which is what this module does.

It drives `meta_tracker.probe_cards.probe_triggered_ability` over one subject per trigger kind and
writes the observed select sequences to `tests/fixtures/triggered_ability_selects.json`. Every field
it records is shuffle-invariant GIVEN a full search — measured 80/80 identical runs at the time this
module was written — so `tests/strategy/test_triggered_ability_shape.py` re-drives the same probes
and asserts the live engine still matches — a future engine build that moved the effect onto its own
option fails there rather than silently invalidating the census.

**"Given a full search" is load-bearing.** Both subjects' triggers search a bounded pool this probe
deck stocks with `_TRIGGER_SUPPORTERS` distinct lines, and 6 face-down prize cards draw from that
same pool invisibly. Nothing bounds how many turns pass before the target enters play, so a long
enough drive can draw the pool down first, at TWO distinct boundaries (Issue #322 follow-up):

* **Partial** — the gate is posed normally, but an accepted search finds fewer than its own
  ceiling. Measured: the search comes up short roughly HALF the time once the drive's own deck
  count falls under 10, against ~0.2% otherwise.
* **Total** (`deckCount == 0`) — the trigger's *"you may…"* gate is never posed at all; the engine
  fizzles straight through to the next MAIN menu rather than offering a choice with nothing to
  find. This one breaks BOTH modes, since there is no y/n to accept or decline, and it is what the
  first attempt at this fix missed: a decline-mode capture on the very next CI run after that fix
  landed, at `deckCount == 0` — a boundary the partial-shortage check could not see, since it never
  runs for decline mode at all. Caught by re-measuring rather than trusting the first fix's local
  pass, which is why the retry now checks BOTH.

Together they are CI's ~1-in-2-runs flake on this file.

**Not shared process state.** The obvious first suspect for a flake that survives 39 other
live-engine tests run the same way was engine/RNG state leaking BETWEEN repeats in one process —
checked and ruled out: the divergence reproduces identically in a single fresh process running one
capture at a time, and correlates cleanly with THIS game's own deck count, not with position in a
repeat sequence. It is per-game board state that this harness under-controls, not cross-game
contamination.

`probe_triggered_ability`'s `search_ceiling` (set per subject below) retries on a fresh shuffle
when a capture came up short — partially (accept mode) or totally (either mode) — of the trigger's
own printed bound, rather than shipping a board-dependent record. The SUCCESSFUL shape recorded is
byte-identical to what a full search always produced, so the committed fixture needed no change.
The same idiom `audit_attacks.py` uses for a missed setup or bench target.

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
#:
#: ``search_ceiling`` is each trigger's OWN printed search bound, passed to
#: ``probe_cards.probe_triggered_ability`` so an accept-mode capture that came up short from a
#: shuffle-dependent deck shortage — not the card's own shape — retries rather than shipping a
#: board-dependent record (see ``probe_cards._accept_capture_is_exhausted``). Punk Up's "up to 5"
#: caps its own ``max_count``; Last-Ditch Catch finds exactly one, so ``None`` means "the select
#: must be posed at all".
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

#: Both modes are driven per subject. Declining is the STRONGER half of the question: an Ability the
#: engine merely *offered* alongside the option would still be offered after the rider was refused,
#: so a clean decline with no `_ABILITY` option on any later menu rules that out.
MODES = ("accept", "decline")

#: The option each trigger kind rides — the ONE definition of that correspondence. The census keys
#: the same fact by `_PLAY` / `_EVOLVE` (`apply_seam_coverage.sites_for`); the test bridges the two
#: through this map rather than re-spelling the `on_evolve -> EVOLVE` cascade at each site.
TRIGGER_OPTION = {"on_evolve": "EVOLVE", "on_play": "PLAY"}


def capture(cards: dict[int, dict] | None = None) -> dict:
    """Drive every subject in both modes and return the fixture payload.

    Shared by the CLI and by the test, so the committed fixture and the live re-run can never be
    built by two different definitions of the measurement.
    """
    cards = load_cards() if cards is None else cards
    subjects = []
    for spec in SUBJECTS:
        card = cards[spec["card_id"]]
        # `search_ceiling` is a DRIVE parameter (retry policy), not a fact the fixture records —
        # folding the whole spec into `row` would leak it into every subject's committed shape
        # (schema/index and every reader of the fixture would gain a field it never had).
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
