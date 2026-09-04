"""Canonical rule-state identity for turn-search nodes."""
from __future__ import annotations

import hashlib
import json
from dataclasses import fields

from common.api import ActionIdentity

from ..engine import Engine
from ..state import GameState, PlayerBoard, PokemonInPlay
from .contracts import (SEARCH_STATE_KEY_SCHEMA_VERSION, BoundaryReason, NodeKind,
                        SearchContractError, SearchStateKey)


_SERIAL_FIELDS = frozenset({
    "attach_energy", "effect_card", "evo", "serial", "serialActive",
    "serialAfter", "serialBefore", "serialBench", "serialTarget", "source", "src",
})
_SERIAL_COLLECTION_FIELDS = frozenset({"answered_listing", "milled", "picked"})
_SEARCH_GAME_FIELDS = frozenset({
    "attach_seq", "attach_tick", "cards", "db", "energy_attached", "executed_chains",
    "first_player", "frames", "ko_turn", "last_posed", "looking", "looking_owner",
    "manual_coin", "outbox", "outbox_god", "parity_manifest", "pending",
    "pending_triggers", "phase", "phase_data", "players", "result", "result_reason",
    "retreated", "rng", "stadium", "stadium_played", "supporter_played", "turn",
    "turn_action_count", "turn_markers",
})


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def _serial_map(gs: GameState) -> dict[int, int]:
    ordered = []
    seen = set()

    def add(values):
        for value in values:
            if isinstance(value, int) and value in gs.cards and value not in seen:
                seen.add(value)
                ordered.append(value)

    def body(value: PokemonInPlay | None):
        if value is not None:
            add(value.stack)
            add(value.energy)
            add(value.tools)

    for board in gs.players:
        add(board.deck)
        add(board.hand)
        add(board.discard)
        add(board.prize)
        body(board.active)
        for value in board.bench:
            body(value)
    add(gs.stadium)
    add(gs.looking or ())
    if gs.pending is not None:
        add(gs.pending.deck_listing or ())
        add((gs.pending.context_card, gs.pending.effect_card))
    add(frame.source for frame in gs.frames)
    add(gs.attach_seq)
    remaining = sorted(
        (serial for serial in gs.cards if serial not in seen),
        key=lambda serial: (gs.cards[serial].owner, gs.cards[serial].card_id, serial),
    )
    add(remaining)
    return {serial: index for index, serial in enumerate(ordered)}


def _reference(value, serials: dict[int, int]):
    return None if value is None else serials[value]


def _references(values, serials: dict[int, int]):
    return tuple(serials[value] for value in values)


def _normalize(value, serials: dict[int, int], *, key: str | None = None):
    if key in _SERIAL_FIELDS and isinstance(value, int) and value in serials:
        return {"$card": serials[value]}
    if key in _SERIAL_COLLECTION_FIELDS:
        if isinstance(value, int) and value in serials:
            return {"$card": serials[value]}
        if isinstance(value, (list, tuple)):
            return tuple({"$card": serials[child]} if child in serials else child
                         for child in value)
    if isinstance(value, dict):
        return {str(child_key): _normalize(child, serials, key=str(child_key))
                for child_key, child in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple)):
        return tuple(_normalize(child, serials) for child in value)
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise SearchContractError(f"unsupported Search State value {type(value).__name__}")


def _pokemon(value: PokemonInPlay | None, serials: dict[int, int]):
    if value is None:
        return None
    serial_fields = {"stack", "energy", "tools"}
    return {
        item.name: (_references(getattr(value, item.name), serials)
                    if item.name in serial_fields
                    else _normalize(getattr(value, item.name), serials, key=item.name))
        for item in fields(PokemonInPlay)
    }


def _player(value: PlayerBoard, serials: dict[int, int]):
    zones = {"deck", "hand", "discard", "prize"}
    result = {}
    for item in fields(PlayerBoard):
        child = getattr(value, item.name)
        if item.name in zones:
            result[item.name] = _references(child, serials)
        elif item.name == "active":
            result[item.name] = _pokemon(child, serials)
        elif item.name == "bench":
            result[item.name] = tuple(_pokemon(body, serials) for body in child)
        else:
            result[item.name] = _normalize(child, serials, key=item.name)
    return result


