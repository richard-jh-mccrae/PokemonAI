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

# Clause shapes the Attach Budget can actually read (CombatMath._accel_units / _hand_yield_units).
_ATTACHES = ("accel",)
_HAND_YIELD_TARGETS = ("basic_energy", "energy")


def _tags() -> dict:
    raw = json.loads((_ROOT / "src" / "common" / "card_functions.json").read_text(encoding="utf-8"))
    return {int(k): set(v) for k, v in raw.items()}


def _clauses() -> dict:
    raw = json.loads((_ROOT / "src" / "common" / "card_effects.json").read_text(encoding="utf-8"))
    return {int(k): v for k, v in raw.items()}


def _deck_ids(deck_csv: Path) -> set:
    ids = set()
    for row in csv.reader(deck_csv.read_text(encoding="utf-8").splitlines()):
        ids.update(int(cell.strip()) for cell in row if cell.strip().isdigit())
    return ids


def _budget_readable(clauses) -> bool:
    """Does any clause give the Budget a unit — an attach, or an Energy put into hand?"""
    return any(
        (cl.get("kind") in _ATTACHES and (cl.get("amount") or cl.get("to_hand")))
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
