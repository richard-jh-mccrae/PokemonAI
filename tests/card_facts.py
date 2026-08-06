"""Committed CARD FACTS a test fixture needs, stated **once**.

A fixture that hand-writes a card's Function Tags is asserting a card fact, and eighteen fixtures
hand-writing the same one is eighteen chances to assert it differently. Issue #418 found exactly
that: fifteen files tagged Ignition Energy ``["discard_eot"]`` and nothing else, dropping the
``provides:1`` / ``provides_evo:3`` pair that carries its actual provision — invisible only because
a hardcoded *three-on-an-Evolution-holding-a-`discard_eot`-card* was supplying the 3 those tags
should have. When the hardcode was replaced by the real accessor
(`CombatMath.provision_codes`, ADR-0125) every one of those fixtures started reading 1 unit,
because that is what they had always been describing.

So the tags live here, ONE copy, **asserted against `src/common/card_functions.json`** by
`tests/strategy/test_provision_seam.py::test_the_committed_tags_are_what_the_shared_fixture_claims`
— stated as a literal rather than loaded from the store, because a constant that reads the store can
only ever agree with it and would make the assertion vacuous.

`tests/` is on `sys.path` (`tests/conftest.py`), so this imports from any subdirectory, the same way
`pilot_helpers` and `scouting_helpers` do.

⚠️ **Not every fixture should take these.** Two tests deliberately run an INCOMPLETE tag set and say
so in their names — `test_reachable_attach.py::test_an_untagged_special_energy_provides_nothing`
(the fail-CLOSED probe, ADR-0067) and
`test_turns_to_afford.py::test_the_strip_reads_the_CLAUSE_not_the_TAG` (ADR-0032's tag-ROUTES /
clause-QUANTIFIES split). Those are asserting what happens when a fact is missing, which is a
different thing from getting it wrong.
"""
from __future__ import annotations

#: **Ignition Energy**, Card ID 17 — `data/EN_Card_Data.csv`, read at source: *"If this card is
#: attached to 1 of your Pokémon, discard it at the end of your turn. As long as this card is
#: attached to a Pokémon, it provides {C} Energy. If this card is attached to an Evolution Pokémon,
#: it provides {C}{C}{C} Energy instead."*
#:
#: Three tags, and all three are load-bearing: ``discard_eot`` ROUTES (the behavioural fact that the
#: card evaporates), while ``provides:1`` / ``provides_evo:3`` QUANTIFY (ADR-0032). It is the pool's
#: ONLY card carrying either ``discard_eot`` or ``provides_evo``, and it carries both — the
#: coincidence that let the retired hardcode read correctly on every card that exists.
#:
#: A tuple, not a list: this is shared across every test in the session and a mutable default would
#: let one fixture edit another's card facts.
IGNITION_TAGS: tuple[str, ...] = ("discard_eot", "provides:1", "provides_evo:3")

#: Card ids of the three Energy cards in the pool that carry a provision tag at all. Boomerang (9)
#: and Telepath Psychic (19) are ``provides:1`` with no expiry and no evolution clause.
IGNITION, BOOMERANG_ENERGY, TELEPATH_PSYCHIC_ENERGY = 17, 9, 19


def ignition_tags() -> list[str]:
    """:data:`IGNITION_TAGS` as the ``list[str]`` `CardFunctions` tables are written with."""
    return list(IGNITION_TAGS)
