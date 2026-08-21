"""Frozen Brief-role resolver retained only for the deprecated Bellman teacher."""
from __future__ import annotations

from common.scouting.pokemon_roles import general_pokemon_roles


_TARGET_ROLE_ORDER = (
    "primary_attacker", "backup_attacker", "accel_source", "counter_mover",
    "draw_engine", "search_engine", "healer", "stall_pokemon", "support_pokemon")


def evolution_line(card_ids, ids_for_name, stat_for_id, forward_ids) -> frozenset[int]:
    line = {int(card_id) for card_id in card_ids}
    if stat_for_id is None:
        return frozenset(line)
    if forward_ids is not None:
        for card_id in tuple(line):
            line.update(int(descendant) for descendant in forward_ids(card_id) or ())
    pending = list(line)
    while pending:
        stat = stat_for_id(pending.pop())
        parent = getattr(stat, "evolvesFrom", None) if stat is not None else None
        for ancestor in ids_for_name(parent) if parent else ():
            if int(ancestor) not in line:
                line.add(int(ancestor))
                pending.append(int(ancestor))
    return frozenset(line)


def resolve_brief_cards(brief, ids_for_name, *, stat_for_id=None, forward_ids=None):
    threat_ids = set()
    role_claims: dict[int, set[str]] = {}
    primary_ids = set()
    for entry in brief.pokemon or ():
        roles = tuple(entry.get("roles") or ())
        ids = {int(card_id) for card_id in ids_for_name(entry.get("card", "")) or ()}
        if stat_for_id is not None:
            generic = general_pokemon_roles(ids, _StatLookup(stat_for_id, forward_ids))
            for card_id, card_roles in generic.items():
                role_claims.setdefault(card_id, set()).update(card_roles)
        if {"primary_attacker", "backup_attacker"}.intersection(roles):
            threat_ids.update(ids)
        for card_id in ids:
            role_claims.setdefault(card_id, set()).update(roles)
        if "primary_attacker" in roles:
            primary_ids.update(ids)
    primary_line = evolution_line(primary_ids, ids_for_name, stat_for_id, forward_ids)
    threat_ids.update(primary_line)
    for card_id in primary_line:
        role_claims.setdefault(card_id, set()).add("primary_attacker")
    targets = {card_id: next((role for role in _TARGET_ROLE_ORDER if role in roles), None)
               for card_id, roles in role_claims.items()}
    return frozenset(threat_ids), {card_id: role for card_id, role in targets.items() if role}


class _StatLookup:
    def __init__(self, get, forward_card_ids=None):
        self.get = get
        self.forward_card_ids = forward_card_ids or (lambda _card_id: ())


__all__ = ("evolution_line", "resolve_brief_cards")
