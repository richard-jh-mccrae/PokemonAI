"""Committed CARD FACTS a test fixture needs, stated **once** (Issue #418).

A fixture that hand-writes a card's Function Tags is asserting a card fact, so the tags live here in
ONE copy, asserted against `src/common/card_functions.json` by `tests/strategy/test_provision_seam.py`
— as a LITERAL, because a constant that reads the store can only ever agree with it.

Not every fixture should take these: a test whose name says it runs an INCOMPLETE tag set is
asserting what happens when a fact is MISSING, which is a different thing from getting it wrong.
"""
from __future__ import annotations

#: Ignition Energy (id 17). All three tags are load-bearing: ``discard_eot`` ROUTES, and
#: ``provides:1`` / ``provides_evo:3`` QUANTIFY (ADR-0032). A tuple, so no fixture can mutate it.
IGNITION_TAGS: tuple[str, ...] = ("discard_eot", "provides:1", "provides_evo:3")

#: Card ids of the three Energy cards in the pool that carry a provision tag at all. Boomerang (9)
#: and Telepath Psychic (19) are ``provides:1`` with no expiry and no evolution clause.
IGNITION, BOOMERANG_ENERGY, TELEPATH_PSYCHIC_ENERGY = 17, 9, 19


def ignition_tags() -> list[str]:
    """:data:`IGNITION_TAGS` as the ``list[str]`` `CardFunctions` tables are written with."""
    return list(IGNITION_TAGS)
