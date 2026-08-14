"""Canonical immutable state for Bellman search."""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, replace
from functools import cached_property
import hashlib


PROBABILITY_MIN = 0.0
PROBABILITY_MAX = 1.0
BELIEF_MASS_TOLERANCE = 1e-6
DEFAULT_ROOT_SEAT = 0
FROZEN_TAGGED_PAIR_LENGTH = 2
SEMANTICALLY_VOLATILE_KEYS = frozenset({
    "logs", "name", "remainingOverageTime", "serial", "step",
    "turnActionCount",
})
UNORDERED_PLAYER_ZONES = ("hand", "discard")


def freeze(value):
    # Observations are built-in containers.  Test exact types first: ``typing.Mapping`` performs
    # an expensive ABC/subclass walk at every leaf, and a single search freezes millions of leaves.
    value_type = type(value)
    if value_type is dict:
        return ("__map__", tuple((str(key), freeze(child)) for key, child in
                                 sorted(value.items(), key=lambda item: str(item[0]))))
    if value_type is list:
        return ("__list__", tuple(freeze(child) for child in value))
    if value_type is tuple:
        return ("__tuple__", tuple(freeze(child) for child in value))
    if value_type is set or value_type is frozenset:
        return ("__set__", tuple(sorted((freeze(child) for child in value), key=repr)))
    if isinstance(value, Mapping):
        return ("__map__", tuple((str(key), freeze(child)) for key, child in
                                 sorted(value.items(), key=lambda item: str(item[0]))))
    return value


def thaw(value):
    if (isinstance(value, tuple) and len(value) == FROZEN_TAGGED_PAIR_LENGTH
            and value[0] == "__map__"):
        return {key: thaw(child) for key, child in value[1]}
    if (isinstance(value, tuple) and len(value) == FROZEN_TAGGED_PAIR_LENGTH
            and value[0] == "__list__"):
        return [thaw(child) for child in value[1]]
    if (isinstance(value, tuple) and len(value) == FROZEN_TAGGED_PAIR_LENGTH
            and value[0] == "__tuple__"):
        return tuple(thaw(child) for child in value[1])
    if (isinstance(value, tuple) and len(value) == FROZEN_TAGGED_PAIR_LENGTH
            and value[0] == "__set__"):
        return set(thaw(child) for child in value[1])
    return value


def _semantic(value):
    """Remove observation history/labels while preserving every rule-relevant state field."""
    if isinstance(value, Mapping):
        return {key: _semantic(child) for key, child in value.items()
                if key not in SEMANTICALLY_VOLATILE_KEYS}
    if isinstance(value, list):
        return [_semantic(child) for child in value]
    if isinstance(value, tuple):
        return tuple(_semantic(child) for child in value)
    return value


def _semantic_observation(observation: Mapping):
    normalized = _semantic(observation)
    current = normalized.get("current") or {}
    if normalized.get("bellmanActor") == current.get("yourIndex"):
        normalized.pop("bellmanActor", None)
    for player in current.get("players") or ():
        if not isinstance(player, dict):
            continue
        player.pop("deck", None)
        for zone in UNORDERED_PLAYER_ZONES:
            cards = player.get(zone)
            if isinstance(cards, list):
                player[zone] = sorted(cards, key=lambda card: repr(freeze(card)))
        bench = player.get("bench")
        if isinstance(bench, list):
            player["bench"] = sorted(bench, key=lambda body: repr(freeze(body)))
    looking = current.get("looking")
    if isinstance(looking, list):
        current["looking"] = sorted(looking, key=lambda card: repr(freeze(card)))
    select = normalized.get("select")
    if isinstance(select, dict):
        select.pop("option", None)
        select.pop("deck", None)
    return normalized


def _plan_observation(observation: Mapping):
    normalized = _semantic_observation(observation)
    normalized.pop("search_begin_input", None)
    return normalized


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
    unknown_mass: float = PROBABILITY_MAX

    def __post_init__(self) -> None:
        if not PROBABILITY_MIN <= float(self.unknown_mass) <= PROBABILITY_MAX:
            raise ValueError("unknown belief mass must be in [0, 1]")
        total = self.unknown_mass + sum(float(prob) for _name, prob in self.archetypes)
        if not PROBABILITY_MAX - BELIEF_MASS_TOLERANCE <= total <= PROBABILITY_MAX + BELIEF_MASS_TOLERANCE:
            raise ValueError("belief probability mass must sum to one")


def _visible_own_ids(observation: Mapping, seat: int) -> Counter:
    current = observation.get("current") or {}
    players = current.get("players") or ()
    player = players[seat] if 0 <= seat < len(players) and players[seat] else {}
    ids = Counter()
    for zone in ("hand", "discard"):
        ids.update(int(card["id"]) for card in (player.get(zone) or ()) if card)
    for body in tuple(player.get("active") or ()) + tuple(player.get("bench") or ()):
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
        seat = int(current.get("yourIndex", DEFAULT_ROOT_SEAT))
        raw_prizes = observation.get("own_prizes") or {}
        prizes = Counter({int(card_id): int(count) for card_id, count in raw_prizes.items()})
        remaining = Counter(int(card_id) for card_id in deck)
        remaining.subtract(_visible_own_ids(observation, seat))
        remaining.subtract(prizes)
        remaining = Counter({card_id: count for card_id, count in remaining.items() if count > 0})
        players = current.get("players") or ()
        opponent = players[1 - seat] if len(players) > 1 and players[1 - seat] else {}
        if belief is None:
            belief = OpponentBelief(visible=freeze(opponent), unknown_mass=PROBABILITY_MAX)
        return cls(
            observation=freeze(dict(observation)), root_seat=seat, deck_name=str(deck_name),
            deck=tuple(int(card_id) for card_id in deck), deck_counts=tuple(sorted(remaining.items())),
            prize_counts=tuple(sorted(prizes.items())), budgets=TurnBudgets.from_observation(observation),
            belief=belief, value_registry_identity=str(value_registry_identity),
        )

    @cached_property
    def obs(self) -> dict:
        return thaw(self.observation)

    @cached_property
    def semantic_key(self) -> str:
        from .options import enumerate_legal_actions

        legal = tuple(action.identity for action in enumerate_legal_actions(self.obs))
        payload = (freeze(_semantic_observation(self.obs)), legal,
                   self.root_seat, self.deck_name, self.deck_counts,
                   self.prize_counts, self.budgets, self.belief,
                   self.value_registry_identity)
        return hashlib.sha256(repr(payload).encode("utf-8")).hexdigest()

    @cached_property
    def plan_key(self) -> str:
        from .options import enumerate_legal_actions

        legal = tuple(action.identity for action in enumerate_legal_actions(self.obs))
        payload = (freeze(_plan_observation(self.obs)), legal,
                   self.root_seat, self.deck_name, self.deck_counts,
                   self.prize_counts, self.budgets, self.belief,
                   self.value_registry_identity)
        return hashlib.sha256(repr(payload).encode("utf-8")).hexdigest()

    @cached_property
    def legal_menu_digest(self) -> str:
        from .options import enumerate_legal_actions

        identities = tuple(action.identity for action in enumerate_legal_actions(self.obs))
        return hashlib.sha256(repr(identities).encode("utf-8")).hexdigest()

    def with_observation(self, observation: Mapping) -> "DecisionState":
        successor = type(self).from_observation(
            observation, deck=self.deck, deck_name=self.deck_name, belief=self.belief,
            value_registry_identity=self.value_registry_identity)
        return replace(successor, root_seat=self.root_seat)


__all__ = ("DecisionState", "OpponentBelief", "TurnBudgets", "freeze", "thaw")
