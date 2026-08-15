"""Deck-neutral demand and known-card coverage for Bellman value calculations.

This module describes recipient-specific opportunities, access odds, and optimistic ceilings.
It never assigns decision utility, steps a rules engine, or samples a hidden card.
"""
from __future__ import annotations

from collections import Counter
import copy
from dataclasses import dataclass
import hashlib
from time import perf_counter

from .fetch import REACH, WINDOW, fetch_target_matches
from .energy import ENERGY_COLORLESS, pays_energy_type, provision_units, unmet_cost_slots
from .information import OutcomeGroup, hypergeometric_classes
from .scouting.card_text import name_in_family
from .strategy.context import _MAIN


DEFAULT_BENCH_CAPACITY = 5
DEFAULT_ENERGY_CODE = 0
FETCHER_CARD_COUNT = 1
FLOAT_TIE_DIGITS = 12
MINIMUM_BODY_HP = 10
NEXT_STAGE_OFFSET = 1
NEXT_TURN_OPTION_DISCOUNT = 1.0
BENCH_HEAL_VALUE_SHARE = 0.25
HEAL_DAMAGE_PER_VALUE = 200.0


def _record_id(value) -> str:
    return hashlib.sha256(repr(value).encode("utf-8")).hexdigest()[:20]


def semantic_action_key(action) -> str:
    return _record_id(action.identity)


@dataclass(frozen=True)
class NeedRoot:
    key: str
    predicate: str
    deadline: int
    outcome: str
    confidence: float
    provenance: str
    recipient: str = ""
    capability: str = ""
    slot: str = ""
    ceiling: float = 0.0
    alternative: str = ""

    @property
    def semantic_id(self) -> str:
        return _record_id(self)


@dataclass(frozen=True)
class AccessEdge:
    source_card_id: int | None
    capability: str
    need_ids: tuple[str, ...]
    earliest_turn: int
    deterministic: bool
    probability: float
    confidence: float
    prerequisites: tuple[str, ...] = ()
    costs: tuple[str, ...] = ()

    @property
    def semantic_id(self) -> str:
        return _record_id(self)


@dataclass(frozen=True)
class NeedPath:
    root_ids: tuple[str, ...]
    edges: tuple[AccessEdge, ...]
    reservations: tuple[str, ...]
    conflicts: tuple[str, ...]
    earliest_turn: int
    probability: float
    confidence: float
    persistence: str

    @property
    def semantic_id(self) -> str:
        return _record_id(self)


@dataclass(frozen=True)
class PathFeatures:
    outcome: str
    deadline: int
    turns: int
    actions: int
    probability: float
    confidence: float
    roots: int
    irreversible: int
    uncertainty: int


@dataclass(frozen=True)
class ActionFocus:
    action_key: str
    family: str
    path_ids: tuple[str, ...]
    score: float
    reason: str


@dataclass(frozen=True)
class UnknownAction:
    action_key: str
    card_id: int | None
    context: int
    reason: str


@dataclass(frozen=True)
class PokemonRole:
    card_id: int
    role: str
    confidence: float
    provenance: str


@dataclass(frozen=True)
class NeedBeam:
    focused: tuple[ActionFocus, ...]
    safety: tuple[ActionFocus, ...]
    unknown: tuple[UnknownAction, ...]
    paths: tuple[NeedPath, ...]
    features: tuple[PathFeatures, ...]
    elapsed_ms: float
    exhausted: bool
    held: tuple[ActionFocus, ...] = ()
    inactive: tuple[ActionFocus, ...] = ()
    roots: tuple[NeedRoot, ...] = ()


@dataclass(frozen=True)
class CapabilityIndex:
    entries: tuple[tuple[int, tuple[str, ...]], ...]
    unknown: tuple[int, ...]

    @classmethod
    def compile(cls, deck, *, stats=None, effects=None, functions=None) -> "CapabilityIndex":
        entries = []
        unknown = []
        for card_id in sorted(set(int(value) for value in deck)):
            kinds = set()
            stat = stats.get(card_id) if stats is not None else None
            if stat is not None:
                if getattr(stat, "is_pokemon", False):
                    kinds.add("deploy" if str(getattr(stat, "stage", "")).lower() == "basic"
                              else "evolve")
                if getattr(stat, "is_energy", False):
                    kinds.add("attach")
            clauses = effects.clauses(card_id) if effects is not None else ()
            for clause in clauses:
                kind = str(clause.get("kind") or "")
                if kind:
                    kinds.add(kind)
                if clause.get("dig") is not None:
                    kinds.add("dig")
            if functions is not None:
                tags = (functions.tags(card_id) if hasattr(functions, "tags")
                        else functions.get(card_id, ()))
                kinds.update(str(tag).split(":", 1)[0] for tag in tags if str(tag))
            row = tuple(sorted(kinds))
            entries.append((card_id, row))
            if not row:
                unknown.append(card_id)
        return cls(tuple(entries), tuple(unknown))

    def kinds(self, card_id: int) -> tuple[str, ...]:
        return dict(self.entries).get(int(card_id), ())


def access_probability(pool_ids, draws: int, eligible_ids) -> float:
    eligible = tuple(sorted(set(int(card_id) for card_id in eligible_ids)))
    if draws <= 0 or not eligible:
        return 0.0
    classes = hypergeometric_classes(
        pool_ids, draws, (OutcomeGroup("need", eligible),))
    return sum(outcome.probability for outcome in classes if outcome.counts[0] > 0)


def _need_fetch_target_matches(clause, stat) -> bool:
    if clause.get("trigger") or clause.get("condition"):
        return False
    family = clause.get("name_family")
    if family and not name_in_family(getattr(stat, "name", None), family):
        return False
    base = {key: value for key, value in clause.items()
            if key not in {"dig", "name_family"}}
    reading = WINDOW if base.get("target") == "supporter" else REACH
    return fetch_target_matches(base, stat, reading=reading)


