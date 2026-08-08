"""Render engine option dicts into human-readable labels for the tagging dropdown.

Options reference cards by ``(area, index)`` using ``cg/api.py`` ``AreaType`` codes,
where ``index`` is a *position* within that zone of ``current`` (verified against the
full-info film). Best-effort: Main actions, card-selects and board targets resolve to
card/attack names; anything unrecognised falls back to a safe, non-misleading generic label.

Board targets are *disambiguated*: a Pokemon on the field renders as
``Name (slot · hp/max · N⚡)`` -- with an ``opp`` prefix when it belongs to the opponent --
so two identical copies (e.g. two benched ``Mega Starmie ex``) can be told apart, and so a
snipe/Boss target shows whose board it is. Attacks resolve their move name via the engine
(``attackId`` -> name), so a two-attack Pokemon no longer renders ``Attack`` twice.
"""
from __future__ import annotations

# api.py AreaType -> current zone key. LOOKING (12) is a top-level list, not per-player.
_AREA = {
    1: "deck", 2: "hand", 3: "discard", 4: "active", 5: "bench",
    6: "prize", 7: "stadium", 9: "tool", 12: "looking",
}

# Lazily resolved so a label-only caller never loads the native engine until it tags an Attack;
# degrades to "Attack #<id>" when the engine is unavailable.
_ATTACK_NAMES: dict[int, str] | None = None


def _attack_name(attack_id: int | None) -> str | None:
    global _ATTACK_NAMES
    if attack_id is None:
        return None
    if _ATTACK_NAMES is None:
        try:
            from cg.api import all_attack
            _ATTACK_NAMES = {a.attackId: a.name for a in all_attack()}
        except Exception:
            _ATTACK_NAMES = {}
    return _ATTACK_NAMES.get(attack_id)


def _mon_entry(current: dict, area: int | None, index: int | None,
               player_index: int) -> dict | None:
    """The Pokemon dict at a per-player board ``(area, index)``, or None if it isn't one."""
    zone_key = _AREA.get(area)
    if zone_key is None or index is None:
        return None
    players = current.get("players") or []
    if not (0 <= player_index < len(players)):
        return None
    zone = players[player_index].get(zone_key) or []
    if 0 <= index < len(zone) and isinstance(zone[index], dict):
        return zone[index]
    return None


def _card_name(current: dict, area: int | None, index: int | None, player_index: int) -> str | None:
    zone_key = _AREA.get(area)
    if zone_key is None or index is None:
        return None
    if zone_key == "looking":
        zone = current.get("looking") or []
        if 0 <= index < len(zone) and isinstance(zone[index], dict):
            return zone[index].get("name")
        return None
    entry = _mon_entry(current, area, index, player_index)
    return entry.get("name") if entry else None


def _board_target(current: dict, area: int | None, index: int | None,
                  player_index: int, seat: int | None) -> str | None:
    """A field Pokemon as ``Name (slot · hp/max · N⚡)``; ``bench K`` is 1-BASED. None when
    ``(area, index)`` is not a board Pokemon, so callers fall back to a plain card name."""
    if area == 4:
        slot = "active"
    elif area == 5 and index is not None:
        slot = f"bench {index + 1}"
    else:
        return None
    entry = _mon_entry(current, area, index, player_index)
    if entry is None:
        return None
    bits = [slot]
    hp, mx = entry.get("hp"), entry.get("maxHp")
    if isinstance(hp, int) and isinstance(mx, int):
        bits.append(f"{hp}/{mx}")
    n_energy = len(entry.get("energyCards") or [])
    if n_energy:
        bits.append(f"{n_energy}⚡")
    owner = "opp " if (seat is not None and player_index != seat) else ""
    return f"{owner}{entry.get('name') or '?'} ({' · '.join(bits)})"


def option_label(option: dict, current: dict) -> str:
    """A readable label for one option, resolved against the full-info board."""
    kind = option.get("type")
    seat = current.get("yourIndex", 0)
    player_index = option.get("playerIndex", seat)

    if kind == "End":
        return "End turn"
    if kind == "Play":                       # index is a hand position
        name = _card_name(current, 2, option.get("index"), player_index)
        return f"Play {name}" if name else "Play"
    if kind == "Attach":
        src = _card_name(current, option.get("area"), option.get("index"), player_index)
        tgt = _board_target(current, option.get("inPlayArea"), option.get("inPlayIndex"),
                            player_index, seat)
        if src and tgt:
            return f"Attach {src} → {tgt}"
        if tgt:
            return f"Attach → {tgt}"
        return f"Attach {src}" if src else "Attach"
    if kind == "Evolve":
        evo = _card_name(current, option.get("area"), option.get("index"), player_index)
        tgt = _board_target(current, option.get("inPlayArea"), option.get("inPlayIndex"),
                            player_index, seat)
        if evo and tgt:
            return f"Evolve {evo} → {tgt}"
        if tgt:
            return f"Evolve → {tgt}"
        return f"Evolve {evo}" if evo else "Evolve"
    if kind == "Attack":
        name = _attack_name(option.get("attackId"))
        if name:
            return f"Attack with {name}"
        aid = option.get("attackId")
        return f"Attack #{aid}" if aid is not None else "Attack"
    if kind == "Card":
        tgt = _board_target(current, option.get("area"), option.get("index"), player_index, seat)
        return tgt or _card_name(current, option.get("area"), option.get("index"),
                                 player_index) or "(card)"

    # Evolve handled above; ToolCard / Energy / Ability / Retreat / Discard / ...: prefer
    # disambiguated board target, else card name, else bare action kind.
    tgt = _board_target(current, option.get("area"), option.get("index"), player_index, seat)
    if tgt:
        return f"{kind}: {tgt}"
    name = _card_name(current, option.get("area"), option.get("index"), player_index)
    if name:
        return f"{kind}: {name}"
    return str(kind) if kind else "(option)"
