"""Card-knowledge loaders for the Pilot (see common/CONTEXT.md: Function Tag).

`CardFunctions` wraps the shipped, offline-built `card_functions.json`
(`{cardId: [tags]}`) produced by `tools/build_card_functions.py`. It is treated as
**partial and additive**: an unknown card simply has no tags, so the table can grow
(evolutions, etc.) without any Pilot change, and a missing file degrades to empty.
"""
from __future__ import annotations

import json
from pathlib import Path

from common.card_tags import is_card_key

_DEFAULT = Path(__file__).resolve().parent / "card_functions.json"


class CardFunctions:
    def __init__(self, table: dict):
        # Reserved keys SKIPPED rather than `int()`-ed (Issue #395 D6.5), matching the builder's
        # `_load_table`. Both walked every key unconditionally, so the store could not carry a
        # `_note` or a provenance block the way `function_overrides.json` and `card_effects.json`
        # already do — and the runtime loader is the half that would have raised at agent start.
        self._table = {int(k): list(v) for k, v in table.items() if is_card_key(k)}

    def tags(self, card_id: int) -> list[str]:
        """Function Tags for a card; [] if the card isn't tagged (yet)."""
        return self._table.get(card_id, [])

    def dig_depth(self, card_id: int) -> int:
        """How many cards this card's draw/dig Ability puts within reach in one use — the `dig:N`
        PARAMETRIC tag (ADR-0070 §3). The evolve decider prices an engine as the readiness odds its
        dig buys, and `draw_hit_probability` needs the depth; keeping it here makes it per-card DATA
        that ages with the card pool through the card-functions pipeline, rather than a constant.

        Only Abilities that put a USABLE enabler in hand carry a depth: Drakloak's Recon Directive
        (top 2, take 1) is 2, but Tatsugiri reveals only a Supporter and Metang attaches {M} directly
        (its value is the Budget's, not the dig's), so neither is tagged. 0 when untagged — the
        decider then makes no income claim (fail-CLOSED, ADR-0067)."""
        return self._parametric_tag(card_id, "dig:")

    def energy_provision(self, card_id: int, *, evolution: bool = False) -> int:
        """How many Energy units this card provides once ATTACHED — the `provides:N` PARAMETRIC tag,
        with `provides_evo:N` for a card whose provision changes on an Evolution Pokémon (#142).

        Same shape and same reason as :meth:`dig_depth`: per-card DATA that ages with the card pool
        through the card-functions pipeline, not a constant in the affordability code. A Basic Energy
        needs no tag — it is one unit of its own colour, and the Attach Budget's hand leg already
        counts those; this answers the question only a Special Energy raises. The COLOUR is not here
        either: ``CardStat.energyType`` already carries it (Ignition and Boomerang report colourless,
        Telepath Psychic reports {P}), so the tag adds only what the stats cannot say.

        Verified at `data/EN_Card_Data.csv`: Ignition Energy "provides {C} Energy… If this card is
        attached to an Evolution Pokémon, it provides {C}{C}{C} Energy instead" — hence the pair of
        tags and the ``evolution`` argument.

        0 when untagged (fail-CLOSED, ADR-0067): an unreadable provision contributes nothing to the
        Budget rather than a guessed one. `test_attach_budget_coverage.py` audits that zero, so a
        shipped deck cannot quietly run a Special Energy the Budget cannot price."""
        # The evolution reading REPLACES the base one ("instead"), and both are floors of the same
        # quantity, so the larger APPLICABLE tag is the provision.
        prefixes = ("provides:",) + (("provides_evo:",) if evolution else ())
        return max((self._parametric_tag(card_id, p) for p in prefixes), default=0)

    def _parametric_tag(self, card_id: int, prefix: str) -> int:
        """The integer carried by a ``<prefix>N`` PARAMETRIC tag, or 0 when the card has none and on
        any unreadable value — the fail-CLOSED read both :meth:`dig_depth` and
        :meth:`energy_provision` are, so the two cannot drift in how they parse the same tag shape."""
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
