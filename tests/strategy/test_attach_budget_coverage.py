"""The Attach Budget's COVERAGE GATE (issue #137 / ADR-0067).

Fail-closed is load-bearing but silent: an accel card with no Effect-Clause row contributes zero
and says nothing about it, so a deck that adds one would quietly under-read its own budget and
re-open the f70 false-famine class of blunder. This gate makes that zero **audited** — every
`tutor_energy` / `energy_accel` card in a shipped agent's deck must either carry a Budget-readable
clause or sit on the explicit list below, with a reason.

Pure data (decklists × Function Tags × Effect Clauses) — no engine, no Pilot; the same shape as the
Scouting coverage gate CI already runs on both platforms.
"""
import csv
import json
from pathlib import Path

import pytest

from common.strategy.combat import _ACCEL_TAGS

_ROOT = Path(__file__).resolve().parents[2]
_AGENTS = _ROOT / "src" / "agents"

# Accel-tagged cards a shipped deck runs that the Budget deliberately values at ZERO. Each entry is
# a ruling, not a TODO — re-verify at source before removing one.
KNOWN_UNMODELLED = {
    666: "Cinderace — its acceleration is the ATTACK Turbo Flare; attacking ends the turn, so it "
         "can never fund another attack this turn (the self-side mirror of ADR-0064's "
         "attack-based-accel exclusion). Permanently zero, not a gap.",
}

# The vocabulary CombatMath's clause interpreter actually models. Anything outside these sets is
# silently zeroed at runtime (_accel_target_ok / _AttachCtx.source_types / condition_met all fail
# CLOSED), so a clause using an unmodelled word must NOT count as coverage — otherwise the gate
# waves through exactly the silent zero it exists to catch.
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
    return {int(k): v for k, v in raw.items()}


def _special_energy_ids() -> set:
    """Special Energy card ids, read off the shipped CSV's type column — the same pure-data seam the
    rest of this gate uses, so it needs no engine. (`CardStat.is_special_energy` answers the same
    question at runtime from the engine's cardType 6; this file deliberately does not boot it.)"""
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
    """An `accel` clause the interpreter can actually turn into units — a quantity AND every gate
    word in the modelled vocabulary."""
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
    """Guards the gate itself: a glob that silently matches nothing would pass every case below."""
    assert _shipped_decks(), "no shipped agent decks found — the coverage gate would be vacuous"


@pytest.mark.parametrize("deck_csv", _shipped_decks(), ids=lambda p: p.parent.name)
def test_every_accel_card_in_a_shipped_deck_is_modelled_or_explicitly_ruled_zero(deck_csv):
    tags, clauses = _tags(), _clauses()
    gaps = [cid for cid in sorted(_deck_ids(deck_csv))
            if (tags.get(cid, set()) & _ACCEL_TAGS)
            and cid not in KNOWN_UNMODELLED
            and not _budget_readable(clauses.get(cid, ()))]
    assert not gaps, (
        f"{deck_csv.parent.name}: accel-tagged cards with no Budget-readable Effect Clause: {gaps}. "
        "Author the clause in tools/meta_tracker/effect_overrides.json (verify the card text at "
        "source first), or add it to KNOWN_UNMODELLED with the ruling that makes zero correct.")


@pytest.mark.parametrize("deck_csv", _shipped_decks(), ids=lambda p: p.parent.name)
def test_every_special_energy_in_a_shipped_deck_carries_its_provision(deck_csv):
    """The SECOND way a Budget goes silently blind (#142). A Special Energy is not one unit of its
    own colour — Ignition Energy provides {C}{C}{C} on an Evolution — so the hand leg's typed-Basic
    count cannot see it, and an untagged one contributes ZERO. On mega_starmie that zero is a Mega
    Starmie ex reading as a famine while the Ignition in hand would arm it outright: a FALSE FAMINE
    on a shipped deck, which is the exact class this phase exists to close.

    The provision is a `provides:N` Function Tag (`provides_evo:N` where the card says "instead"),
    curated in tools/meta_tracker/function_overrides.json against the card text — the same seam and
    the same parametric shape as `dig:N`. The COLOUR is not tagged: CardStat.energyType has it."""
    tags = _tags()
    special = _special_energy_ids()
    gaps = sorted(cid for cid in _deck_ids(deck_csv) if cid in special
                  and not any(str(t).startswith("provides:") for t in tags.get(cid, ())))
    assert not gaps, (
        f"{deck_csv.parent.name}: Special Energy with no `provides:N` tag: {gaps}. Read the card's "
        "'it provides …' line at data/EN_Card_Data.csv and add the tag to "
        "tools/meta_tracker/function_overrides.json — untagged, the Attach Budget prices it at zero.")


def test_the_special_energy_audit_has_something_to_audit():
    """Guards the gate: if the card data stopped reporting Special Energy the check above would
    pass vacuously on every deck."""
    assert _special_energy_ids(), "no Special Energy found in the card data — the audit is vacuous"


def test_the_known_unmodelled_list_stays_honest():
    """A card that GAINED a clause must leave the ruled-zero list — the list is for cards the
    Budget must ignore, never a parking lot for ones it now reads."""
    clauses = _clauses()
    stale = [cid for cid in KNOWN_UNMODELLED if _budget_readable(clauses.get(cid, ()))]
    assert not stale, f"now Budget-readable — drop from KNOWN_UNMODELLED: {stale}"


def test_the_f70_enabler_carries_its_full_two_unit_yield():
    """Crispin (1198) is the primitive's reason to exist: 'up to 2 Basic Energy cards of different
    types … put 1 into your hand. Attach the other.' Both halves must be in the shipped row, or the
    2-cost typed reach the oracle was built for silently disappears."""
    crispin = _clauses().get(1198, ())
    accel = [cl for cl in crispin if cl.get("kind") == "accel"]
    assert accel, "Crispin lost its accel clause"
    assert accel[0].get("amount") == 1, "the ATTACH half"
    assert accel[0].get("to_hand") == 1, "the put-1-into-your-hand half — the f70 fix"
    assert accel[0].get("distinct_types") is True, "'of different types' — the same-colour guard"


def test_the_gate_rejects_a_clause_written_in_unmodelled_vocabulary():
    """A row can carry a quantity and still be worth zero at runtime, because every gate word the
    interpreter doesn't know fails CLOSED. The audit must not accept such a row as coverage —
    otherwise it certifies the silent zero it exists to surface."""
    assert _budget_readable([{"kind": "accel", "amount": 1, "source": "deck",
                              "target": "any_pokemon"}])
    for unmodelled in ({"target": "in_play_ex"},          # target class the interpreter refuses
                       {"source": "hand"},                # zone it cannot read
                       {"condition": "opponent_has_stadium"}):   # condition it cannot evaluate
        row = {"kind": "accel", "amount": 1, "source": "deck", "target": "any_pokemon", **unmodelled}
        assert not _budget_readable([row]), f"gate accepted an unreadable clause: {row}"