def infer_pokemon_roles(deck, registry, stats=None) -> tuple[PokemonRole, ...]:
    declared = registry.roles
    inferred = {}
    for card_id in sorted(set(int(value) for value in deck)):
        stat = stats.get(card_id) if stats is not None else None
        if stat is None or not getattr(stat, "is_pokemon", False):
            continue
        roles = set(declared.get(card_id, ()))
        if roles & {"primary_attacker", "win_condition"}:
            role, provenance = "primary_attacker", "brief"
        elif "secondary_attacker" in roles:
            role, provenance = "secondary_attacker", "brief"
        elif roles & {"engine", "support", "support_pokemon"}:
            role, provenance = "support_pokemon", "brief"
        elif tuple(getattr(stat, "attacks", ()) or ()):
            role, provenance = "secondary_attacker", "generic"
        else:
            role, provenance = "support_pokemon", "generic"
        inferred[card_id] = PokemonRole(card_id, role, 1.0 if provenance == "brief" else 0.7,
                                        provenance)
    generic_attackers = [row for row in inferred.values()
                         if row.role == "secondary_attacker" and row.provenance == "generic"]
    if generic_attackers and not any(row.role == "primary_attacker" for row in inferred.values()):
        leader = max(generic_attackers, key=lambda row: (
            int(getattr(stats.get(row.card_id), "hp", 0) or 0), -row.card_id))
        inferred[leader.card_id] = PokemonRole(
            leader.card_id, "primary_attacker", leader.confidence, leader.provenance)
    for line in registry.lines:
        if not line or int(line[-1]) not in inferred:
            continue
        top = inferred[int(line[-1])]
        for card_id in line[:-1]:
            if int(card_id) in inferred:
                inferred[int(card_id)] = PokemonRole(
                    int(card_id), top.role, top.confidence, top.provenance)
    return tuple(inferred[card_id] for card_id in sorted(inferred))


def opponent_threat_roots(observation, stats=None) -> tuple[NeedRoot, ...]:
    current = observation.get("current") or {}
    players = current.get("players") or ()
    seat = int(current.get("yourIndex", 0))
    opponent = players[1 - seat] if 0 <= 1 - seat < len(players) and players[1 - seat] else {}
    roots = []
    for area in ("active", "bench"):
        for index, body in enumerate(opponent.get(area) or ()):
            if not body or not (body.get("energyCards") or body.get("energies")):
                continue
            deadline = 0 if area == "active" else 1
            recipient = str(body.get("serial", f"{area}:{index}:{body.get('id', 0)}"))
            key = f"deny:{recipient}:threat"
            roots.append(NeedRoot(
                key, key, deadline, "prevent_prize", 0.75, "generic",
                recipient, "deny", "threat"))
            stat = stats.get(body.get("id")) if stats is not None else None
            energy_types = tuple(int(value) for value in body.get("energies") or ())
            energy_count = len(energy_types or tuple(body.get("energyCards") or ()))
            if (area == "active" and stat is not None
                    and int(getattr(stat, "retreatCost", 0) or 0) == energy_count):
                retreat_key = f"deny:{recipient}:retreat"
                roots.append(NeedRoot(
                    retreat_key, retreat_key, 0, "prevent_retreat", 1.0, "card_stats",
                    recipient, "deny", "retreat"))
            required_types = tuple(int(value) for value in
                                   getattr(stat, "abilityEnergyTypes", ()) or ())
            if (stat is not None and getattr(stat, "hasAbility", False)
                    and sum(value in required_types for value in energy_types) == 1):
                ability_key = f"deny:{recipient}:ability"
                roots.append(NeedRoot(
                    ability_key, ability_key, deadline, "prevent_ability", 1.0, "card_stats",
                    recipient, "deny", "ability"))
    return tuple(roots)


