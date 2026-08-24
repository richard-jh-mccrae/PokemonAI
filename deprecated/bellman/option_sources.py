"""Bellman-only source-card recovery from engine option shapes."""
from __future__ import annotations

import json

from common.option_equivalence import (
    AREA_HAND, AREA_STADIUM, _FINGERPRINT_REFERENCE_LENGTH, _ZONE_REFS, _card_at,
    _is_implicit_play,
)


def option_source_card(option: dict, frame: dict | None):
    if not isinstance(option, dict):
        return None
    seat = option.get("playerIndex")
    if seat is None:
        seat = ((frame or {}).get("current") or {}).get("yourIndex", 0)
    area = option.get("area", AREA_HAND)
    if area is None and _is_implicit_play(option):
        area = AREA_HAND
    return _card_at(frame, seat, area, option.get("index"))


def option_in_play_source_id(option, frame: dict | None, seat: int | None = None) -> int | None:
    if not isinstance(option, dict):
        return None
    card_id = option.get("cardId")
    if card_id is not None:
        return int(card_id)
    if option.get("playerIndex") is not None:
        seat = option["playerIndex"]
    if seat is None:
        seat = ((frame or {}).get("current") or {}).get("yourIndex", 0)
    for area_key, index_key in reversed(_ZONE_REFS):
        area = option.get(area_key)
        if area is None:
            continue
        index = option.get(index_key)
        if area == AREA_STADIUM:
            cards = ((frame or {}).get("current") or {}).get("stadium") or []
            card = (cards[index] if isinstance(index, int) and 0 <= index < len(cards)
                    else None)
        else:
            card = _card_at(frame, seat, area, index)
        return (int(card["id"]) if isinstance(card, dict) and card.get("id") is not None
                else None)
    return None

def fingerprint_source_card_id(part, frame: dict | None) -> int | None:
    if not isinstance(part, str):
        return None
    try:
        decoded = json.loads(part)
    except (TypeError, ValueError):
        return None
    if not isinstance(decoded, list) or not decoded:
        return None
    head = decoded[0]
    if isinstance(head, dict):
        return option_in_play_source_id(head, frame)
    fields = decoded[1] if len(decoded) > 1 and isinstance(decoded[1], dict) else {}
    if fields.get("cardId") is not None:
        return int(fields["cardId"])
    cards = decoded[2] if len(decoded) > 2 and isinstance(decoded[2], list) else []
    for reference in cards:
        if (isinstance(reference, list) and len(reference) == _FINGERPRINT_REFERENCE_LENGTH
                and isinstance(reference[1], dict) and reference[1].get("id") is not None):
            return int(reference[1]["id"])
    return None
