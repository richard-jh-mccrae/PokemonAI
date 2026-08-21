from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Mapping

from common.cards import card_clauses, card_store
from common.cards.card_facts import EnergyCard, PokemonCard
from common.cards.pokemon_roles import POKEMON_ROLES, undeclared_pokemon_roles
from common.observation import ObservationState
from common.scouting.pokemon_roles import general_pokemon_roles
from common.scouting.scorer import posterior


def _roles(values) -> Mapping[int, tuple[str, ...]]:
    normalized = {int(card_id): tuple(dict.fromkeys(roles))
                  for card_id, roles in (values or {}).items()}
    unknown = undeclared_pokemon_roles(
        role for roles in normalized.values() for role in roles)
    if unknown:
        raise KeyError(f"unknown Pokemon Role {unknown[0]!r}")
    return MappingProxyType(dict(sorted(normalized.items())))


def _probabilities(values) -> Mapping[int, float]:
    normalized = {int(card_id): float(value)
                  for card_id, value in (values or {}).items()}
    if any(not math.isfinite(value) or not 0.0 <= value <= 1.0
           for value in normalized.values()):
        raise ValueError("opponent card probabilities must be finite and between zero and one")
    return MappingProxyType(dict(sorted(normalized.items())))


def _identity(value) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.blake2b(payload.encode("utf-8"), digest_size=16).hexdigest()


@dataclass(frozen=True, slots=True)
class OpponentTrait:
    name: str
    value: bool | str


@dataclass(frozen=True, slots=True)
class OpponentMechanic:
    name: str
    probability: float

    def __post_init__(self):
        probability = float(self.probability)
        if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
            raise ValueError("opponent mechanic probability must be finite and bounded")
        object.__setattr__(self, "probability", probability)


_TRAIT_TYPES = {
    "deckout_vulnerability": bool,
    "heal_wall": bool,
    "opening_fragility": bool,
    "setup_dependency": (list, tuple),
    "tempo": str,
}
_TEMPO = frozenset({"fast", "midrange", "slow"})
_MECHANICS = frozenset({
    "comeback_disruption", "damage_cap", "effect_immunity", "hand_size_attack",
    "item_lock", "no_pivot", "piercing", "single_prize", "special_energy_only",
    "spread",
})


def _traits(claims) -> tuple[OpponentTrait, ...]:
    compiled = []
    for name, value in (claims or {}).items():
        if name not in _TRAIT_TYPES:
            raise KeyError(f"unknown opponent Trait {name!r}")
        if not isinstance(value, _TRAIT_TYPES[name]):
            raise TypeError(f"opponent Trait {name!r} has invalid value type")
        values = tuple(value) if name == "setup_dependency" else (value,)
        for item in values:
            if name == "tempo" and item not in _TEMPO:
                raise ValueError(f"opponent Trait 'tempo' requires one of {sorted(_TEMPO)}")
            if name == "setup_dependency" and item not in POKEMON_ROLES:
                raise KeyError(f"unknown Pokemon Role {item!r}")
            compiled.append(OpponentTrait(name, item))
    return tuple(sorted(compiled, key=lambda item: (item.name, str(item.value))))


