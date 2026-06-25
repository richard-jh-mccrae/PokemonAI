"""Render engine option dicts into human-readable labels for the tagging dropdown.

Options reference cards by ``(area, index)`` using ``cg/api.py`` ``AreaType`` codes,
where ``index`` is a *position* within that zone of ``current`` (verified against the
full-info film). Best-effort: Main actions and card-selects resolve to card names;
anything unrecognised falls back to a safe, non-misleading generic label.
"""
from __future__ import annotations

# api.py AreaType -> current zone key. LOOKING (12) is a top-level list, not per-player.
_AREA = {
    1: "deck", 2: "hand", 3: "discard", 4: "active", 5: "bench",
    6: "prize", 7: "stadium", 9: "tool", 12: "looking",
}


def _card_name(current: dict, area: int | None, index: int | None, player_index: int) -> str | None:
    zone_key = _AREA.get(area)
    if zone_key is None or index is None:
        return None
    if zone_key == "looking":
        zone = current.get("looking") or []
    else:
        players = current.get("players") or []
        if not (0 <= player_index < len(players)):
            return None
        zone = players[player_index].get(zone_key) or []
    if 0 <= index < len(zone) and isinstance(zone[index], dict):
        return zone[index].get("name")
    return None


def option_label(option: dict, current: dict) -> str:
    """A readable label for one option, resolved against the full-info board."""
    kind = option.get("type")
    player_index = option.get("playerIndex", current.get("yourIndex", 0))

    if kind == "End":
        return "End turn"
    if kind == "Play":                       # index is a hand position
        name = _card_name(current, 2, option.get("index"), player_index)
        return f"Play {name}" if name else "Play"
    if kind == "Attach":
        src = _card_name(current, option.get("area"), option.get("index"), player_index)
        tgt = _card_name(current, option.get("inPlayArea"), option.get("inPlayIndex"), player_index)
        if src and tgt:
            return f"Attach {src} → {tgt}"
        return f"Attach {src}" if src else "Attach"
    if kind == "Card":
        return _card_name(current, option.get("area"), option.get("index"), player_index) or "(card)"
    if kind == "Attack":
        return option.get("name") or "Attack"

    # Evolve / Ability / Retreat / Discard / ...: use the card name when resolvable.
    name = _card_name(current, option.get("area"), option.get("index"), player_index)
    if name:
        return f"{kind}: {name}"
    return str(kind) if kind else "(option)"
