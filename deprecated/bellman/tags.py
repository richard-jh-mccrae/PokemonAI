"""Frozen loose-tag adapter retained only for Bellman teacher replay."""
from __future__ import annotations


def is_card_key(key) -> bool:
    return str(key).lstrip("-").isdigit()


class CardFunctions:
    def __init__(self, table: dict):
        self._table = {int(key): list(value) for key, value in table.items()
                       if is_card_key(key)}

    def tags(self, card_id: int) -> list[str]:
        return self._table.get(int(card_id), [])

    @classmethod
    def load(cls):
        from common.cards import card_store
        return cls({card_id: sorted(getattr(record, "tags", ()) or ())
                    for card_id, record in card_store().items()})


__all__ = ("CardFunctions", "is_card_key")