def _mechanics(resources) -> tuple[OpponentMechanic, ...]:
    store = card_store()
    present = {int(card_id): float(probability) for card_id, probability in resources.items()
               if float(probability) > 0.0 and int(card_id) in store}
    by_name: dict[str, float] = {}

    def add(name, probability):
        by_name[name] = max(by_name.get(name, 0.0), float(probability))

    for card_id, probability in present.items():
        record = store[card_id]
        clauses = card_clauses(record)
        kinds = {clause.kind for clause in clauses}
        if "item_lock" in kinds:
            add("item_lock", probability)
        if "ignores_effects" in kinds:
            add("piercing", probability)
        if "prevent_effects" in kinds:
            add("effect_immunity", probability)
        if any(clause.kind == "prevent_damage"
               and str(clause.params.get("condition", "")).startswith("damage_")
               for clause in clauses):
            add("damage_cap", probability)
        if any(clause.kind == "damage_counters"
               and clause.params.get("per") == "card_in_own_hand" for clause in clauses):
            add("hand_size_attack", probability)
        if ("bench_spread" in kinds
                or any(clause.kind == "damage_counters"
                       and clause.params.get("target") in {"opp_bench", "opp_any"}
                       for clause in clauses)):
            add("spread", probability)
        if any(clause.kind == "draw"
               and clause.params.get("condition") == "pokemon_ko_last_turn"
               and clause.params.get("rider") == "shuffle_both_hands"
               for clause in clauses):
            add("comeback_disruption", probability)

    pokemon = [store[card_id] for card_id in present
               if isinstance(store[card_id], PokemonCard)]
    if pokemon and all(card.prize_value == 1 for card in pokemon):
        add("single_prize", 1.0)
    energies = [store[card_id] for card_id in present
                if isinstance(store[card_id], EnergyCard)]
    if energies and all(card.kind == "special_energy" for card in energies):
        add("special_energy_only", 1.0)
    mobility = max((probability for card_id, probability in present.items()
                    if {clause.kind for clause in card_clauses(store[card_id])}
                    & {"gust", "retreat_reduction", "self_switch", "switch_self"}), default=0.0)
    if mobility < 1.0:
        add("no_pivot", 1.0 - mobility)
    unknown = set(by_name) - _MECHANICS
    if unknown:
        raise KeyError(f"unknown opponent Mechanic {sorted(unknown)[0]!r}")
    return tuple(OpponentMechanic(name, probability)
                 for name, probability in sorted(by_name.items()))


@dataclass(frozen=True, slots=True)
class OpponentResources:
    hand_count: int
    deck_count: int
    prize_count: int
    active_count: int
    bench_count: int
    discard_count: int


@dataclass(frozen=True, slots=True)
class OpponentResourceDelta:
    from_turn: int
    to_turn: int
    hand_count: int
    deck_count: int
    prize_count: int
    active_count: int
    bench_count: int
    discard_count: int


class OpponentEventKind(str, Enum):
    ATTACK = "attack"
    DRAW = "draw"
    KNOCKOUT = "knockout"
    MOVEMENT = "movement"
    PUBLIC = "public"
    SHUFFLE = "shuffle"
    UNKNOWN = "unknown"


class OpponentSubsystem(str, Enum):
    INFERENCE = "inference"
    LIFECYCLE = "lifecycle"
    ROLE_RESOLUTION = "role_resolution"


@dataclass(frozen=True, slots=True)
class OpponentFailure:
    subsystem: OpponentSubsystem
    error: str


@dataclass(frozen=True, slots=True)
class OpponentPublicEvent:
    turn: int
    sequence: int
    kind: OpponentEventKind
    source: str
    raw_kind: int | None
    public_fields: tuple[tuple[str, object], ...]
    recognized: bool
    player_index: int | None = None
    card_id: int | None = None
    from_area: int | None = None
    to_area: int | None = None


def _public_event(turn, sequence, raw_kind, fields, recognized):
    values = dict(fields)
    from_area, to_area = values.get("fromArea"), values.get("toArea")
    if raw_kind in {6, 7}:
        kind = (OpponentEventKind.KNOCKOUT if from_area == 4 and to_area == 3
                else OpponentEventKind.MOVEMENT)
    else:
        kind = {0: OpponentEventKind.SHUFFLE, 4: OpponentEventKind.DRAW,
                5: OpponentEventKind.DRAW, 15: OpponentEventKind.ATTACK}.get(
                    raw_kind, OpponentEventKind.PUBLIC if recognized
                    else OpponentEventKind.UNKNOWN)
    return OpponentPublicEvent(
        turn, sequence, kind, "public_log", raw_kind, tuple(fields), recognized,
        values.get("playerIndex"), values.get("cardId"), from_area, to_area)


@dataclass(frozen=True, slots=True)
class OpponentEvidence:
    turn: int
    opponent_seat: int
    revealed_card_ids: tuple[int, ...]
    in_play_card_ids: tuple[int, ...]
    resources: OpponentResources
    events: tuple = ()

    @classmethod
    def from_state(cls, state: ObservationState) -> "OpponentEvidence":
        bodies = state.them.bodies
        in_play = tuple(sorted(body.card.card_id for body in bodies))
        revealed = set(in_play)
        revealed.update(card.card_id for card in state.them.discard)
        for body in bodies:
            revealed.update(card.card_id for card in (
                body.energy_cards + body.tools + body.pre_evolution))
        resources = OpponentResources(
            state.them.hand_count, state.them.deck_count, state.them.prize_count,
            int(state.them.active is not None), len(state.them.bench), len(state.them.discard))
        return cls(state.turn.number, 1 - state.seat, tuple(sorted(revealed)),
                   in_play, resources, tuple(state.events))


