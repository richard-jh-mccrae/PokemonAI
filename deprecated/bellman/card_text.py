"""Bellman-only card-name family matching."""
from __future__ import annotations

from common.scouting.card_text import normalize_card_name


def name_in_family(name: str | None, family: str | None) -> bool:
    if not family:
        return True
    if not name:
        return False
    return normalize_card_name(name).startswith(normalize_card_name(family) + " ")


__all__ = ("name_in_family",)
