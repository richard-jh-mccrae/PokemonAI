"""Portable transition predicates shared by both Bellman engine adapters."""
from __future__ import annotations


def end_has_forced_value_change(state, registry) -> bool:
    """Whether ending consumes a visible attached resource with a turn-boundary rider."""
    if registry is None:
        return False
    current = state.obs.get("current") or {}
    players = current.get("players") or ()
    seat = state.root_seat
    player = players[seat] if 0 <= seat < len(players) and players[seat] else {}
    bodies = tuple(player.get("active") or ()) + tuple(player.get("bench") or ())
    return any("discard_eot" in registry.functions.get(int(card.get("id", 0)), ())
               for body in bodies if body for card in (body.get("energyCards") or ()) if card)


__all__ = ("end_has_forced_value_change",)
