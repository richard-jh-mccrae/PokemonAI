"""Canonical immutable state for Bellman search."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
import hashlib
import json
from typing import Mapping


def freeze(value):
    if isinstance(value, Mapping):
        return tuple((str(key), freeze(child)) for key, child in
                     sorted(value.items(), key=lambda item: str(item[0])))
    if isinstance(value, (list, tuple)):
        return tuple(freeze(child) for child in value)
    if isinstance(value, (set, frozenset)):
        return tuple(sorted((freeze(child) for child in value), key=repr))
    return value


def thaw(value):
    if isinstance(value, tuple):
        if all(isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], str)
               for item in value):
            return {key: thaw(child) for key, child in value}
        return [thaw(child) for child in value]
    return value


@dataclass(frozen=True)
class TurnBudgets:
    supporter: bool
    manual_attach: bool
    retreat: bool
    ability: tuple[int, ...]
    attack: bool
    stadium: bool

    @classmethod
    def from_observation(cls, observation: Mapping) -> "TurnBudgets":
        current = observation.get("current") or {}
        return cls(
            supporter=not bool(current.get("supporterPlayed")),
            manual_attach=not bool(current.get("energyAttached")),
            retreat=not bool(current.get("retreated")),
            ability=tuple(sorted(int(serial) for serial in
                                 (current.get("abilityUsedBodies") or ()))),
            attack=True,
            stadium=not bool(current.get("stadiumPlayed")),
        )


@dataclass(frozen=True)
class OpponentBelief:
    visible: tuple
    archetypes: tuple[tuple[str, float], ...] = ()
    properties: tuple[tuple[str, object], ...] = ()
    unknown_mass: float = 1.0

    def __post_init__(self) -> None:
        if not 0.0 <= float(self.unknown_mass) <= 1.0:
            raise ValueError("unknown belief mass must be in [0, 1]")
        total = self.unknown_mass + sum(float(prob) for _name, prob in self.archetypes)
        if not 0.999999 <= total <= 1.000001:
            raise ValueError("belief probability mass must sum to one")


def _visible_own_ids(observation: Mapping, seat: int) -> Counter:
    current = observation.get("current") or {}
    players = current.get("players") or ()
    player = players[seat] if 0 <= seat < len(players) and players[seat] else {}
    ids = Counter()
    for zone in ("hand", "discard"):
        ids.update(int(card["id"]) for card in (player.get(zone) or ()) if card)
    for body in (player.get("active") or ()) + (player.get("bench") or ()):
        if not body:
            continue
        ids[int(body["id"])] += 1
        ids.update(int(card["id"]) for card in (body.get("preEvolution") or ()) if card)
        ids.update(int(card["id"]) for card in (body.get("energyCards") or ()) if card)
        ids.update(int(card["id"]) for card in (body.get("tools") or ()) if card)
    for card in current.get("stadium") or ():
        if card and int(card.get("playerIndex", seat)) == seat:
            ids[int(card["id"])] += 1
    return ids


@dataclass(frozen=True)
class DecisionState:
    observation: tuple
    root_seat: int
    deck_name: str
    deck: tuple[int, ...]
    deck_counts: tuple[tuple[int, int], ...]
    prize_counts: tuple[tuple[int, int], ...]
    budgets: TurnBudgets
    belief: OpponentBelief
    value_registry_identity: str

    @classmethod
    def from_observation(cls, observation: Mapping, *, deck: tuple[int, ...], deck_name: str,
                         belief: OpponentBelief | None = None,
                         value_registry_identity: str = "bellman-seeds-v1") -> "DecisionState":
        current = observation.get("current") or {}
        seat = int(current.get("yourIndex", 0))
        raw_prizes = observation.get("own_prizes") or {}
        prizes = Counter({int(card_id): int(count) for card_id, count in raw_prizes.items()})
        remaining = Counter(int(card_id) for card_id in deck)
        remaining.subtract(_visible_own_ids(observation, seat))
        remaining.subtract(prizes)
        remaining = Counter({card_id: count for card_id, count in remaining.items() if count > 0})
        players = current.get("players") or ()
        opponent = players[1 - seat] if len(players) > 1 and players[1 - seat] else {}
        if belief is None:
            belief = OpponentBelief(visible=freeze(opponent), unknown_mass=1.0)
        return cls(
            observation=freeze(dict(observation)), root_seat=seat, deck_name=str(deck_name),
            deck=tuple(int(card_id) for card_id in deck), deck_counts=tuple(sorted(remaining.items())),
            prize_counts=tuple(sorted(prizes.items())), budgets=TurnBudgets.from_observation(observation),
            belief=belief, value_registry_identity=str(value_registry_identity),
        )

    @property
    def obs(self) -> dict:
        return thaw(self.observation)

    @property
    def semantic_key(self) -> str:
        payload = freeze((self.observation, self.root_seat, self.deck_name, self.deck_counts,
                          self.prize_counts, self.budgets, self.belief,
                          self.value_registry_identity))
        return hashlib.sha256(repr(payload).encode("utf-8")).hexdigest()

    def with_observation(self, observation: Mapping) -> "DecisionState":
        successor = type(self).from_observation(
            observation, deck=self.deck, deck_name=self.deck_name, belief=self.belief,
            value_registry_identity=self.value_registry_identity)
        return replace(successor, root_seat=self.root_seat)


__all__ = ("DecisionState", "OpponentBelief", "TurnBudgets", "freeze", "thaw")
