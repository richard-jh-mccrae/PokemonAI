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
SUBTREE_DIGEST_BYTES = 16


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


# --- Incremental semantic hashing -------------------------------------------------------------
#
# The state keys used to be built by copying the observation three times (semantic strip, freeze,
# repr) and hashing the final string.  Those intermediate trees were built once per search node and
# thrown away immediately.  The writers below feed the hash directly from the observation in one
# walk, allocating nothing but per-card digests for the order-free zones.  Only key *equality*
# matters to any consumer, so the byte layout is free to differ from the old repr form; what must
# be preserved exactly is which observations compare equal, and the skip/sort rules below mirror
# ``_semantic_observation`` rule for rule.


def _feed(update, value):
    value_type = type(value)
    if value_type is str:
        data = value.encode("utf-8", "surrogatepass")
        update(b"S%d:" % len(data))
        update(data)
    elif value_type is int:
        update(b"I%d;" % value)
    elif value_type is bool:
        update(b"B1" if value else b"B0")
    elif value_type is float:
        update(b"F")
        update(repr(value).encode("ascii"))
        update(b";")
    elif value is None:
        update(b"N")
    elif value_type is dict:
        update(b"{")
        for key in sorted(value, key=str):
            if key in SEMANTICALLY_VOLATILE_KEYS:
                continue
            update(b"K")
            _feed(update, str(key))
            _feed(update, value[key])
        update(b"}")
    elif value_type is list:
        update(b"[")
        for child in value:
            _feed(update, child)
        update(b"]")
    elif value_type is tuple:
        update(b"(")
        for child in value:
            _feed(update, child)
        update(b")")
    elif value_type is set or value_type is frozenset:
        _feed_unordered(update, value)
    elif isinstance(value, Mapping):
        update(b"{")
        for key in sorted(value, key=str):
            if key in SEMANTICALLY_VOLATILE_KEYS:
                continue
            update(b"K")
            _feed(update, str(key))
            _feed(update, value[key])
        update(b"}")
    else:
        update(b"O")
        update(repr(value).encode("utf-8", "surrogatepass"))
        update(b";")


def _subtree_digest(value) -> bytes:
    hasher = hashlib.blake2b(digest_size=SUBTREE_DIGEST_BYTES)
    _feed(hasher.update, value)
    return hasher.digest()


def _feed_unordered(update, items):
    update(b"<")
    for digest in sorted(_subtree_digest(child) for child in items):
        update(digest)
    update(b">")


def _feed_mapping(update, value, skip):
    update(b"{")
    for key in sorted(value, key=str):
        if key in SEMANTICALLY_VOLATILE_KEYS or key in skip:
            continue
        update(b"K")
        _feed(update, str(key))
        _feed(update, value[key])
    update(b"}")


def _feed_player(update, player):
    update(b"{")
    for key in sorted(player, key=str):
        if key in SEMANTICALLY_VOLATILE_KEYS or key == "deck":
            continue
        update(b"K")
        _feed(update, str(key))
        child = player[key]
        if (key == "bench" or key in UNORDERED_PLAYER_ZONES) and type(child) is list:
            _feed_unordered(update, child)
        else:
            _feed(update, child)
    update(b"}")


def _feed_current(update, current):
    update(b"{")
    for key in sorted(current, key=str):
        if key in SEMANTICALLY_VOLATILE_KEYS:
            continue
        update(b"K")
        _feed(update, str(key))
        child = current[key]
        if key == "players" and type(child) is list:
            update(b"[")
            for player in child:
                if type(player) is dict:
                    _feed_player(update, player)
                else:
                    _feed(update, player)
            update(b"]")
        elif key == "looking" and type(child) is list:
            _feed_unordered(update, child)
        else:
            _feed(update, child)
    update(b"}")


