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

    @classmethod
    def load(cls, path=None) -> "CardFunctions":
        p = Path(path) if path is not None else _DEFAULT
        if p.exists():
            return cls(json.loads(p.read_text(encoding="utf-8")))
        return cls({})