class NeedBeamBuilder:
    def __init__(self, model: "NeedModel", capabilities: CapabilityIndex, *, width=8,
                 family_variants=2, horizon=2, max_ms=10.0, roles=()):
        self.model = model
        self.capabilities = capabilities
        self.width = max(1, int(width))
        self.family_variants = max(1, int(family_variants))
        self.horizon = max(0, int(horizon))
        self.max_ms = max(0.0, float(max_ms))
        self.roles = {role.card_id: role for role in roles}

    def build(self, state, actions, *, ranking=None) -> NeedBeam:
        started = perf_counter()
        deadline = started + self.max_ms / 1000.0
        context = int((state.obs.get("select") or {}).get("context", _MAIN))
        if context != _MAIN:
            safety = tuple(ActionFocus(
                semantic_action_key(action), "forced_selection", (), 0.0, "forced_selection")
                for action in actions)
            elapsed = (perf_counter() - started) * 1000.0
            return NeedBeam((), safety, (), (), (), elapsed, elapsed > self.max_ms)
        needs = self.model.immediate(state.obs, state.root_seat)
        roots = tuple(self._root(need) for need in needs) + opponent_threat_roots(
            state.obs, self.model.stats)
        action_sources = tuple(filter(None, (
            self._source_card_id(state, action) for action in actions)))
        paths = list(self._direct_paths(roots, needs))
        paths.extend(self._access_paths(
            state, roots, needs, source_ids=action_sources))
        if perf_counter() < deadline:
            paths.extend(self._acceleration_paths(roots))
            paths.extend(self._denial_paths(roots))
        features = tuple(self._features(path, roots) for path in paths)
        by_action = ({candidate.action: candidate for candidate in ranking.candidates}
                     if ranking is not None else {})
        by_source: dict[int, list[NeedPath]] = {}
        for path in paths:
            for edge in path.edges:
                if edge.source_card_id is not None:
                    by_source.setdefault(edge.source_card_id, []).append(path)
        focused = []
        safety = []
        unknown = []
        held = []
        inactive = []
        for action in actions:
            key = semantic_action_key(action)
            candidate = by_action.get(action)
            family = (candidate.family if candidate is not None
                      and not candidate.family.startswith("unclassified:")
                      else action.identity.kind)
            if action.identity.kind in {"attack", "end", "retreat"}:
                safety.append(ActionFocus(key, family, (), 0.0, "safety"))
                continue
            card_id = self._source_card_id(state, action)
            related = by_source.get(card_id, ()) if card_id is not None else ()
            if card_id is not None and self._supporter_fetch_blocked(state, card_id):
                held.append(ActionFocus(key, family, (), 0.0, "supporter_already_played"))
                continue
            if related:
                assigned_roots = self._assigned_roots(state, action, needs, roots)
                if assigned_roots:
                    root_scores = {
                        root_id: max(self._path_score(path, roots) for path in related
                                     if path.root_ids[0] == root_id)
                        for root_id in assigned_roots
                        if any(path.root_ids[0] == root_id for path in related)
                    }
                    score = sum(root_scores.values())
                else:
                    score = max(self._path_score(path, roots) for path in related)
                if candidate is not None and candidate.score is not None:
                    score += max(0.0, float(candidate.score))
                focused.append(ActionFocus(
                    key, family, tuple(sorted(path.semantic_id for path in related)),
                    score, "need_path"))
            elif (candidate is not None and candidate.score is not None
                  and float(candidate.score) > 0.0):
                focused.append(ActionFocus(
                    key, family, (), float(candidate.score), "family_equation"))
            else:
                kinds = self._known_kinds(card_id) if card_id is not None else ()
                if kinds:
                    inactive.append(ActionFocus(
                        key, family, (), 0.0, f"no_current_need:{','.join(kinds)}"))
                else:
                    unknown.append(UnknownAction(
                        key, card_id, int((state.obs.get("select") or {}).get("context", 0)),
                        f"unconnected_action:{action.identity.kind}"))
        focused = self._retain(focused)
        elapsed = (perf_counter() - started) * 1000.0
        return NeedBeam(tuple(focused), tuple(safety), tuple(unknown), tuple(paths), features,
                        elapsed, perf_counter() >= deadline, tuple(held), tuple(inactive), roots)

    def _root(self, need: Need) -> NeedRoot:
        role = next((self.roles.get(int(card_id)) for card_id, _value in need.direct
                     if self.roles.get(int(card_id)) is not None), None)
        timing_deadline = 1 if need.timing == "next_turn" else 0
        if need.key.startswith("heal"):
            outcome, deadline = "prevent_prize", 0
        elif need.key.startswith("deploy"):
            outcome = f"establish_{role.role if role else 'attacker'}"
            deadline = (0 if role is not None and role.role == "primary_attacker"
                        else min(2, self.horizon))
        elif need.key.startswith("evolve"):
            outcome, deadline = f"establish_{role.role if role else 'attacker'}", timing_deadline
        else:
            outcome, deadline = "take_prize", timing_deadline
        deadline = max(deadline, timing_deadline)
        return NeedRoot(
            need.key, need.key, deadline, outcome,
            role.confidence if role else 1.0, role.provenance if role else "generic",
            need.recipient, need.capability, need.slot,
            need.ceiling or max((value for _card_id, value in need.direct), default=0.0),
            need.alternative)

    @staticmethod
    def _direct_paths(roots, needs):
        for root, need in zip(roots, needs):
            for card_id, _value in need.direct:
                edge = AccessEdge(int(card_id), "direct", (root.semantic_id,), 0, True, 1.0, 1.0)
                yield NeedPath((root.semantic_id,), (edge,), (), (), 0, 1.0, 1.0, "safe")

    def _access_paths(self, state, roots, needs, *, source_ids=()):
        pool = tuple(card_id for card_id, count in state.deck_counts for _ in range(count))
        available = frozenset(pool)
        players = ((state.obs.get("current") or {}).get("players") or ())
        seat = int(getattr(state, "root_seat", 0))
        mine = players[seat] if seat < len(players) else {}
        discard = frozenset(int(card["id"]) for card in mine.get("discard") or ()
                            if card and card.get("id") is not None)
        known_top = tuple(state.obs.get("known_top") or ())
        downstream = []
        current_sources = tuple(sorted(set(int(card_id) for card_id in source_ids)))
        future_sources = tuple(sorted(
            source_id for source_id, _kinds in self.capabilities.entries
            if source_id not in current_sources))
        sources = (*current_sources, *future_sources)
        root_needs = tuple(
            (root, need, tuple(card_id for card_id, _value in need.direct
                               if int(card_id) in available))
            for root, need in zip(roots, needs)
        )
        for root, _need, eligible in root_needs:
            if known_top and int(known_top[0][1]) in eligible:
                edge = AccessEdge(None, "known_top_draw", (root.semantic_id,), 1,
                                  True, 1.0, 1.0)
                yield NeedPath((root.semantic_id,), (edge,), ("known_top",), (), 1,
                               1.0, 1.0, "fragile")
        for source_id in sources:
            clauses = tuple(self.model.effects.clauses(source_id)) if self.model.effects else ()
            for root, need, eligible in root_needs:
                for clause in clauses:
                    kind = str(clause.get("kind") or "")
                    if kind == "fetch" and clause.get("zone") == "deck":
                        reachable = tuple(card_id for card_id in eligible
                                          if _need_fetch_target_matches(
                                              clause, self.model.stat(card_id)))
                        if not reachable:
                            continue
                        depth = int(clause.get("dig", 0) or 0)
                        probability = access_probability(pool, depth, reachable) if depth else 1.0
                        reservations = tuple(
                            f"discard:{index}" for index in range(discard_cost(clause)))
                        edge = AccessEdge(source_id, "dig" if depth else "fetch",
                                          (root.semantic_id,), 0, depth == 0, probability, 1.0,
                                          costs=reservations)
                        path = NeedPath((root.semantic_id,), (edge,), reservations, (), 0,
                                        probability, 1.0, "safe")
                        downstream.append((source_id, root, path))
                        yield path
                    elif kind == "fetch" and clause.get("zone") == "discard":
                        reachable = tuple(
                            int(card_id) for card_id, _value in need.direct
                            if int(card_id) in discard
                            and _need_fetch_target_matches(clause, self.model.stat(card_id)))
                        if not reachable:
                            continue
                        edge = AccessEdge(source_id, "recover", (root.semantic_id,), 0,
                                          True, 1.0, 1.0)
                        path = NeedPath((root.semantic_id,), (edge,), (), (), 0,
                                        1.0, 1.0, "safe")
                        downstream.append((source_id, root, path))
                        yield path
                    elif kind == "draw":
                        depth = int(clause.get("amount", 0) or 0)
                        probability = access_probability(pool, depth, eligible)
                        if probability <= 0.0:
                            continue
                        edge = AccessEdge(source_id, "draw", (root.semantic_id,), 0,
                                          False, probability, 1.0)
                        path = NeedPath((root.semantic_id,), (edge,), (), (), 0,
                                        probability, 1.0, "safe")
                        downstream.append((source_id, root, path))
                        yield path
        current = state.obs.get("current") or {}
        if current.get("supporterPlayed"):
            return
        for source_id in sources:
            for clause in tuple(self.model.effects.clauses(source_id)) if self.model.effects else ():
                if (clause.get("kind") != "fetch" or clause.get("zone") != "deck"
                        or clause.get("target") != "supporter"):
                    continue
                players = current.get("players") or ()
                mine = players[state.root_seat] if state.root_seat < len(players) else {}
                hand_ids = {int(card["id"]) for card in mine.get("hand") or () if card}
                useful = tuple(sorted({downstream_id for downstream_id, _root, _path in downstream
                                       if downstream_id in available
                                       if downstream_id not in hand_ids
                                       if bool(getattr(self.model.stat(downstream_id),
                                                       "is_supporter", False))}))
                if not useful:
                    continue
                depth = int(clause.get("dig", 0) or 0)
                access = access_probability(pool, depth, useful) if depth else 1.0
                for downstream_id, root, path in downstream:
                    if downstream_id not in useful:
                        continue
                    outer = AccessEdge(
                        source_id, "dig_supporter" if depth else "fetch_supporter",
                        (root.semantic_id,), 0, depth == 0, access, 1.0,
                        prerequisites=("supporter_allowance",))
                    probability = access * path.probability
                    yield NeedPath(
                        path.root_ids, (outer, *path.edges), ("supporter_allowance",), (), 0,
                        probability, min(1.0, path.confidence), "safe")

    def _denial_paths(self, roots):
        threats = tuple(root for root in roots if root.key.startswith("deny:"))
        for source_id, kinds in self.capabilities.entries:
            if "energy_denial" not in kinds:
                continue
            for root in threats:
                edge = AccessEdge(source_id, "energy_denial", (root.semantic_id,), 0,
                                  False, 0.5, root.confidence)
                yield NeedPath((root.semantic_id,), (edge,), (), (), root.deadline,
                               0.5, root.confidence, "safe")

    def _acceleration_paths(self, roots):
        funding = tuple(root for root in roots if root.key.startswith("fund"))
        for source_id, kinds in self.capabilities.entries:
            if not ({"accel", "energy_acceleration"} & set(kinds)):
                continue
            for root in funding:
                edge = AccessEdge(
                    source_id, "energy_acceleration", (root.semantic_id,), 0,
                    True, 1.0, root.confidence)
                yield NeedPath(
                    (root.semantic_id,), (edge,), (), (), 0, 1.0,
                    root.confidence, "safe")

    @staticmethod
    def _features(path: NeedPath, roots) -> PathFeatures:
        root = next(root for root in roots if root.semantic_id == path.root_ids[0])
        return PathFeatures(root.outcome, root.deadline, path.earliest_turn, len(path.edges),
                            path.probability, path.confidence, len(path.root_ids),
                            len(path.reservations), int(path.persistence == "fragile"))

    @staticmethod
    def _path_score(path: NeedPath, roots) -> float:
        root = next(root for root in roots if root.semantic_id == path.root_ids[0])
        urgency = 1.0 / (1.0 + root.deadline)
        supporter_first = any(edge.capability in {"dig_supporter", "fetch_supporter"}
                              for edge in path.edges)
        access = path.probability * path.confidence * urgency * (1.0 + root.ceiling)
        return access / (1.0 + len(path.reservations)) + float(supporter_first)

    def _retain(self, focused):
        focused.sort(key=lambda row: (-row.score, row.family, row.action_key))
        counts = {}
        retained = []
        for row in focused:
            if counts.get(row.family, 0) >= self.family_variants:
                continue
            retained.append(row)
            counts[row.family] = counts.get(row.family, 0) + 1
            if len(retained) >= self.width:
                break
        return retained

    def _assigned_roots(self, state, action, needs, roots) -> frozenset[str]:
        card_id, recipient, units = self.model.supply_context(state, action)
        if card_id is None:
            return frozenset()
        current = state.obs.get("current") or {}
        players = current.get("players") or ()
        mine = players[state.root_seat] if state.root_seat < len(players) else {}
        signatures = self.model.coverage_slots(
            card_id, needs,
            supporter_available=not bool(current.get("supporterPlayed")),
            discard_capacity=max(0, len(mine.get("hand") or ()) - 1),
            available_targets=Counter(dict(state.deck_counts)),
            recipient=recipient, provision_units=units)
        assignment = best_assignment(
            signatures, len(needs), target_counts=Counter(dict(state.deck_counts)))
        return frozenset(
            roots[index].semantic_id for index in range(len(needs))
            if assignment.covered_mask & (1 << index))

    @staticmethod
    def _source_card_id(state, action):
        if len(action.selection) != 1:
            return None
        options = ((state.obs.get("select") or {}).get("option") or ())
        option_index = action.selection[0]
        if not 0 <= option_index < len(options):
            return None
        option = options[option_index]
        if action.identity.kind in {"ability", "skill"}:
            area = option.get("inPlayArea", option.get("area"))
            index = option.get("inPlayIndex", option.get("index"))
            if area == 7:
                stadium = (state.obs.get("current") or {}).get("stadium") or ()
                if isinstance(index, int) and 0 <= index < len(stadium) and stadium[index]:
                    return int(stadium[index]["id"])
                return None
            players = ((state.obs.get("current") or {}).get("players") or ())
            mine = players[state.root_seat] if state.root_seat < len(players) else {}
            zone = "active" if area == 4 else "bench" if area == 5 else None
            bodies = mine.get(zone) or () if zone is not None else ()
            if isinstance(index, int) and 0 <= index < len(bodies) and bodies[index]:
                return int(bodies[index]["id"])
            return None
        if action.identity.kind not in {"play", "attach", "evolve"}:
            return None
        hand_index = option.get("index")
        players = ((state.obs.get("current") or {}).get("players") or ())
        mine = players[state.root_seat] if state.root_seat < len(players) else {}
        hand = mine.get("hand") or ()
        if not isinstance(hand_index, int) or not 0 <= hand_index < len(hand) or not hand[hand_index]:
            return None
        return int(hand[hand_index]["id"])

    def _known_kinds(self, card_id: int) -> tuple[str, ...]:
        kinds = set(self.capabilities.kinds(card_id))
        if self.model.effects is not None:
            kinds.update(str(clause.get("kind")) for clause in self.model.effects.clauses(card_id)
                         if clause.get("kind"))
        return tuple(sorted(kinds))

    def _supporter_fetch_blocked(self, state, card_id: int) -> bool:
        current = state.obs.get("current") or {}
        if not current.get("supporterPlayed") or self.model.effects is None:
            return False
        return any(
            clause.get("kind") == "fetch" and clause.get("zone") == "deck"
            and clause.get("target") == "supporter"
            for clause in self.model.effects.clauses(card_id))


