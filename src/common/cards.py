"""Card-knowledge loaders for the Pilot (see common/CONTEXT.md: Function Tag).

`CardFunctions` wraps the shipped, offline-built `card_functions.json`
(`{cardId: [tags]}`) produced by `tools/build_card_functions.py`. It is treated as
**partial and additive**: an unknown card simply has no tags, so the table can grow
(evolutions, etc.) without any Pilot change, and a missing file degrades to empty.
"""
from __future__ import annotations

import json
from pathlib import Path

_DEFAULT = Path(__file__).resolve().parent / "card_functions.json"


class CardFunctions:
    def __init__(self, table: dict):
        self._table = {int(k): list(v) for k, v in table.items()}

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
        for t in self._table.get(card_id, ()):
            if isinstance(t, str) and t.startswith("dig:"):
                try:
                    return max(0, int(t.split(":", 1)[1]))
                except ValueError:
                    return 0
        return 0

    @classmethod
    def load(cls, path=None) -> "CardFunctions":
        p = Path(path) if path is not None else _DEFAULT
        if p.exists():
            return cls(json.loads(p.read_text(encoding="utf-8")))
        return cls({})