def _pending(value, serials: dict[int, int]):
    if value is None:
        return None
    return {
        "seat": value.seat, "type": value.type, "context": value.context,
        "min_count": value.min_count, "max_count": value.max_count,
        "options": _normalize(value.options, serials),
        "remain_damage_counter": value.remain_damage_counter,
        "remain_energy_cost": value.remain_energy_cost,
        "deck_listing": (None if value.deck_listing is None
                         else _references(value.deck_listing, serials)),
        "context_card": _reference(value.context_card, serials),
        "effect_card": _reference(value.effect_card, serials),
    }


def _state_projection(gs: GameState):
    actual = frozenset(item.name for item in fields(GameState))
    if actual != _SEARCH_GAME_FIELDS:
        raise SearchContractError("GameState field inventory changed")
    serials = _serial_map(gs)
    cards = tuple(
        (serials[serial], card.card_id, card.owner)
        for serial, card in sorted(gs.cards.items(), key=lambda item: serials[item[0]])
    )
    frames_payload = tuple({
        "program": _normalize(frame.program, serials),
        "pc": frame.pc,
        "vars": _normalize(frame.vars, serials),
        "seat": frame.seat,
        "source": _reference(frame.source, serials),
        "kind": frame.kind,
    } for frame in gs.frames)
    return {
        "cards": cards,
        "players": tuple(_player(board, serials) for board in gs.players),
        "turn": gs.turn,
        "turn_action_count": gs.turn_action_count,
        "first_player": gs.first_player,
        "supporter_played": gs.supporter_played,
        "stadium_played": gs.stadium_played,
        "energy_attached": gs.energy_attached,
        "retreated": gs.retreated,
        "result": gs.result,
        "result_reason": gs.result_reason,
        "stadium": _references(gs.stadium, serials),
        "turn_markers": _normalize(gs.turn_markers, serials),
        "ko_turn": tuple(gs.ko_turn),
        "attach_seq": tuple(sorted(
            (serials[serial], tick) for serial, tick in gs.attach_seq.items())),
        "attach_tick": gs.attach_tick,
        "looking": None if gs.looking is None else _references(gs.looking, serials),
        "looking_owner": gs.looking_owner,
        "pending": _pending(gs.pending, serials),
        "frames": frames_payload,
        "pending_triggers": _normalize(gs.pending_triggers, serials),
        "last_posed": tuple(gs.last_posed),
        "phase": gs.phase,
        "phase_data": _normalize(gs.phase_data, serials),
        "manual_coin": gs.manual_coin,
    }


def search_state_key(engine: Engine, kind: NodeKind, actor_seat: int | None,
                     perspective_seat: int, root_turn: int,
                     boundary_reason: BoundaryReason | None, *,
                     continuation=None, observation_key: str | None = None) -> SearchStateKey:
    payload = {
        "schema_version": SEARCH_STATE_KEY_SCHEMA_VERSION,
        "state": _state_projection(engine.gs),
        "node": {
            "kind": kind.value, "actor_seat": actor_seat,
            "perspective_seat": perspective_seat, "root_turn": root_turn,
            "boundary_reason": (None if boundary_reason is None
                                else boundary_reason.value),
            "continuation": continuation,
            "observation_key": observation_key,
        },
    }
    return SearchStateKey(hashlib.sha256(_canonical(payload)).hexdigest())


def unavailable_state_key(parent: SearchStateKey, action: ActionIdentity,
                          failure_type: str) -> SearchStateKey:
    payload = {
        "schema_version": SEARCH_STATE_KEY_SCHEMA_VERSION,
        "parent": parent.digest,
        "action": [action.kind, action.parts],
        "kind": NodeKind.UNAVAILABLE.value,
        "failure_type": failure_type,
    }
    return SearchStateKey(hashlib.sha256(_canonical(payload)).hexdigest())


def turn_boundary_state_key(*, perspective_seat: int, root_turn: int,
                            observation_key: str) -> SearchStateKey:
    payload = {
        "schema_version": SEARCH_STATE_KEY_SCHEMA_VERSION,
        "node": {
            "kind": NodeKind.TURN_BOUNDARY.value,
            "perspective_seat": perspective_seat,
            "root_turn": root_turn,
            "boundary_reason": BoundaryReason.TURN_TRANSITION.value,
            "observation_key": observation_key,
        },
    }
    return SearchStateKey(hashlib.sha256(_canonical(payload)).hexdigest())


__all__ = ("search_state_key", "turn_boundary_state_key", "unavailable_state_key")