@dataclass(frozen=True)
class Need:
    """One board demand and the direct card identities that can satisfy it."""

    key: str
    direct: tuple[tuple[int, float], ...]
    timing: str = "immediate"
    recipient: str = ""
    capability: str = ""
    slot: str = ""
    ceiling: float = 0.0
    alternative: str = ""


@dataclass(frozen=True)
class CoverageEdge:
    """A card's value when assigned to one need."""

    need_index: int
    value: float
    fetched_target: int | None = None
    exclusive_group: str = ""
    alternative: str = ""
    constraints: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class ResolvedAssignment:
    """Maximum non-duplicated assignment over card-to-need coverage."""

    value: float
    covered_mask: int
    used_card_mask: int = 0


@dataclass(frozen=True)
class RetainedOption:
    """A deterministic next-turn option requiring visible hand positions."""

    key: str
    required_cards: tuple[int, ...]
    value: float
    description: str


@dataclass(frozen=True)
class RetainedAssignment:
    """Best compatible set of deterministic next-turn options."""

    value: float
    options: tuple[RetainedOption, ...]


def body_rows(player):
    for area in ("active", "bench"):
        for index, body in enumerate(player.get(area) or ()):
            if body:
                yield area, index, body


def discard_cost(clause) -> int:
    cost = str(clause.get("cost") or "")
    if not cost.startswith("discard_"):
        return 0
    try:
        return max(0, int(cost.split("_", 1)[1]))
    except (TypeError, ValueError):
        return 0


