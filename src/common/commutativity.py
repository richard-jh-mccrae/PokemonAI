"""Conservative action footprints for Bellman partial-order reduction.

Footprints declare state dependencies, not desirability.  Two deterministic actions may be placed in
one canonical order only when neither writes a resource read or written by the other.  Unknown,
information-revealing, and random effects are barriers by construction.
"""
from __future__ import annotations

from dataclasses import dataclass

from common.strategy.context import _ACTIVE, _BENCH


INFORMATION_EFFECT_KINDS = frozenset({"coin", "draw", "fetch", "energy_recur", "accel"})
DECLARED_DETERMINISTIC_EFFECT_KINDS = frozenset({
    "damage_boost", "gust", "heal", "self_switch", "stadium_static",
})
OPAQUE_ACTION_KINDS = frozenset({
    "ability", "attack", "card", "decline", "discard", "end", "energy", "energy_card",
    "number", "retreat", "skill", "special_condition", "tool_card", "yes", "no",
})


@dataclass(frozen=True)
class ActionFootprint:
    """Stable event identity plus the abstract resources it reads and writes."""

    event: tuple[str, ...]
    reads: frozenset[str] = frozenset()
    writes: frozenset[str] = frozenset()
    barrier: bool = False


def independent(left: ActionFootprint, right: ActionFootprint) -> bool:
    """Whether either fixed action order reaches the same information and state boundary."""
    if left.barrier or right.barrier or left.event == right.event:
        return False
    return not (
        left.writes & (right.reads | right.writes)
        or right.writes & (left.reads | left.writes)
    )


def _actor_side(observation: dict) -> tuple[int, dict]:
    current = observation.get("current") or {}
    seat = int(observation.get("bellmanActor", current.get("yourIndex", 0)))
    players = current.get("players") or ()
    player = players[seat] if 0 <= seat < len(players) and players[seat] else {}
    return seat, player


def _selected_option(observation: dict, action):
    options = tuple((observation.get("select") or {}).get("option") or ())
    if len(action.selection) != 1:
        return None
    index = action.selection[0]
    return options[index] if 0 <= index < len(options) else None


def _hand_card(player: dict, option: dict | None):
    index = option.get("index") if option else None
    hand = tuple(player.get("hand") or ())
    return hand[index] if isinstance(index, int) and 0 <= index < len(hand) else None


def _body(player: dict, option: dict | None):
    if option is None:
        return None
    area, index = option.get("inPlayArea"), option.get("inPlayIndex")
    if not isinstance(index, int) or index < 0:
        return None
    bodies = (player.get("active") or ()) if area == _ACTIVE else (
        (player.get("bench") or ()) if area == _BENCH else ())
    return bodies[index] if index < len(bodies) else None


def _card_token(card) -> str:
    if not card or card.get("id") is None:
        return "unknown"
    return str(int(card["id"]))


def _body_token(body, option: dict | None) -> str:
    if body and body.get("serial") is not None:
        return str(int(body["serial"]))
    return f"{option.get('inPlayArea', '?')}:{option.get('inPlayIndex', '?')}" if option else "?"


def action_footprint(state, action, *, effects=None, stats=None) -> ActionFootprint:
    """Build a portable dependency declaration from action structure and effect clauses.

    Returning a barrier is always safe: it merely forgoes reduction.  Only fully declared,
    deterministic effects are admitted.
    """
    observation = state.obs
    _seat, player = _actor_side(observation)
    option = _selected_option(observation, action)
    card = _hand_card(player, option)
    card_token = _card_token(card)
    body = _body(player, option)
    body_token = _body_token(body, option)
    kind = action.identity.kind

    if kind in OPAQUE_ACTION_KINDS:
        return ActionFootprint((kind, *map(str, action.identity.parts)), barrier=True)

    if kind == "attach":
        event = (kind, card_token, body_token)
        return ActionFootprint(
            event,
            frozenset({f"hand:{card_token}", "allowance:energy", "own:energy",
                       f"body:{body_token}:identity"}),
            frozenset({f"hand:{card_token}", "allowance:energy", "own:energy",
                       f"body:{body_token}:energy"}),
        )

    if kind == "evolve":
        event = (kind, card_token, body_token)
        body_identity = f"body:{body_token}:identity"
        return ActionFootprint(
            event,
            frozenset({f"hand:{card_token}", body_identity, "own:hp"}),
            frozenset({f"hand:{card_token}", body_identity, "own:hp"}),
        )

    if kind != "play" or not card or card.get("id") is None or effects is None:
        return ActionFootprint((kind, card_token), barrier=True)

    card_id = int(card["id"])
    clauses = tuple(effects.clauses(card_id))
    clause_kinds = frozenset(str(clause.get("kind", "")) for clause in clauses)
    if (not clause_kinds or clause_kinds & INFORMATION_EFFECT_KINDS
            or not clause_kinds <= DECLARED_DETERMINISTIC_EFFECT_KINDS):
        return ActionFootprint((kind, card_token), barrier=True)

    reads = {f"hand:{card_token}"}
    writes = {f"hand:{card_token}"}
    stat = stats.get(card_id) if stats is not None else None
    if stat is not None and getattr(stat, "is_supporter", False):
        reads.add("allowance:supporter")
        writes.add("allowance:supporter")
    if stat is not None and getattr(stat, "is_stadium", False):
        reads.add("allowance:stadium")
        writes.update(("allowance:stadium", "field:stadium"))

    if "gust" in clause_kinds:
        reads.add("opponent:lineup")
        writes.add("opponent:lineup")
    if "heal" in clause_kinds:
        reads.add("own:hp")
        writes.add("own:hp")
        riders = frozenset(str(clause.get("rider", "")) for clause in clauses)
        if "bounce_energy_to_hand" in riders:
            reads.add("own:energy")
            writes.add("own:energy")
    if "self_switch" in clause_kinds:
        reads.add("own:lineup")
        writes.add("own:lineup")
    if "damage_boost" in clause_kinds:
        reads.add("own:damage-modifiers")
        writes.add("own:damage-modifiers")
    if "stadium_static" in clause_kinds:
        writes.add("field:stadium")
    return ActionFootprint((kind, card_token), frozenset(reads), frozenset(writes))


__all__ = ("ActionFootprint", "action_footprint", "independent")