@dataclass(frozen=True)
class ArchetypeBelief:
    probability: float
    roles: Mapping[int, tuple[str, ...]] = field(default_factory=dict)
    traits: tuple = ()
    mechanics: tuple = ()
    archetype: str = ""
    resources: Mapping[int, float] = field(default_factory=dict)

    def __post_init__(self):
        probability = float(self.probability)
        if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
            raise ValueError("archetype probability must be finite and between zero and one")
        object.__setattr__(self, "probability", probability)
        object.__setattr__(self, "roles", _roles(self.roles))
        traits = tuple(self.traits)
        if any(not isinstance(trait, OpponentTrait) for trait in traits):
            raise TypeError("opponent traits must be OpponentTrait values")
        for trait in traits:
            _traits({trait.name: ([trait.value] if trait.name == "setup_dependency"
                                  else trait.value)})
        mechanics = tuple(self.mechanics)
        if any(not isinstance(mechanic, OpponentMechanic) for mechanic in mechanics):
            raise TypeError("opponent mechanics must be OpponentMechanic values")
        unknown = {mechanic.name for mechanic in mechanics} - _MECHANICS
        if unknown:
            raise KeyError(f"unknown opponent Mechanic {sorted(unknown)[0]!r}")
        object.__setattr__(self, "traits", traits)
        object.__setattr__(self, "mechanics", mechanics)
        object.__setattr__(self, "archetype", str(self.archetype))
        object.__setattr__(self, "resources", _probabilities(self.resources))


@dataclass(frozen=True)
class OpponentSnapshot:
    evidence: OpponentEvidence
    observed_roles: Mapping[int, tuple[str, ...]]
    candidates: tuple[ArchetypeBelief, ...]
    unknown_mass: float
    timeline: tuple[OpponentPublicEvent, ...] = ()
    resource_delta: OpponentResourceDelta | None = None
    failures: tuple[OpponentFailure, ...] = ()
    knowledge_identity: str = ""
    identity: str = ""

    def __post_init__(self):
        candidates = tuple(self.candidates)
        unknown = float(self.unknown_mass)
        if not 0.0 <= unknown <= 1.0:
            raise ValueError("unknown posterior mass must be between zero and one")
        if abs(unknown + sum(item.probability for item in candidates) - 1.0) > 1e-6:
            raise ValueError("candidate probabilities plus unknown mass must equal one")
        object.__setattr__(self, "observed_roles", _roles(self.observed_roles))
        object.__setattr__(self, "candidates", candidates)
        object.__setattr__(self, "unknown_mass", unknown)
        object.__setattr__(self, "timeline", tuple(self.timeline))
        failures = tuple(self.failures)
        if any(not isinstance(item, OpponentFailure) for item in failures):
            raise TypeError("opponent failures must be OpponentFailure values")
        object.__setattr__(self, "failures", failures)
        if not self.identity:
            object.__setattr__(self, "identity", _identity(self.canonical_data()))

    @property
    def degraded(self) -> bool:
        return bool(self.failures)

    def canonical_data(self) -> dict:
        evidence = self.evidence
        return {
            "candidates": [{
                "archetype": candidate.archetype,
                "probability": candidate.probability,
                "resources": list(candidate.resources.items()),
                "roles": [(card_id, list(roles))
                          for card_id, roles in candidate.roles.items()],
                "traits": [(trait.name, trait.value) for trait in candidate.traits],
                "mechanics": [(mechanic.name, mechanic.probability)
                              for mechanic in candidate.mechanics],
            } for candidate in self.candidates],
            "evidence": {
                "in_play_card_ids": list(evidence.in_play_card_ids),
                "opponent_seat": evidence.opponent_seat,
                "resources": [getattr(evidence.resources, name) for name in (
                    "hand_count", "deck_count", "prize_count", "active_count",
                    "bench_count", "discard_count")],
                "revealed_card_ids": list(evidence.revealed_card_ids),
                "turn": evidence.turn,
            },
            "failures": [{"error": item.error, "subsystem": item.subsystem.value}
                         for item in self.failures],
            "knowledge_identity": self.knowledge_identity,
            "observed_roles": [(card_id, list(roles))
                               for card_id, roles in self.observed_roles.items()],
            "resource_delta": (None if self.resource_delta is None else
                               [getattr(self.resource_delta, name) for name in (
                                   "from_turn", "to_turn", "hand_count", "deck_count",
                                   "prize_count", "active_count", "bench_count",
                                   "discard_count")]),
            "timeline": [{
                "kind": event.kind.value,
                "source": event.source,
                "raw_kind": event.raw_kind,
                "player_index": event.player_index,
                "card_id": event.card_id,
                "from_area": event.from_area,
                "to_area": event.to_area,
                "public_fields": list(event.public_fields),
                "recognized": event.recognized,
                "sequence": event.sequence,
                "turn": event.turn,
            } for event in self.timeline],
            "unknown_mass": self.unknown_mass,
        }