def coverage_signature(edges: dict[int, float]) -> tuple[tuple[int, float], ...]:
    return tuple(sorted((int(index), round(float(value), FLOAT_TIE_DIGITS))
                        for index, value in edges.items() if value > 0.0))


def best_assignment(signatures, need_count: int, *, target_counts=None) -> ResolvedAssignment:
    """Assign tokens to needs without reusing a fetched deck target.

    Plain ``(need_index, value)`` pairs remain valid direct-resource edges. ``CoverageEdge`` adds
    an optional fetched target; its limited count is consumed only when that edge is selected.
    """
    target_counts = target_counts or {}
    target_ids = tuple(sorted(int(card_id) for card_id, count in target_counts.items() if count > 0))
    target_positions = {card_id: index for index, card_id in enumerate(target_ids)}
    initial_counts = tuple(int(target_counts[card_id]) for card_id in target_ids)
    dp = {(0, initial_counts, ()): (0.0, 0)}
    for card_index, signature in enumerate(signatures):
        advanced = dict(dp)
        for (mask, available, alternatives), (value, used) in dp.items():
            for raw_edge in signature:
                if isinstance(raw_edge, CoverageEdge):
                    need_index, edge_value, target, group, alternative = (
                        raw_edge.need_index, raw_edge.value, raw_edge.fetched_target,
                        raw_edge.exclusive_group, raw_edge.alternative)
                    constraints = raw_edge.constraints
                else:
                    need_index, edge_value = raw_edge
                    target = None
                    group = alternative = ""
                    constraints = ()
                bit = 1 << need_index
                if mask & bit:
                    continue
                selected = dict(alternatives)
                choices = constraints + (((group, alternative),) if group else ())
                if any(choice_group in selected and selected[choice_group] != choice
                       for choice_group, choice in choices):
                    continue
                selected.update(choices)
                next_available = available
                if target is not None:
                    position = target_positions.get(int(target))
                    if position is None or available[position] <= 0:
                        continue
                    next_available = (*available[:position], available[position] - 1,
                                      *available[position + 1:])
                new_mask = mask | bit
                candidate = (value + edge_value, used | (1 << card_index))
                state = (new_mask, next_available, tuple(sorted(selected.items())))
                previous = advanced.get(state)
                if (previous is None or
                        (round(candidate[0], FLOAT_TIE_DIGITS), candidate[1])
                        > (round(previous[0], FLOAT_TIE_DIGITS), previous[1])):
                    advanced[state] = candidate
        dp = advanced
    (mask, _available, _alternatives), (value, used) = max(
        dp.items(), key=lambda row: (round(row[1][0], FLOAT_TIE_DIGITS), row[0][0], row[1][1]))
    return ResolvedAssignment(value, mask, used)


def best_retained_assignment(options: tuple[RetainedOption, ...]) -> RetainedAssignment:
    """Weighted set packing over visible cards and mutually exclusive opportunity keys."""
    if not options:
        return RetainedAssignment(0.0, ())
    keys = {key: index for index, key in enumerate(sorted(
        {option.key for option in options}))}
    dp: dict[tuple[int, int], tuple[float, tuple[RetainedOption, ...]]] = {(0, 0): (0.0, ())}
    for option in options:
        card_mask = sum(1 << index for index in option.required_cards)
        key_mask = 1 << keys[option.key]
        advanced = dict(dp)
        for (used_cards, used_keys), (value, chosen) in dp.items():
            if used_cards & card_mask or used_keys & key_mask:
                continue
            state = (used_cards | card_mask, used_keys | key_mask)
            candidate = (value + option.value, (*chosen, option))
            previous = advanced.get(state)
            if previous is None or round(candidate[0], FLOAT_TIE_DIGITS) > round(
                    previous[0], FLOAT_TIE_DIGITS):
                advanced[state] = candidate
        dp = advanced
    value, chosen = max(dp.values(), key=lambda row: (
        round(row[0], FLOAT_TIE_DIGITS), tuple(option.description for option in row[1])))
    return RetainedAssignment(value, chosen)


