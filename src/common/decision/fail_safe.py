from __future__ import annotations

import hashlib
import json

from common.api import ActionIdentity
from common.options import LegalAction, enumerate_legal_actions
from common.strategy.context import (
    _DAMAGE,
    _DAMAGE_COUNTER,
    _DAMAGE_COUNTER_ANY,
    _DAMAGE_COUNTER_COUNT,
    _DRAW_COUNT,
    _END,
    _TO_BENCH,
    _TO_FIELD,
    _TO_HAND,
)
from .contracts import FailSafeRequest


def _int_field(mapping, key, default: int) -> int:
    value = (mapping or {}).get(key, default)
    return default if value is None else int(value)


def safe_legal_selection(observation: dict) -> list[int]:
    select = observation.get("select") or {}
    options = tuple(select.get("option") or ())
    try:
        return _ranked_selection(select, options, observation)
    except (AttributeError, IndexError, KeyError, TypeError, ValueError):
        return list(range(_safe_minimum(select, len(options))))


def _safe_minimum(select, option_count: int) -> int:
    try:
        return min(max(0, int(select.get("minCount") or 0)), option_count)
    except (AttributeError, TypeError, ValueError):
        return min(1, option_count)


def _ranked_selection(select, options, observation: dict) -> list[int]:
    context = _int_field(select, "context", -1)
    end_index = next((index for index, option in enumerate(options)
                      if isinstance(option, dict) and option.get("type") is not None
                      and int(option["type"]) == _END), None)
    if context == 0 and end_index is not None:
        return [end_index]
    minimum = min(max(0, int(select.get("minCount") or 0)), len(options))
    maximum = min(max(minimum, int(select.get("maxCount") or 0)), len(options))
    if not options:
        return []
    if context == _TO_HAND:
        return list(range(maximum))
    if context in {_TO_BENCH, _TO_FIELD}:
        return list(range(max(minimum, min(1, maximum))))
    if context in {_DAMAGE, _DAMAGE_COUNTER, _DAMAGE_COUNTER_ANY}:
        players = ((observation.get("current") or {}).get("players") or ())
        counters = max(1, int(select.get("remainDamageCounter") or 1))

        def target(index):
            option = options[index]
            seat = int(option.get("playerIndex", 1))
            area = int(option.get("area", -1))
            player = players[seat] if 0 <= seat < len(players) and players[seat] else {}
            bodies = ((player.get("active") or ()) if area == 4 else
                      (player.get("bench") or ()) if area == 5 else ())
            position = option.get("index")
            body = (bodies[position] if isinstance(position, int)
                    and 0 <= position < len(bodies) else {})
            hp = int((body or {}).get("hp", 10 ** 9))
            if hp <= 0:
                return (2, 0, index)
            return (0 if hp <= counters * 10 else 1, hp, index)

        return [min(range(len(options)), key=target)]
    if context in {_DRAW_COUNT, _DAMAGE_COUNTER_COUNT}:
        return [max(range(len(options)), key=lambda index: (
            int(options[index].get("number", -1)), -index))]
    return list(range(minimum))


def fail_safe_request(observation: dict) -> FailSafeRequest:
    try:
        actions = enumerate_legal_actions(observation)
    except (AttributeError, IndexError, KeyError, TypeError, ValueError):
        actions = ()
    selection = tuple(safe_legal_selection(observation))
    if not any(selection in action.equivalent_selections for action in actions):
        select = observation.get("select") or {}
        try:
            context = int(select.get("context", -1))
        except (AttributeError, TypeError, ValueError):
            context = -1
        action = LegalAction(
            ActionIdentity("fail_safe_raw", (context,)), selection, (selection,), ())
        actions = (*actions, action)
    current = observation.get("current") or {}
    try:
        seat = int(current.get("yourIndex", 0))
    except (AttributeError, TypeError, ValueError):
        seat = 0
    payload = json.dumps(observation, sort_keys=True, default=str).encode("utf-8")
    key = hashlib.blake2b(payload, digest_size=16).hexdigest()
    raw_select = observation.get("select") or {}
    try:
        context = int(raw_select.get("context")) if isinstance(raw_select, dict) else None
    except (TypeError, ValueError):
        context = None
    return FailSafeRequest(observation, tuple(actions), seat, key, key, context)


__all__ = ("fail_safe_request", "safe_legal_selection")
