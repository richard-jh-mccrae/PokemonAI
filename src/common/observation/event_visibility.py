from __future__ import annotations


_PLAYER = frozenset({"playerIndex"})
_CARD = _PLAYER | {"cardId", "serial"}
_TARGET = _CARD | {"cardIdTarget", "serialTarget"}
_CHANGE = _PLAYER | {"cardIdBefore", "serialBefore", "cardIdAfter", "serialAfter"}
_MOVE = _PLAYER | {"fromArea", "toArea"}
EVENT_FIELDS = {
    0: _PLAYER, 1: _PLAYER | {"hasBasicPokemon"}, 2: _PLAYER, 3: _PLAYER,
    4: _CARD, 5: _PLAYER, 6: _MOVE | _CARD, 7: _MOVE,
    8: _PLAYER | {"cardIdActive", "serialActive", "cardIdBench", "serialBench"},
    9: _CHANGE, 10: _CARD, 11: _TARGET, 12: _TARGET, 13: _TARGET,
    14: _CHANGE | _CARD, 15: _CARD | {"attackId"},
    16: _CARD | {"value", "putDamageCounter"},
    17: _CARD | {"isRecover"}, 18: _CARD | {"isRecover"},
    19: _CARD | {"isRecover"}, 20: _CARD | {"isRecover"},
    21: _CARD | {"isRecover"}, 22: _PLAYER | {"head"}, 23: frozenset({"result", "reason"}),
}
_BOOLEAN_FIELDS = frozenset({"hasBasicPokemon", "isRecover", "putDamageCounter", "head"})


def _valid_field(key, value):
    if key in _BOOLEAN_FIELDS:
        return type(value) is bool
    if not isinstance(value, int) or isinstance(value, bool):
        return False
    if key == "playerIndex":
        return value in (0, 1)
    if key == "result":
        return value in (0, 1, 2)
    if key.startswith("cardId"):
        return value > 0
    if key == "value":
        return True
    return value >= 0


def visible_event(row, seat):
    if not isinstance(row, dict):
        return None, (), False
    value = row.get("type")
    kind = int(value) if value is not None else None
    if kind == 4 and row.get("playerIndex") != seat:
        kind = 5
    allowed = EVENT_FIELDS.get(kind, ())
    fields = tuple((key, value) for key, value in sorted(row.items())
                   if key in allowed and value is not None
                   and isinstance(value, (bool, int, float, str)))
    if any(not _valid_field(key, value) for key, value in fields):
        raise ValueError("event visibility contains invalid field values")
    return kind, fields, kind in EVENT_FIELDS


def validate_events(events, seat):
    for event in events:
        fields = dict(event.public_fields)
        allowed = EVENT_FIELDS.get(event.kind, ())
        if (event.kind == 4 and fields.get("playerIndex") != seat
                or any(value is not None and key not in allowed for key, value in fields.items())
                or any(value is not None and not _valid_field(key, value) for key, value in fields.items())
                or event.recognized != (event.kind in EVENT_FIELDS)
                or len(fields) != len(event.public_fields)):
            raise ValueError("event visibility violates the focal observation contract")
