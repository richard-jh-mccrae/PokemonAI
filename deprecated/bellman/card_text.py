"""Bellman-only card-name family matching."""
from __future__ import annotations

_APOSTROPHES = str.maketrans({"\u2019": "'", "\u02bc": "'", "\u2018": "'"})


def _normalize(name: str) -> str:
    return " ".join((name or "").translate(_APOSTROPHES).split())


def name_in_family(name: str | None, family: str | None) -> bool:
    if not family:
        return True
    if not name:
        return False
    return _normalize(name).startswith(_normalize(family) + " ")


__all__ = ("name_in_family",)