@dataclass(frozen=True)
class _CompiledProfile:
    roles: Mapping[int, tuple[str, ...]]
    traits: tuple[OpponentTrait, ...]
    mechanics: tuple[OpponentMechanic, ...]


def _profile_roles(brief, provider) -> Mapping[int, tuple[str, ...]]:
    claims: dict[int, list[str]] = {}

    def add(card_id, roles):
        target = claims.setdefault(int(card_id), [])
        target.extend(role for role in roles if role not in target)

    for entry in brief.pokemon:
        ids = tuple(int(card_id) for card_id in provider.ids_for_name(entry.get("card", "")))
        if not ids:
            raise ValueError(f"{brief.slug}: unresolved Pokemon {entry.get('card')!r}")
        generic = general_pokemon_roles(ids, provider)
        for card_id in ids:
            add(card_id, (*generic.get(card_id, ()), *(entry.get("roles") or ())))
        if "primary_attacker" not in (entry.get("roles") or ()):
            continue
        line = set(ids)
        for card_id in ids:
            line.update(int(value) for value in provider.forward_card_ids(card_id))
        pending = list(ids)
        while pending:
            stat = provider.get(pending.pop())
            parent = getattr(stat, "evolvesFrom", None) if stat is not None else None
            for card_id in provider.ids_for_name(parent) if parent else ():
                if int(card_id) not in line:
                    line.add(int(card_id))
                    pending.append(int(card_id))
        for card_id in line:
            add(card_id, ("primary_attacker",))
    return _roles(claims)


@dataclass(frozen=True)
class OpponentKnowledgeBase:
    priors: Mapping[str, float]
    card_inclusion: Mapping[str, Mapping[int, float]]
    background: Mapping[int, float]
    profiles: Mapping[str, _CompiledProfile]
    identity: str

    @classmethod
    def compile(cls, artifact, briefs, provider) -> "OpponentKnowledgeBase":
        priors = {str(name): float(value) for name, value in artifact.priors.items()}
        if any(not math.isfinite(value) or value < 0.0 for value in priors.values()):
            raise ValueError("opponent priors must be finite and non-negative")
        inclusion = {str(name): _probabilities(values)
                     for name, values in artifact.card_inclusion.items()}
        if set(inclusion) != set(priors):
            raise ValueError("every opponent prior requires card inclusion data")
        background = _probabilities(artifact.background)
        profiles: dict[str, _CompiledProfile] = {}
        routes = {}
        for brief in briefs:
            roles = _profile_roles(brief, provider)
            traits = _traits(brief.traits)
            for archetype in brief.covers:
                key = str(archetype).replace("’", "'")
                if key in routes:
                    raise ValueError(
                        f"opponent archetype {archetype!r} has multiple profiles")
                routes[key] = brief.slug
                matches = [name for name in priors if name.replace("’", "'") == key]
                if not matches:
                    continue
                for name in matches:
                    if name in profiles:
                        raise ValueError(f"opponent archetype {name!r} has multiple profiles")
                    profiles[name] = _CompiledProfile(
                        roles, traits, _mechanics(inclusion[name]))
        for name in priors:
            profiles.setdefault(name, _CompiledProfile(
                _roles({}), (), _mechanics(inclusion[name])))
        canonical = {
            "background": list(background.items()),
            "card_inclusion": {name: list(values.items())
                               for name, values in sorted(inclusion.items())},
            "profiles": {name: {
                "mechanics": [(item.name, item.probability) for item in profile.mechanics],
                "roles": [(card_id, list(roles)) for card_id, roles in profile.roles.items()],
                "traits": [(item.name, item.value) for item in profile.traits],
            } for name, profile in sorted(profiles.items())},
            "priors": sorted(priors.items()),
        }
        return cls(MappingProxyType(dict(sorted(priors.items()))),
                   MappingProxyType(dict(sorted(inclusion.items()))), background,
                   MappingProxyType(dict(sorted(profiles.items()))), _identity(canonical))


