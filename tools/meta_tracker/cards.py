"""Card-metadata access, backed by the portable ``cards.json`` cache.

Regenerate the cache with ``dump_cards.py`` when the legal pool changes.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from . import config

_STAGE_RANK = {"basic": 0, "stage1": 1, "stage2": 2}


@lru_cache(maxsize=1)
def load_cards(path: str | Path | None = None) -> dict[int, dict]:
    """Return ``{card_id: metadata}`` from the JSON cache (card_id as int)."""
    p = Path(path) if path else config.CARDS_JSON
    raw = json.loads(p.read_text(encoding="utf-8"))
    return {int(k): v for k, v in raw.items()}


def is_pokemon(card: dict) -> bool:
    return card.get("category") == "pokemon"


def is_exclass(card: dict) -> bool:
    """ex or Mega-ex — i.e. gives the opponent extra prizes when KO'd."""
    return bool(card.get("ex") or card.get("megaEx"))


def is_attacker(card: dict) -> bool:
    """A Pokémon with at least one damaging attack."""
    return is_pokemon(card) and card.get("maxDamage", 0) > 0


def stage_rank(card: dict) -> int:
    """basic=0, stage1=1, stage2=2, non-staged=-1."""
    return _STAGE_RANK.get(card.get("stage"), -1)
