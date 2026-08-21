"""The pre-store effect-clause table; the teacher's transition reconstruction reads it."""
from __future__ import annotations

import json
from pathlib import Path

from common.cards.tags import is_card_key


_DEFAULT = Path(__file__).resolve().parents[2] / "src" / "common" / "card_effects.json"


class CardEffects:
    def __init__(self, table: dict):
        table = table or {}
        self._table = {
            int(card_id): tuple(dict(clause) for clause in clauses)
            for card_id, clauses in table.items()
            if is_card_key(card_id) and isinstance(clauses, list)
        }
        coverage = table.get("_covers") or {}
        self._full = frozenset(
            int(card_id) for card_id, verdict in coverage.items()
            if is_card_key(card_id) and isinstance(verdict, dict)
            and verdict.get("covers") == "full"
        )

    def clauses(self, card_id: int) -> tuple[dict, ...]:
        return self._table.get(int(card_id), ())

    def fully_covers(self, card_id: int) -> bool:
        return int(card_id) in self._full

    @classmethod
    def load(cls, path=None) -> "CardEffects":
        source = Path(path) if path is not None else _DEFAULT
        return cls(json.loads(source.read_text(encoding="utf-8")) if source.exists() else {})


__all__ = ("CardEffects",)
