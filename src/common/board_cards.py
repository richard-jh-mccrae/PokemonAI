"""**The one walk** over a board Pokémon's cards — the raw-observation shape, in one place.

A board body (`cg.api.Pokemon`) carries FOUR card-bearing keys and one that is not cards at all, and
telling them apart is the whole reason this module exists (Issue #297):

    id / serial     the body's own card
    energyCards     list[Card]        — the Energy CARDS attached
    tools           list[Card]        — the Pokémon Tool CARDS attached
    preEvolution    list[Card]        — the CARDS stacked under it
    energies        list[EnergyType]  — **NOT cards.** The Energy UNITS those cards PROVIDE

``energies`` is the trap. It reads like a fifth card list and coincidentally behaves like one,
because the eight Basic Energy card ids are numerically equal to their ``EnergyType`` codes (Basic
{G} is card 1 and ``GRASS`` is 1, …, Basic {M} is card 8 and ``METAL`` is 8 — `data/EN_Card_Data.csv`
and `cg.api.EnergyType`). The coincidence ends at the ninth card: Ignition Energy is card **17** and
renders as ``[0, 0, 0]`` (three COLORLESS units), Rock Fighting Energy is card **20** and renders as
``[6]`` — the code for Basic {F} Energy, a card it is not. A counter that walks ``energies`` for card
identity therefore misses card 17 entirely and decrements card 6 for every card 20.

Measured on the committed corrections store (Issue #297): **137 of 5902** board-body OCCURRENCES
carry an ``energies`` that disagrees with its ``energyCards`` — occurrences rather than distinct
bodies, since one body recurs across the frames of a turn. Narrowed to the 372 frames the two
ADR-0072 gates replay, and to MY side (the only one :attr:`~common.state_model.MySide.visible_counts`
walks): **25 of 1018 bodies**, every one of them an Ignition.

So: **card identity comes from** :data:`CARD_STACKS`; **unit counts come from** ``energies``. Every
reader that wants "which cards are provably out of the deck" goes through :func:`body_card_entries`
or :func:`body_card_ids` here, and there is no second opinion about which keys those are.

Pure / lib-free (the gates, the deck tracker and the scouting layer all import it without touching
the native engine), and it never raises — a malformed body yields nothing rather than crashing the
agent on the grader.
"""
from __future__ import annotations

#: The keys of a board body that hold CARDS attached to / stacked under it. The body's own ``id`` is
#: not in the tuple because it is not a list — :func:`body_card_entries` yields it first.
CARD_STACKS = ("energyCards", "tools", "preEvolution")


def card_id(entry) -> int | None:
    """The card id of a zone entry — a dict ``{'id': …}`` or a bare int — or None.

    Both shapes are real: the engine hands dicts, while several hand-built fixtures and the
    ``preEvolution``-style stacks a test writes by hand carry bare ids."""
    if isinstance(entry, dict):
        return entry.get("id")
    return entry if isinstance(entry, int) and not isinstance(entry, bool) else None


def body_card_entries(body):
    """Yield every CARD entry a board Pokémon accounts for: the body itself, then each card attached
    to or stacked under it (:data:`CARD_STACKS`), in a fixed key order.

    Entries, not ids, because :meth:`~common.deck_tracker.OwnCardModel._visible` also needs each
    entry's ``serial`` to dedupe the resolving-card rider. Callers that only want ids take
    :func:`body_card_ids`.

    ``energies`` is deliberately NOT walked — see the module docstring."""
    if not body:
        return
    yield body
    for group in CARD_STACKS:
        for entry in (body.get(group) or ()):
            if entry is not None:
                yield entry


def body_card_ids(body):
    """The card ids :func:`body_card_entries` names, skipping anything that resolves to none."""
    for entry in body_card_entries(body):
        cid = card_id(entry)
        if cid is not None:
            yield cid


def body_unit_codes(body) -> tuple:
    """The OTHER half: a body's ``energies`` as a tuple of ``EnergyType`` codes — the Energy UNITS
    its attached cards provide.

    Here rather than at either reader, for the same reason as :func:`body_card_ids`: the model's
    :attr:`~common.state_model.BodyView.energy_key` and
    :meth:`~common.strategy.combat.CombatMath.attached_unit_codes` had this expression
    character-for-character each, and each docstring called itself the one accessor. Two accessors
    for one field is how the card half drifted in the first place.

    Tuple rather than a generator because both callers need it hashable — one is a memo key, the
    other is walked twice. The engine gives bare ints; the dict coercion is a cheap guard so a
    hand-built fixture cannot make a memo key raise."""
    return tuple(e.get("id") if isinstance(e, dict) else e
                 for e in ((body or {}).get("energies") or ()))
