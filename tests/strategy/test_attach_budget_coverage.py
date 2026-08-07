"""The Attach Budget's COVERAGE GATE (Issue #137 / ADR-0067).

An accel card with no Effect-Clause row contributes zero SILENTLY; this gate makes every such zero
audited. Pure data (decklists x Function Tags x Effect Clauses) — no engine, no Pilot.
"""
import csv
import json
from pathlib import Path

import pytest

from common import snapshot_coverage
from common.strategy.combat import _ACCEL_TAGS

_ROOT = Path(__file__).resolve().parents[2]
_AGENTS = _ROOT / "src" / "agents"

# Accel valued at ZERO deliberately. Each entry is a ruling — re-verify at source before removing one.
KNOWN_UNMODELLED = {
    666: "Cinderace — its acceleration is the ATTACK Turbo Flare; attacking ends the turn, so it "
         "can never fund another attack this turn (the self-side mirror of ADR-0064's "
         "attack-based-accel exclusion). Permanently zero, not a gap.",
}

# Accel where ZERO is WRONG and the modelling is OWED. Separate from `KNOWN_UNMODELLED` ("zero is
# correct") on purpose: folding a real gap into that list would be a lie the gate then enforces.
SELF_SIDE_OWED = {
    648: "Marnie's Grimmsnarl ex — [Ability] Punk Up attaches up to 5 Basic {D} from the deck when "
         "the card is played from HAND TO EVOLVE (verified, data/EN_Card_Data.csv), and it does NOT "
         "end the turn, so Cinderace's ruling above does not cover it: this is a self-side accel the "
         "Budget cannot see, which is the f70 false-famine class. NO LONGER SHIPPED — PR #436 deleted "
         "`grimmsnarl_ex` (2026-08-06), the only deck that ran it, so the gap is latent rather than "
         "live; the entry stays because the gap is in the BUDGET, not in that decklist, and the audit "
         "above scans the card data rather than the decks. "
         "SURFACED by POC-T1 (Issue #260), which tagged the card for the OPPONENT-facing Threat "
         "Clock (Issue #257) — `card_functions.json` had no entry for 648 at all, so the gap existed "
         "and this gate could not see it. Closing it is ISSUE #137's charter, not #260's: "
         "`attach_budget` would have to admit an Evolution POKEMON in hand and take a board fact it "
         "is not given today (is a legal evolve base in play, and is the turn's evolve still "
         "available?). Owner: Issue #137 follow-up, filed in POC-T1's wave-2 packet.",
}

# The vocabulary CombatMath's clause interpreter models. Anything outside these sets is silently
# zeroed at runtime (every gate word fails CLOSED), so it must NOT count as coverage.
_ATTACHES = ("accel",)
_HAND_YIELD_TARGETS = ("basic_energy", "energy")
_TARGETS = (None, "any_pokemon", "stage2", "benched")
_SOURCES = ("deck", "discard")
_CONDITIONS = (None, "more_prizes_remaining_than_opp")


def _tags() -> dict:
    raw = json.loads((_ROOT / "src" / "common" / "card_functions.json").read_text(encoding="utf-8"))
    return {int(k): set(v) for k, v in raw.items()}


def _clauses() -> dict:
    raw = json.loads((_ROOT / "src" / "common" / "card_effects.json").read_text(encoding="utf-8"))
    # Shared parse, not a local `int(k)` walk: the compendium carries a non-numeric `_covers` key.
    return snapshot_coverage.clause_lists(raw)


def _special_energy_ids() -> set:
    """From the CSV type column, not `CardStat.is_special_energy` — this gate boots no engine."""
    path = _ROOT / "data" / "EN_Card_Data.csv"
    rows = csv.DictReader(path.read_text(encoding="utf-8").splitlines())
    return {int(r["Card ID"]) for r in rows
            if "Special Energy" in (r["Stage (Pok\u00e9mon)/Type (Energy and Trainer)"] or "")}


def _deck_ids(deck_csv: Path) -> set:
    ids = set()
    for row in csv.reader(deck_csv.read_text(encoding="utf-8").splitlines()):
        ids.update(int(cell.strip()) for cell in row if cell.strip().isdigit())
    return ids


def _accel_readable(cl) -> bool:
    """A quantity AND every gate word in the modelled vocabulary."""
    return (cl.get("kind") in _ATTACHES
            and bool(cl.get("amount") or cl.get("to_hand"))
            and cl.get("target") in _TARGETS
            and cl.get("source") in _SOURCES
            and cl.get("condition") in _CONDITIONS)


