"""The one walk over a board Pokémon's cards (Issue #297). Pure / lib-free, and never raises.

CARD identity comes from :data:`CARD_STACKS`; UNIT counts come from ``energies``, which is NOT a
card list — Ignition Energy is card 17 but renders as three COLORLESS units, Rock Fighting is card
20 but renders as Basic {F}'s code. Walking it for card identity misses 17 and miscounts 6.
"""
from __future__ import annotations

#: The CARD-bearing keys of a board body. Its own ``id`` is not one — it is not a list.
CARD_STACKS = ("energyCards", "tools", "preEvolution")


def card_id(entry) -> int | None:
    """The card id of a zone entry, or None. Both the engine's dicts and hand-built bare ids are real."""
    if isinstance(entry, dict):
        return entry.get("id")
    return entry if isinstance(entry, int) and not isinstance(entry, bool) else None


def body_card_entries(body):
    """Every CARD entry a board Pokémon accounts for. Entries, not ids: `deck_tracker` dedupes on
    ``serial``. ``energies`` is deliberately NOT walked — see the module docstring."""
    if not body:
        return
    yield body
    for group in CARD_STACKS:
        for entry in (body.get(group) or ()):
            if entry is not None:
                yield entry


def body_card_ids(body):
    for entry in body_card_entries(body):
        cid = card_id(entry)
        if cid is not None:
            yield cid


def body_unit_codes(body) -> tuple:
    """The UNIT half — a body's ``energies`` as ``EnergyType`` codes. Tuple because one caller memo-keys
    on it and the other walks it twice."""
    return tuple(e.get("id") if isinstance(e, dict) else e
                 for e in ((body or {}).get("energies") or ()))
