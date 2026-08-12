"""Effect-clause data consumed by Bellman transition reconstruction."""
from __future__ import annotations

import json
from pathlib import Path

from .card_tags import is_card_key


_DEFAULT = Path(__file__).with_name("card_effects.json")


class CardEffects:
    def __init__(self, table: dict):
        self._table = {
            int(card_id): tuple(dict(clause) for clause in clauses)
            for card_id, clauses in (table or {}).items()
            if is_card_key(card_id) and isinstance(clauses, list)
        }

    def clauses(self, card_id: int) -> tuple[dict, ...]:
        return self._table.get(int(card_id), ())

    @classmethod
    def load(cls, path=None) -> "CardEffects":
        source = Path(path) if path is not None else _DEFAULT
        return cls(json.loads(source.read_text(encoding="utf-8")) if source.exists() else {})


__all__ = ("CardEffects",)