def _feed_semantic_observation(update, observation):
    """Mirror ``_semantic_observation``: volatile keys, hidden zones, and label noise never reach
    the hash; order-free zones contribute as sorted per-card digests.  ``search_begin_input`` is
    deliberately absent here — the key builder appends it separately so the plan key can omit it."""
    current = observation.get("current")
    your_index = current.get("yourIndex") if type(current) is dict else None
    drop_actor = observation.get("bellmanActor") == your_index
    update(b"{")
    for key in sorted(observation, key=str):
        if key in SEMANTICALLY_VOLATILE_KEYS or key == "search_begin_input":
            continue
        if key == "bellmanActor" and drop_actor:
            continue
        update(b"K")
        _feed(update, str(key))
        child = observation[key]
        if key == "current" and type(child) is dict:
            _feed_current(update, child)
        elif key == "select" and type(child) is dict:
            _feed_mapping(update, child, ("option", "deck"))
        else:
            _feed(update, child)
    update(b"}")


_BELIEF_DIGEST_CACHE: dict[int, tuple[object, bytes]] = {}
_BELIEF_DIGEST_CACHE_LIMIT = 64


def _belief_digest(belief) -> bytes:
    """One belief object is shared by every state in a search; digest it once per object."""
    entry = _BELIEF_DIGEST_CACHE.get(id(belief))
    if entry is not None and entry[0] is belief:
        return entry[1]
    if len(_BELIEF_DIGEST_CACHE) >= _BELIEF_DIGEST_CACHE_LIMIT:
        _BELIEF_DIGEST_CACHE.clear()
    hasher = hashlib.blake2b(digest_size=SUBTREE_DIGEST_BYTES)
    _feed(hasher.update,
          (belief.visible, belief.archetypes, belief.properties, float(belief.unknown_mass)))
    digest = hasher.digest()
    _BELIEF_DIGEST_CACHE[id(belief)] = (belief, digest)
    return digest


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
    def legal_actions(self) -> tuple:
        """The state's legal moves, enumerated once.  The keys below, the menu digest, and every
        transition provider ask for the same menu, and it depends on nothing but ``obs``."""
        from .options import enumerate_legal_actions

        return enumerate_legal_actions(self.obs)

    @cached_property
    def action_scratch(self) -> dict:
        """Per-state scratch for pure per-(state, action) derivations (e.g. solver footprints).

        Living on the state, the scratch dies with the state — a solver-side table keyed by state
        identity would either pin every explored state for a whole decision or risk stale ids.
        """
        return {}

    @cached_property
    def _state_keys(self) -> tuple[str, str]:
        """``(semantic_key, plan_key)`` from one observation walk.

        Both keys hash identical material except ``search_begin_input``, which only the semantic
        key sees.  The shared prefix is hashed once and forked with ``hasher.copy()``.
        """
        hasher = hashlib.sha256()
        update = hasher.update
        obs = self.obs
        _feed_semantic_observation(update, obs)
        for action in self.legal_actions:
            identity = action.identity
            update(b"A")
            _feed(update, identity.kind)
            _feed(update, identity.parts)
        _feed(update, (self.root_seat, self.deck_name, self.deck_counts, self.prize_counts))
        budgets = self.budgets
        _feed(update, (budgets.supporter, budgets.manual_attach, budgets.retreat,
                       budgets.ability, budgets.attack, budgets.stadium))
        update(_belief_digest(self.belief))
        _feed(update, self.value_registry_identity)
        plan_key = hasher.hexdigest()
        if "search_begin_input" in obs:
            update(b"SBI")
            _feed(update, obs["search_begin_input"])
            return hasher.hexdigest(), plan_key
        return plan_key, plan_key

    @property
    def semantic_key(self) -> str:
        return self._state_keys[0]

    @property
    def plan_key(self) -> str:
        return self._state_keys[1]

    @cached_property
    def legal_menu_digest(self) -> str:
        hasher = hashlib.sha256()
        for action in self.legal_actions:
            identity = action.identity
            hasher.update(b"A")
            _feed(hasher.update, identity.kind)
            _feed(hasher.update, identity.parts)
        return hasher.hexdigest()

    def with_observation(self, observation: Mapping) -> "DecisionState":
        successor = type(self).from_observation(
            observation, deck=self.deck, deck_name=self.deck_name, belief=self.belief,
            value_registry_identity=self.value_registry_identity)
        return replace(successor, root_seat=self.root_seat)


__all__ = ("DecisionState", "OpponentBelief", "TurnBudgets", "freeze", "thaw")