def _budget_readable(clauses) -> bool:
    """Does any clause give the Budget a unit — an attach, or an Energy put into hand?"""
    return any(
        _accel_readable(cl)
        or (cl.get("kind") == "fetch" and cl.get("zone") == "deck"
            and cl.get("target") in _HAND_YIELD_TARGETS)
        for cl in clauses)


def _shipped_decks():
    return sorted(p for p in _AGENTS.glob("*/deck.csv") if (p.parent / "main.py").exists())


def test_there_are_shipped_agent_decks_to_audit():
    assert _shipped_decks(), "no shipped agent decks found — the coverage gate would be vacuous"


@pytest.mark.parametrize("deck_csv", _shipped_decks(), ids=lambda p: p.parent.name)
def test_every_accel_card_in_a_shipped_deck_is_modelled_or_explicitly_ruled_zero(deck_csv):
    tags, clauses = _tags(), _clauses()
    gaps = [cid for cid in sorted(_deck_ids(deck_csv))
            if (tags.get(cid, set()) & _ACCEL_TAGS)
            and cid not in KNOWN_UNMODELLED and cid not in SELF_SIDE_OWED
            and not _budget_readable(clauses.get(cid, ()))]
    assert not gaps, (
        f"{deck_csv.parent.name}: accel-tagged cards with no Budget-readable Effect Clause: {gaps}. "
        "Author the clause in tools/meta_tracker/effect_overrides.json (verify the card text at "
        "source first), add it to KNOWN_UNMODELLED with the ruling that makes zero correct, or — "
        "when zero is WRONG and the fix belongs to another track — to SELF_SIDE_OWED with its owner.")


def test_an_owed_entry_names_its_owner_and_is_not_quietly_modelled():
    clauses = _clauses()
    for cid, owner in SELF_SIDE_OWED.items():
        assert "Issue #" in owner and len(owner) > 80, f"{cid}: an owed entry must name its owner"
        assert not _budget_readable(clauses.get(cid, ())), (
            f"{cid} is now Budget-readable — remove it from SELF_SIDE_OWED")


@pytest.mark.parametrize("deck_csv", _shipped_decks(), ids=lambda p: p.parent.name)
def test_every_special_energy_in_a_shipped_deck_carries_its_provision(deck_csv):
    """A Special Energy is not one unit of its own colour (Ignition provides {C}{C}{C} on an Evolution),
    so the provision is a `provides:N` tag in function_overrides.json; the COLOUR is CardStat.energyType."""
    tags = _tags()
    special = _special_energy_ids()
    gaps = sorted(cid for cid in _deck_ids(deck_csv) if cid in special
                  and not any(str(t).startswith("provides:") for t in tags.get(cid, ())))
    assert not gaps, (
        f"{deck_csv.parent.name}: Special Energy with no `provides:N` tag: {gaps}. Read the card's "
        "'it provides …' line at data/EN_Card_Data.csv and add the tag to "
        "tools/meta_tracker/function_overrides.json — untagged, the Attach Budget prices it at zero.")


def test_the_special_energy_audit_has_something_to_audit():
    assert _special_energy_ids(), "no Special Energy found in the card data — the audit is vacuous"


def test_the_known_unmodelled_list_stays_honest():
    clauses = _clauses()
    stale = [cid for cid in KNOWN_UNMODELLED if _budget_readable(clauses.get(cid, ()))]
    assert not stale, f"now Budget-readable — drop from KNOWN_UNMODELLED: {stale}"


def test_the_f70_enabler_carries_its_full_two_unit_yield():
    """Crispin (1198): 'up to 2 Basic Energy cards of different types … put 1 into your hand. Attach
    the other.' Both halves must be in the shipped row."""
    crispin = _clauses().get(1198, ())
    accel = [cl for cl in crispin if cl.get("kind") == "accel"]
    assert accel, "Crispin lost its accel clause"
    assert accel[0].get("amount") == 1, "the ATTACH half"
    assert accel[0].get("to_hand") == 1, "the put-1-into-your-hand half — the f70 fix"
    assert accel[0].get("distinct_types") is True, "'of different types' — the same-colour guard"


def test_the_gate_rejects_a_clause_written_in_unmodelled_vocabulary():
    """A row can carry a quantity and still be worth zero at runtime — unknown gate words fail CLOSED."""
    assert _budget_readable([{"kind": "accel", "amount": 1, "source": "deck",
                              "target": "any_pokemon"}])
    for unmodelled in ({"target": "in_play_ex"},
                       {"source": "hand"},
                       {"condition": "opponent_has_stadium"}):
        row = {"kind": "accel", "amount": 1, "source": "deck", "target": "any_pokemon", **unmodelled}
        assert not _budget_readable([row]), f"gate accepted an unreadable clause: {row}"