class OpponentModel:
    def __init__(self, knowledge: OpponentKnowledgeBase, *, provider=None,
                 candidate_limit: int = 3, strict: bool = False, scorer=posterior):
        if candidate_limit <= 0:
            raise ValueError("candidate limit must be positive")
        self.knowledge = knowledge
        self.provider = provider
        self.candidate_limit = int(candidate_limit)
        self.strict = bool(strict)
        self.scorer = scorer
        self._revealed: set[int] = set()
        self._event_batches: dict[int, dict[str, tuple]] = {}
        self._sequence = 0
        self._last_evidence: OpponentEvidence | None = None

    def _timeline(self, evidence: OpponentEvidence) -> tuple[OpponentPublicEvent, ...]:
        payload = tuple((event.kind, event.public_fields, event.recognized)
                        for event in evidence.events)
        if payload:
            batch_id = _identity([evidence.turn, payload])
            batches = self._event_batches.setdefault(evidence.turn, {})
            if batch_id not in batches:
                events = []
                for kind, fields, recognized in payload:
                    events.append(_public_event(
                        evidence.turn, self._sequence, kind, fields, recognized))
                    self._sequence += 1
                batches[batch_id] = tuple(events)
        minimum = evidence.turn - 1
        self._event_batches = {
            turn: batches for turn, batches in self._event_batches.items()
            if minimum <= turn <= evidence.turn}
        return tuple(sorted(
            (event for batches in self._event_batches.values()
             for events in batches.values() for event in events),
            key=lambda event: (event.turn, event.sequence)))

    def _resource_delta(self, evidence: OpponentEvidence) -> OpponentResourceDelta | None:
        previous = self._last_evidence
        if previous is None:
            return None
        before, after = previous.resources, evidence.resources
        return OpponentResourceDelta(
            previous.turn, evidence.turn,
            after.hand_count - before.hand_count,
            after.deck_count - before.deck_count,
            after.prize_count - before.prize_count,
            after.active_count - before.active_count,
            after.bench_count - before.bench_count,
            after.discard_count - before.discard_count)

    def update(self, evidence: OpponentEvidence) -> OpponentSnapshot:
        if not isinstance(evidence, OpponentEvidence):
            raise TypeError("OpponentModel accepts OpponentEvidence only")
        regression = (self._last_evidence is not None
                      and evidence.turn < self._last_evidence.turn)
        if regression and self.strict:
            raise ValueError("opponent evidence turn regressed within one match")
        timeline = self._timeline(evidence)
        delta = self._resource_delta(evidence)
        self._last_evidence = evidence
        self._revealed.update(evidence.revealed_card_ids)
        failures = []
        beliefs = ()
        unknown = 1.0
        if regression:
            failures.append(OpponentFailure(
                OpponentSubsystem.LIFECYCLE, "turn_regression"))
        else:
            try:
                candidates, unknown = self.scorer(
                    self.knowledge.priors, self.knowledge.card_inclusion,
                    self.knowledge.background, self._revealed)
                kept = tuple(candidates[:self.candidate_limit])
                unknown += sum(probability for _name, probability
                               in candidates[self.candidate_limit:])
                beliefs = tuple(ArchetypeBelief(
                    probability, self.knowledge.profiles[name].roles,
                    self.knowledge.profiles[name].traits,
                    self.knowledge.profiles[name].mechanics, archetype=name,
                    resources=self.knowledge.card_inclusion.get(name, {}))
                    for name, probability in kept)
            except Exception as exc:
                if self.strict:
                    raise
                failures.append(OpponentFailure(
                    OpponentSubsystem.INFERENCE, type(exc).__name__))
        try:
            roles = general_pokemon_roles(evidence.revealed_card_ids, self.provider)
        except Exception as exc:
            if self.strict:
                raise
            roles = {}
            failures.append(OpponentFailure(
                OpponentSubsystem.ROLE_RESOLUTION, type(exc).__name__))
        return OpponentSnapshot(
            evidence, roles, beliefs, unknown, timeline, delta,
            failures=tuple(failures), knowledge_identity=self.knowledge.identity)
