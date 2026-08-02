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
writes the observed select sequences to `tests/fixtures/triggered_ability_selects.json`, so
`tests/strategy/test_triggered_ability_shape.py` re-drives the same probes and asserts the live
engine still matches — a future engine build that moved the effect onto its own option fails there
rather than silently invalidating the census.

⚠️ **This docstring used to claim every recorded field is shuffle-invariant, "measured: 80/80
identical runs". That was false**, and 80/80 was luck rather than evidence: a deck-searching trigger
is skipped outright when the draw leaves its target unreachable, which records `effect_selects: []`
— the draw's shape, not the card's. CI's determinism backstop caught it on repeat 3 of 15, and it
reproduces at ~1 in 20 locally. Shuffle-invariance is now something the harness ENFORCES rather than
asserts: `build_trigger_deck` stocks 4 Supporter lines so exhaustion is out of the mulligan tail's
reach, and `_accept_is_measurable` refuses to record a whiff as a measurement at all.

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
     "searches_deck": True,
     "why": "3 copies in a shipped deck, clauses already ruled `covers: full`, and its effect "
            "(attach up to 5 Basic {D} from deck) is loud enough to read straight off the selects"},
    {"card_id": 1071, "trigger": "on_play", "ability": "Last-Ditch Catch", "deck": "mega_starmie",
     "searches_deck": True,
     "why": "3 copies in a shipped deck; the deploy trigger is measured separately from the evolve "
            "trigger rather than assumed to match it"},
)

#: How many fresh games a subject may be re-driven when its ACCEPT branch comes back with no effect
#: selects at all. See `_accept_is_measurable`.
_MAX_REDRAWS = 8

#: `SUBJECTS` keys that steer the HARNESS rather than describe the measurement — stripped before the
#: row reaches the fixture, so a knob can be added without churning the committed artifact.
_HARNESS_KEYS = frozenset({"searches_deck"})

#: Both modes are driven per subject. Declining is the STRONGER half of the question: an Ability the
#: engine merely *offered* alongside the option would still be offered after the rider was refused,
#: so a clean decline with no `_ABILITY` option on any later menu rules that out.
MODES = ("accept", "decline")

#: The option each trigger kind rides — the ONE definition of that correspondence. The census keys
#: the same fact by `_PLAY` / `_EVOLVE` (`apply_seam_coverage.sites_for`); the test bridges the two
#: through this map rather than re-spelling the `on_evolve -> EVOLVE` cascade at each site.
TRIGGER_OPTION = {"on_evolve": "EVOLVE", "on_play": "PLAY"}


def _accept_is_measurable(spec: dict, rec: dict) -> bool:
    """Did this ACCEPT run actually observe the effect, or did its search whiff on the draw?

    A deck-searching trigger is **skipped outright by the engine when the deck holds no target** —
    Meowth ex's Last-Ditch Catch searches for a Supporter, Punk Up for Basic {D}. When that happens
    the run records ``effect_selects: []``, which is not the card's shape, it is the draw's. It looks
    identical to a real measurement and the fixture comparison then fails on a coin flip
    (`test_triggered_ability_shape.py`, CI's determinism backstop, repeat 3 of 15).

    ``ability_option_seen`` is what keeps this from being tautological. If the engine ever DID move
    the effect onto its own `_ABILITY` option, accept would come back with no effect selects **and**
    that bit set — a real answer change, which must fail loudly rather than be re-rolled. So only the
    both-empty case (no selects, no Ability option: nothing observed at all) counts as a whiff."""
    return (not spec.get("searches_deck")
            or bool(rec["effect_selects"])
            or bool(rec["ability_option_seen"]))


def _drive(spec: dict, cards: dict[int, dict], mode: str, name: str) -> dict:
    """One subject in one mode, re-drawing while the ACCEPT branch whiffs on its deck search.

    Re-driving re-rolls the SHUFFLE, never the answer: the property under measurement (does the
    effect ride the option it was played by) is shuffle-invariant *given* that the search has a
    target, and `_accept_is_measurable` is exactly the check that the precondition held. Bounded,
    and it raises rather than returning an unmeasured record — a probe that silently emits "I saw
    nothing" as a measurement is how a fixture ends up encoding the draw."""
    last = None
    for _ in range(_MAX_REDRAWS if mode == "accept" else 1):
        last = probe_triggered_ability(spec["card_id"], cards, decline=(mode == "decline"))
        if last is None:
            raise RuntimeError(f"{name} ({spec['card_id']}) never reached its "
                               f"{spec['trigger']} option — probe harness regression?")
        if mode != "accept" or _accept_is_measurable(spec, last):
            return last
    raise RuntimeError(
        f"{name} ({spec['card_id']}) accepted its {spec['trigger']} trigger but observed NOTHING "
        f"in {_MAX_REDRAWS} fresh games — no effect selects and no Ability option. Its deck search "
        f"is finding no target, so the probe deck is mis-built (see `build_trigger_deck`); this is "
        f"a harness fault, not a measurement.")


def capture(cards: dict[int, dict] | None = None) -> dict:
    """Drive every subject in both modes and return the fixture payload.

    Shared by the CLI and by the test, so the committed fixture and the live re-run can never be
    built by two different definitions of the measurement.
    """
    cards = load_cards() if cards is None else cards
    subjects = []
    for spec in SUBJECTS:
        card = cards[spec["card_id"]]
        # HARNESS keys never reach the artifact: the fixture records what the ENGINE did, and a knob
        # that only steers how the probe drives it is not a measurement. Keeping `searches_deck` out
        # is why adding it did not churn a byte of `triggered_ability_selects.json` — verified by
        # diffing a live capture against the committed file, which came back identical.
        row = {k: v for k, v in spec.items() if k not in _HARNESS_KEYS}
        row.update(name=card.get("name"), stage=card.get("stage"))
        for mode in MODES:
            rec = _drive(spec, cards, mode, row["name"])
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
