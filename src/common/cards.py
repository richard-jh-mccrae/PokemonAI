"""`CardFunctions` wraps the shipped `card_functions.json`. **Partial and additive**: an unknown card
has no tags and a missing file degrades to empty, so the table can grow without runtime changes."""
from __future__ import annotations

import json
from pathlib import Path

from common.card_tags import is_card_key

_DEFAULT = Path(__file__).resolve().parent / "card_functions.json"
_PARTNER_PREFIX = "partner:"
_ROLE_PREFIX = "role:"
_EVOLVES_PREFIX = "evolves:"


class CardFunctions:
    def __init__(self, table: dict):
        # Reserved keys SKIPPED rather than `int()`-ed, so the store can carry a `_note` block.
        self._table = {int(k): list(v) for k, v in table.items() if is_card_key(k)}

    def tags(self, card_id: int) -> list[str]:
        return self._table.get(card_id, [])

    def partners(self, card_id: int) -> tuple[int, ...]:
        """Printed in-play partner dependencies carried as ``partner:<card-id>`` tags.

        These are card facts, not deck doctrine. Invalid or self-referential values fail closed.
        """
        card_id = int(card_id)
        partners = set()
        for tag in self._table.get(card_id, ()):
            if not isinstance(tag, str) or not tag.startswith(_PARTNER_PREFIX):
                continue
            try:
                partner = int(tag.removeprefix(_PARTNER_PREFIX))
            except ValueError:
                continue
            if partner > 0 and partner != card_id:
                partners.add(partner)
        return tuple(sorted(partners))

    def roles(self, card_id: int) -> tuple[str, ...]:
        """Shared card roles carried as ``role:<name>`` tags."""
        return tuple(tag.removeprefix(_ROLE_PREFIX) for tag in self._table.get(int(card_id), ())
                     if isinstance(tag, str) and tag.startswith(_ROLE_PREFIX)
                     and tag.removeprefix(_ROLE_PREFIX))

    def evolves_to(self, card_id: int) -> tuple[int, ...]:
        """Printed one-hop evolution targets carried as ``evolves:<card-id>`` tags."""
        card_id = int(card_id)
        targets = set()
        for tag in self._table.get(card_id, ()):
            if not isinstance(tag, str) or not tag.startswith(_EVOLVES_PREFIX):
                continue
            try:
                target = int(tag.removeprefix(_EVOLVES_PREFIX))
            except ValueError:
                continue
            if target > 0 and target != card_id:
                targets.add(target)
        return tuple(sorted(targets))

    def dig_depth(self, card_id: int) -> int:
        """Cards this card's draw/dig Ability puts within reach in one use — the `dig:N` tag. Only
        Abilities that put a USABLE enabler in hand carry a depth; 0 when untagged (fail-CLOSED)."""
        return self._parametric_tag(card_id, "dig:")

    def energy_provision(self, card_id: int, *, evolution: bool = False) -> int:
        """Energy UNITS this card provides once ATTACHED. Basic Energy needs no tag; the COLOUR is
        `CardStat.energyType`, not here. 0 when untagged (fail-CLOSED)."""
        # The evolution reading REPLACES the base one ("instead"), and both are floors of the same
        # quantity, so the larger APPLICABLE tag is the provision.
        prefixes = ("provides:",) + (("provides_evo:",) if evolution else ())
        return max((self._parametric_tag(card_id, p) for p in prefixes), default=0)

    def _parametric_tag(self, card_id: int, prefix: str) -> int:
        """The integer carried by a ``<prefix>N`` tag; 0 when absent or unreadable (fail-CLOSED)."""
        for tag in self._table.get(card_id, ()):
            if isinstance(tag, str) and tag.startswith(prefix):
                try:
                    return max(0, int(tag.split(":", 1)[1]))
                except ValueError:
                    return 0
        return 0

    @classmethod
    def load(cls, path=None) -> "CardFunctions":
        p = Path(path) if path is not None else _DEFAULT
        if p.exists():
            return cls(json.loads(p.read_text(encoding="utf-8")))
        return cls({})
