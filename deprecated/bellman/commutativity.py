"""Conservative action footprints for Bellman partial-order reduction.

Footprints declare state dependencies, not desirability.  Two deterministic actions may be placed in
one canonical order only when neither writes a resource read or written by the other.  Unknown,
information-revealing, and random effects are barriers by construction.
"""
from __future__ import annotations

from dataclasses import dataclass

from common.cards import card_store, play_clauses
from common.cards.card_facts import STADIUM, SUPPORTER, TrainerCard
from common.cards.functions.fetch import REACH, fetch_target_matches
from common.strategy.context import _ACTIVE, _BENCH


INFORMATION_EFFECT_KINDS = frozenset({"coin", "draw", "fetch", "energy_recur", "accel"})
DECLARED_DETERMINISTIC_EFFECT_KINDS = frozenset({
    "damage_boost", "gust", "heal", "self_switch", "stadium_static",
})
OPAQUE_ACTION_KINDS = frozenset({
    "ability", "attack", "card", "decline", "discard", "end", "energy", "energy_card",
    "number", "skill", "special_condition", "tool_card", "yes", "no",
})


@dataclass(frozen=True)
class ActionFootprint:
    """Stable event identity plus the abstract resources it reads and writes."""

    event: tuple[str, ...]
    reads: frozenset[str] = frozenset()
    writes: frozenset[str] = frozenset()
    barrier: bool = False
    information_first: bool = False
    commitment: bool = False


def independent(left: ActionFootprint, right: ActionFootprint) -> bool:
    """Whether either fixed action order reaches the same information and state boundary."""
    if left.barrier or right.barrier or left.event == right.event:
        return False
    return not (
        left.writes & (right.reads | right.writes)
        or right.writes & (left.reads | left.writes)
    )


def information_precedes(information: ActionFootprint, commitment: ActionFootprint) -> bool:
    return (information.event != commitment.event and information.information_first
            and commitment.commitment)


def _pure_hidden_fetch(clauses) -> bool:
    prohibited = {"cost", "cost_required", "rider", "trigger"}
    return bool(clauses) and all(
        clause.kind == "fetch" and clause.zone == "deck"
        and (clause.dest or "hand") == "hand"
        and not prohibited.intersection(clause.params)
        for clause in clauses)


def _dead_bench_fetch(state, player: dict, clauses, cards) -> bool:
    bench_clauses = tuple(
        clause for clause in clauses
        if clause.kind == "fetch" and clause.zone == "deck"
        and clause.dest == "bench"
    )
    if not bench_clauses or len(bench_clauses) != len(clauses):
        return False
    if len(player.get("bench") or ()) >= int(player.get("benchMax", 5)):
        return True
    deck_counts = tuple(getattr(state, "deck_counts", ()))
    if not deck_counts:
        return False
    return not any(
        count > 0 and fetch_target_matches(clause, cards.get(int(card_id)), reading=REACH)
        for clause in bench_clauses
        for card_id, count in deck_counts
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


def action_footprint(state, action, *, cards=None) -> ActionFootprint:
    """Build dependencies from action structure; uncertain declarations become barriers."""
    cards = card_store() if cards is None else cards
    observation = state.obs
    _seat, player = _actor_side(observation)
    option = _selected_option(observation, action)
    card = _hand_card(player, option)
    card_token = _card_token(card)
    body = _body(player, option)
    body_token = _body_token(body, option)
    kind = action.identity.kind

    if kind in OPAQUE_ACTION_KINDS:
        return ActionFootprint((kind, *map(str, action.identity.parts)), barrier=True,
                               commitment=kind in {"attack", "retreat"})

    if kind == "attach":
        event = (kind, card_token, body_token)
        return ActionFootprint(
            event,
            frozenset({f"hand:{card_token}", "allowance:energy",
                       f"body:{body_token}:identity"}),
            frozenset({f"hand:{card_token}", "allowance:energy",
                       f"body:{body_token}:energy"}),
            commitment=True,
        )

    if kind == "evolve":
        event = (kind, card_token, body_token)
        body_identity = f"body:{body_token}:identity"
        target = cards.get(int(card["id"])) if card and card.get("id") is not None else None
        if target is not None and getattr(target, "has_ability", False):
            return ActionFootprint(event, barrier=True, commitment=True)
        return ActionFootprint(
            event,
            frozenset({f"hand:{card_token}", body_identity, f"body:{body_token}:hp"}),
            frozenset({f"hand:{card_token}", f"body:{body_token}:card",
                       body_identity, f"body:{body_token}:hp"}),
            commitment=True,
        )

    if kind == "retreat":
        active = (player.get("active") or ())
        active_body = active[0] if active else None
        active_token = _body_token(active_body, None)
        lineup = tuple(active) + tuple(player.get("bench") or ())
        lineup_identities = {
            f"body:{_body_token(candidate, None)}:identity" for candidate in lineup
        }
        return ActionFootprint(
            (kind, body_token),
            frozenset({"allowance:retreat", "own:lineup",
                       f"body:{active_token}:energy", f"body:{body_token}:identity",
                       *lineup_identities}),
            frozenset({"allowance:retreat", "own:lineup", f"body:{active_token}:energy"}),
            commitment=True,
        )

    if kind != "play" or not card or card.get("id") is None:
        return ActionFootprint((kind, card_token), barrier=True)

    card_id = int(card["id"])
    record = cards.get(card_id)
    clauses = play_clauses(record)
    is_supporter = isinstance(record, TrainerCard) and record.kind == SUPPORTER
    is_stadium = isinstance(record, TrainerCard) and record.kind == STADIUM
    consumes_allowance = is_supporter or is_stadium
    dead_bench_fetch = _dead_bench_fetch(state, player, clauses, cards)
    spends_resources = any(
        clause.cost or clause.cost_required for clause in clauses
    )
    if _pure_hidden_fetch(clauses) and not consumes_allowance:
        return ActionFootprint((kind, card_token), barrier=True, information_first=True)
    clause_kinds = frozenset(str(clause.kind) for clause in clauses)
    if (not clause_kinds or clause_kinds & INFORMATION_EFFECT_KINDS
            or not clause_kinds <= DECLARED_DETERMINISTIC_EFFECT_KINDS):
        return ActionFootprint((kind, card_token), barrier=True,
                               commitment=consumes_allowance or dead_bench_fetch
                               or spends_resources)

    reads = {f"hand:{card_token}"}
    writes = {f"hand:{card_token}"}
    if is_supporter:
        reads.add("allowance:supporter")
        writes.add("allowance:supporter")
    if is_stadium:
        reads.add("allowance:stadium")
        writes.update(("allowance:stadium", "field:stadium"))

    if "gust" in clause_kinds:
        reads.add("opponent:lineup")
        writes.add("opponent:lineup")
    if "heal" in clause_kinds:
        reads.add("own:hp")
        writes.add("own:hp")
        riders = frozenset(str(clause.rider or "") for clause in clauses)
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
    return ActionFootprint((kind, card_token), frozenset(reads), frozenset(writes),
                           commitment=True)


__all__ = ("ActionFootprint", "action_footprint", "independent", "information_precedes")