class NeedModel:
    """Derive immediate demands and deterministic next-turn visible-hand options."""

    def __init__(self, registry, family_evaluator, *, effects=None, stats=None):
        self.registry = registry
        self.family_evaluator = family_evaluator
        self.effects = effects
        self.stats = stats

    def stat(self, card_id):
        return self.stats.get(int(card_id)) if self.stats is not None and card_id is not None else None

    def potential(self, observation):
        return self.family_evaluator(observation)

    def operation_gain(self, before, after) -> float:
        return max(0.0, float(self.potential(after).total - self.potential(before).total))

    def immediate(self, observation, seat: int) -> tuple[Need, ...]:
        current = observation.get("current") or {}
        players = current.get("players") or ()
        mine = players[seat] if len(players) > seat else {}
        needs: list[Need] = []
        rows = tuple(body_rows(mine))

        for area, index, body in rows:
            timing = "next_turn" if body.get("appearThisTurn") else "immediate"
            target = self._next_stage(body.get("id"))
            if target is None:
                continue
            evolved = self._evolve(observation, seat, area, index, target)
            gain = self.operation_gain(observation, evolved)
            if gain > 0.0:
                recipient = self._recipient(area, index, body)
                needs.append(Need(
                    f"evolve:{recipient}:{target}", ((target, gain),),
                    timing=timing, recipient=recipient, capability="evolve",
                    slot=str(target), ceiling=gain))

        funding_timing = "next_turn" if current.get("energyAttached") else "immediate"
        candidates = tuple(
            (int(card_id), self.stat(card_id)) for card_id in self.registry.facts
            if self.stat(card_id) is not None
            and getattr(self.stat(card_id), "is_energy", False))
        for area, index, body in rows:
            body_stat = self.stat(body.get("id"))
            attacks = tuple(getattr(body_stat, "attacks", ()) or ()) if body_stat else ()
            recipient = self._recipient(area, index, body)
            gains = {}
            for candidate, energy_stat in candidates:
                attached = copy.deepcopy(observation)
                target_body = attached["current"]["players"][seat][area][index]
                units = self._energy_units(candidate, target_body)
                energy_type = getattr(energy_stat, "energyType", None)
                code = DEFAULT_ENERGY_CODE if energy_type is None else int(energy_type)
                target_body.setdefault("energies", []).extend([code] * units)
                target_body.setdefault("energyCards", []).append({"id": candidate})
                gains[candidate] = self.operation_gain(observation, attached)
            for attack_id in attacks:
                attack = (self.stats.attack(attack_id)
                          if self.stats is not None and hasattr(self.stats, "attack") else None)
                if attack is None:
                    continue
                requirements = tuple(getattr(attack, "energyTypes", ()) or ())
                if not requirements:
                    requirements = (ENERGY_COLORLESS,) * int(getattr(attack, "cost", 0) or 0)
                missing_slots = unmet_cost_slots(body.get("energies") or (), requirements)
                allocations = {}
                for candidate, energy_stat in candidates:
                    compatible = sum(
                        pays_energy_type(
                            getattr(energy_stat, "energyType", DEFAULT_ENERGY_CODE)
                            if getattr(energy_stat, "energyType", None) is not None
                            else DEFAULT_ENERGY_CODE,
                            required_type)
                        for _slot_index, required_type in missing_slots
                    )
                    supplied = min(self._energy_units(candidate, body), compatible)
                    if supplied > 0 and gains[candidate] > 0.0:
                        allocations[candidate] = gains[candidate] / supplied
                for slot_index, required_type in missing_slots:
                    direct = tuple(sorted(
                        (candidate, allocations[candidate])
                        for candidate, energy_stat in candidates
                        if candidate in allocations
                        if pays_energy_type(
                            getattr(energy_stat, "energyType", DEFAULT_ENERGY_CODE)
                            if getattr(energy_stat, "energyType", None) is not None
                            else DEFAULT_ENERGY_CODE,
                            required_type)
                    ))
                    if not direct:
                        continue
                    slot = f"{slot_index}:{required_type}"
                    needs.append(Need(
                        f"fund_attack:{recipient}:{attack_id}:{slot}", direct,
                        timing=funding_timing, recipient=recipient,
                        capability="fund_attack", slot=slot,
                        ceiling=max(value for _card_id, value in direct),
                        alternative=str(attack_id)))

        for area, index, body in rows:
            recipient = self._recipient(area, index, body)
            heal_edges = {}
            for card_id in self.registry.facts:
                clauses = tuple(self.effects.clauses(card_id)) if self.effects is not None else ()
                gains = [self._heal_gain(observation, seat, clause, target=(area, index))
                         for clause in clauses if clause.get("kind") == "heal"]
                gain = max(gains, default=0.0)
                if gain > 0.0:
                    heal_edges[int(card_id)] = gain
            if heal_edges:
                damage = max(0, int(body.get("maxHp", body.get("hp", 0)))
                             - int(body.get("hp", 0)))
                band = str((damage // 30) * 30)
                ceiling = max(heal_edges.values())
                needs.append(Need(
                    f"heal:{recipient}:{band}", tuple(sorted(heal_edges.items())),
                    recipient=recipient, capability="heal", slot=band, ceiling=ceiling))

        bench_space = max(0, int(mine.get("benchMax", DEFAULT_BENCH_CAPACITY))
                          - len(mine.get("bench") or ()))
        for line in self.registry.lines:
            if not line or bench_space <= 0:
                continue
            base, payoff = int(line[0]), int(line[-1])
            desired = max((route.count(payoff) for route in self.registry.prize_routes), default=1)
            present = sum(int(body.get("id", 0)) in line for _area, _index, body in rows)
            missing = min(bench_space, max(0, desired - present))
            if missing <= 0:
                continue
            deployed = copy.deepcopy(observation)
            stat = self.stat(base)
            hp = int(getattr(stat, "hp", MINIMUM_BODY_HP) or MINIMUM_BODY_HP)
            deployed["current"]["players"][seat].setdefault("bench", []).append(
                {"id": base, "hp": hp, "maxHp": hp, "appearThisTurn": True,
                 "preEvolution": [], "energies": [], "energyCards": [], "tools": []})
            gain = self.operation_gain(observation, deployed)
            if gain > 0.0:
                line_key = "-".join(str(card_id) for card_id in line)
                first_slot = len(mine.get("bench") or ())
                needs.extend(Need(
                    f"deploy:{line_key}:{first_slot + offset}", ((base, gain),),
                    recipient=line_key, capability="deploy", slot=str(first_slot + offset),
                    ceiling=gain)
                    for offset in range(missing))
        return tuple(needs)

    @staticmethod
    def _recipient(area: str, index: int, body) -> str:
        return str(body.get("serial", f"{area}:{index}:{body.get('id', 0)}"))

    def _heal_gain(self, observation, seat: int, clause: dict, *, target=None) -> float:
        if clause.get("rider") not in (None, "bounce_energy_to_hand"):
            return 0.0
        restriction = clause.get("restriction")
        if restriction not in (None, "active_only", "mega_only"):
            return 0.0
        condition = clause.get("condition")
        if condition not in (None, "energy_3_plus", "remaining_hp_30_or_less",
                             "played_supporter_this_turn"):
            return 0.0
        current = observation.get("current") or {}
        players = current.get("players") or ()
        mine = players[seat] if len(players) > seat else {}
        candidates = list(body_rows(mine))
        if target is not None:
            candidates = [row for row in candidates if row[:2] == target]
        if restriction == "active_only":
            candidates = [row for row in candidates if row[0] == "active"]
        elif restriction == "mega_only":
            candidates = [row for row in candidates
                          if bool(getattr(self.stat(row[2].get("id")), "megaEx", False))]
        if condition == "played_supporter_this_turn" and not current.get("supporterPlayed"):
            return 0.0

        def eligible(body):
            if condition == "energy_3_plus" and len(body.get("energyCards") or ()) < 3:
                return False
            if condition == "remaining_hp_30_or_less" and int(body.get("hp", 0)) > 30:
                return False
            return int(body.get("hp", 0)) < int(body.get("maxHp", body.get("hp", 0)))

        candidates = [row for row in candidates if eligible(row[2])]
        groups = (tuple(candidates),) if clause.get("each_of") else tuple((row,) for row in candidates)
        best = 0.0
        for group in groups:
            healed = copy.deepcopy(observation)
            gain = 0.0
            for area, index, original in group:
                body = healed["current"]["players"][seat][area][index]
                maximum = int(body.get("maxHp", body.get("hp", 0)))
                amount = maximum if clause.get("amount") == "all" else int(clause.get("amount", 0))
                restored = min(maximum - int(original.get("hp", 0)), amount)
                gain += restored / HEAL_DAMAGE_PER_VALUE * (
                    1.0 if area == "active" else BENCH_HEAL_VALUE_SHARE)
                body["hp"] = min(maximum, int(body.get("hp", 0)) + amount)
                gain = max(gain, self.operation_gain(observation, healed))
                if clause.get("rider") == "bounce_energy_to_hand":
                    player = healed["current"]["players"][seat]
                    bounced = tuple(body.get("energyCards") or ())
                    if player.get("hand") is None:
                        player["handCount"] = int(player.get("handCount", 0) or 0) + len(bounced)
                    else:
                        player.setdefault("hand", []).extend(bounced)
                    body["energyCards"] = []
                    body["energies"] = []
            gain = max(gain, self.operation_gain(observation, healed))
            best = max(best, gain)
        return best

    def coverage_slots(self, card_id: int, needs: tuple[Need, ...], *,
                       supporter_available: bool, discard_capacity: int,
                       available_targets=None, recipient: str | None = None,
                       provision_units: int = 1, recipient_units=None,
                       resource_group: str = "") -> tuple[tuple[CoverageEdge, ...], ...]:
        """Independent resources a card can supply, respecting printed fetch capacity.

        A multi-target fetch contributes one assignment token per printed target.  The tokens are
        capped by matching targets still available in the deck, so a Tutor is never an out once all
        of its relevant targets are visible, discarded, or known prized.
        """
        edges = {index: dict(need.direct).get(int(card_id), 0.0)
                 for index, need in enumerate(needs)
                 if recipient is None or need.recipient == recipient}
        edges = {index: value for index, value in edges.items() if value > 0.0}
        def edge(index, value, target=None, constraints=()):
            need = needs[index]
            group = (f"{need.recipient}:{need.capability}"
                     if need.alternative else "")
            return CoverageEdge(
                index, value, target, group, need.alternative, constraints)

        direct = tuple(edge(index, value) for index, value in sorted(edges.items()))
        stat = self.stat(card_id)
        if stat is not None and getattr(stat, "is_energy", False):
            if recipient is None and recipient_units is not None:
                tokens = []
                for unit_index in range(max(recipient_units.values(), default=0)):
                    token = tuple(
                        edge(index, value, constraints=(
                            (f"energy:{resource_group}", needs[index].recipient),))
                        for index, value in sorted(edges.items())
                        if int(recipient_units.get(needs[index].recipient, 1)) > unit_index
                    )
                    if token:
                        tokens.append(token)
                return tuple(tokens)
            units = max(1, int(provision_units))
            return tuple(direct for _ in range(units)) if direct else ()
        if stat is None or getattr(stat, "is_pokemon", False):
            return (direct,) if direct else ()
        if getattr(stat, "is_supporter", False) and not supporter_available:
            return (direct,) if direct else ()
        tokens = []
        clauses = tuple(self.effects.clauses(card_id)) if self.effects is not None else ()
        for clause in clauses:
            if clause.get("kind") != "fetch" or clause.get("zone") != "deck":
                continue
            if not all(not clause.get(field) for field in
                       ("trigger", "dig", "condition", "name_family")):
                continue
            if bool(clause.get("cost_required")) and discard_cost(clause) > discard_capacity:
                continue
            reachable = tuple(
                edge(index, value, int(target))
                for index, need in enumerate(needs)
                for target, value in need.direct
                if (fetch_target_matches(clause, self.stat(target), reading=REACH)
                    and (available_targets is None
                         or int(available_targets.get(int(target), 0)) > 0))
            )
            matching_targets = {
                edge.fetched_target for edge in reachable
            }
            remaining_targets = (sum(int(available_targets.get(target, 0))
                                     for target in matching_targets)
                                 if available_targets is not None else len(matching_targets))
            printed_capacity = max(1, int(clause.get("amount", 1) or 1))
            for _ in range(min(printed_capacity, remaining_targets)):
                if reachable:
                    tokens.append(reachable)
        return tuple(token for token in (direct, *tokens) if token)

    def supply_context(self, state, action) -> tuple[int | None, str | None, int]:
        if len(action.selection) != 1 or action.identity.kind not in {"play", "attach", "evolve"}:
            return None, None, 1
        options = tuple((state.obs.get("select") or {}).get("option") or ())
        option_index = action.selection[0]
        option = options[option_index] if 0 <= option_index < len(options) else {}
        players = (state.obs.get("current") or {}).get("players") or ()
        mine = players[state.root_seat] if state.root_seat < len(players) else {}
        hand = mine.get("hand") or ()
        hand_index = option.get("index")
        if not isinstance(hand_index, int) or not 0 <= hand_index < len(hand) or not hand[hand_index]:
            return None, None, 1
        card_id = int(hand[hand_index]["id"])
        if action.identity.kind == "play":
            return card_id, None, 1
        area = option.get("inPlayArea")
        index = option.get("inPlayIndex")
        zone = "active" if area == 4 else "bench" if area == 5 else None
        bodies = mine.get(zone) or () if zone is not None else ()
        if not isinstance(index, int) or not 0 <= index < len(bodies) or not bodies[index]:
            return card_id, None, 1
        body = bodies[index]
        recipient = self._recipient(zone, index, body)
        units = self._energy_units(card_id, body) if action.identity.kind == "attach" else 1
        return card_id, recipient, units

    def energy_units_by_recipient(self, observation, seat: int, card_id: int) -> dict[str, int]:
        players = (observation.get("current") or {}).get("players") or ()
        mine = players[seat] if seat < len(players) else {}
        return {
            self._recipient(area, index, body): self._energy_units(card_id, body)
            for area, index, body in body_rows(mine)
        }

    def uncovered_by_hand(self, needs: tuple[Need, ...], hand_ids, *,
                          supporter_available: bool, discard_capacity: int,
                          available_targets=None, observation=None,
                          seat: int = 0) -> tuple[Need, ...]:
        signatures = []
        for resource_index, card_id in enumerate(hand_ids):
            stat = self.stat(card_id)
            recipient_units = (self.energy_units_by_recipient(observation, seat, card_id)
                               if observation is not None and stat is not None
                               and getattr(stat, "is_energy", False) else None)
            signatures.extend(self.coverage_slots(
                int(card_id), needs,
                supporter_available=supporter_available,
                discard_capacity=discard_capacity,
                available_targets=available_targets,
                recipient_units=recipient_units,
                resource_group=f"held:{resource_index}"))
        assignment = best_assignment(signatures, len(needs), target_counts=available_targets)
        return tuple(need for index, need in enumerate(needs)
                     if not assignment.covered_mask & (1 << index))

    def next_turn_retained(self, observation, seat: int, hand_ids) -> RetainedAssignment:
        """Value deterministic next-turn uses of cards already visible now."""
        projected = self._next_turn_observation(observation, seat, hand_ids)
        original_player = observation["current"]["players"][seat]
        appeared = {(area, index) for area, index, body in body_rows(original_player)
                    if body.get("appearThisTurn")}
        options: list[RetainedOption] = []
        hand = projected["current"]["players"][seat].get("hand") or ()

        for area, index in sorted(appeared):
            body = projected["current"]["players"][seat][area][index]
            target = self._next_stage(body.get("id"))
            if target is None:
                continue
            for hand_index, card in enumerate(hand):
                if not card or int(card.get("id", 0)) != target:
                    continue
                evolved = self._evolve(projected, seat, area, index, target,
                                       consumed_cards=(hand_index,))
                gain = self.operation_gain(projected, evolved) * NEXT_TURN_OPTION_DISCOUNT
                if gain <= 0.0:
                    continue
                key = f"develop:{area}:{index}"
                option = RetainedOption(key, (hand_index,), gain,
                                        f"evolve:{area}:{index}:{target}")
                options.append(option)

        return best_retained_assignment(tuple(options))

    def new_next_turn_needs(self, observation, seat: int, *, current=None) -> tuple[Need, ...]:
        """Demands that first become actionable after turn allowances reset."""
        current = self.immediate(observation, seat) if current is None else tuple(current)
        deferred = tuple(need for need in current if need.timing == "next_turn")
        if deferred:
            return deferred
        if current:
            return ()
        projected = self._next_turn_observation(observation, seat, ())
        return self.immediate(projected, seat)

    def _next_stage(self, card_id) -> int | None:
        card_id = int(card_id or 0)
        for line in self.registry.lines:
            if card_id in line[:-1]:
                return int(line[line.index(card_id) + NEXT_STAGE_OFFSET])
        return None

    def _evolve(self, observation, seat: int, area: str, index: int, target: int, *,
                consumed_cards: tuple[int, ...] = ()):
        evolved = copy.deepcopy(observation)
        self._remove_hand_positions(evolved, seat, consumed_cards)
        body = evolved["current"]["players"][seat][area][index]
        previous = int(body.get("id", 0))
        target_stat = self.stat(target)
        old_max = int(body.get("maxHp", body.get("hp", 0)) or 0)
        damage = max(0, old_max - int(body.get("hp", old_max) or 0))
        body.setdefault("preEvolution", []).append({"id": previous})
        body["id"] = int(target)
        body["appearThisTurn"] = True
        if target_stat is not None and int(getattr(target_stat, "hp", 0) or 0) > 0:
            body["maxHp"] = int(target_stat.hp)
            body["hp"] = max(MINIMUM_BODY_HP, int(target_stat.hp) - damage)
        return evolved

    def _energy_units(self, card_id: int, body) -> int:
        return provision_units(
            self.registry.functions, card_id, evolved=bool(body.get("preEvolution")))

    @staticmethod
    def _tag_amount(tags, prefix: str) -> int:
        amounts = []
        for tag in tags:
            if not str(tag).startswith(prefix):
                continue
            try:
                amounts.append(max(0, int(str(tag).split(":", 1)[1])))
            except ValueError:
                continue
        return max(amounts, default=0)

    @staticmethod
    def _remove_hand_positions(observation, seat: int, positions) -> None:
        positions = tuple(positions)
        if not positions:
            return
        player = observation["current"]["players"][seat]
        hand = player.get("hand")
        if hand is None:
            return
        for position in sorted(set(int(value) for value in positions), reverse=True):
            if 0 <= position < len(hand):
                hand.pop(position)
        player["handCount"] = len(hand)

    @staticmethod
    def _next_turn_observation(observation, seat: int, hand_ids):
        projected = copy.deepcopy(observation)
        current = projected["current"]
        current["turn"] = int(current.get("turn", 0)) + 1
        current["supporterPlayed"] = False
        current["energyAttached"] = False
        current["retreated"] = False
        current["stadiumPlayed"] = False
        projected["bellmanActor"] = seat
        player = current["players"][seat]
        player["hand"] = [{"id": int(card_id)} for card_id in hand_ids]
        player["handCount"] = len(player["hand"])
        for _area, _index, body in body_rows(player):
            body["appearThisTurn"] = False
        return projected


__all__ = (
    "AccessEdge", "ActionFocus", "CapabilityIndex", "CoverageEdge", "Need", "NeedBeam",
    "NeedBeamBuilder", "NeedModel", "NeedPath", "NeedRoot", "PathFeatures", "PokemonRole",
    "ResolvedAssignment",
    "RetainedAssignment", "RetainedOption", "UnknownAction", "access_probability",
    "best_assignment", "best_retained_assignment", "coverage_signature", "infer_pokemon_roles",
    "opponent_threat_roots", "semantic_action_key",
)
