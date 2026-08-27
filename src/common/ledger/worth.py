"""Card demand: what this board can consume from its hand and attached Energy.

Demand classifies cards semantically; valuation coefficients are applied later by the Ledger.
Energy usability is MARGINAL: a unit counts only if it fills a still-unfilled slot of an attack
on the current body or a forward evolution already visible in hand."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from dataclasses import dataclass, field, fields, is_dataclass
from functools import lru_cache
from enum import Enum
from types import MappingProxyType
from typing import Mapping

from common.cards import FUNCTION_CATALOG, card_store, play_clauses
from common.cards.card_facts import COLORLESS, SUPPORTER, EnergyCard, PokemonCard, TrainerCard
from common.cards.functions.energy import provision_units
from common.cards.functions.fetch import DEADNESS, fetch_target_matches
from common.observation.knowledge import PROBABILITY_SCALE
from common.opponent import ArchetypeBelief, OpponentMechanic, OpponentTrait
from common.strategy import PrizePlan

from .configuration import DeckOverlay, ValuationConfiguration


CONTENT_ID_DIGEST_BYTES = 16
MODEL_ID_DIGEST_BYTES = 8
MULTI_PROVISION_UNITS = 2


@dataclass(frozen=True)
class EvaluationModel:
    """Everything deck-scoped the evaluator needs for observable valuation."""

    configuration: ValuationConfiguration
    store: Mapping[int, object] = field(repr=False)
    prize_plan: PrizePlan = PrizePlan()
    opponent_profiles: Mapping[str, "OpponentProfile"] = field(
        default_factory=dict, repr=False)
    store_identity: str = field(init=False)
    _identity: str = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        identity = (_default_store_identity() if self.store is card_store()
                    else content_identity(self.store))
        object.__setattr__(self, "store_identity", identity)
        object.__setattr__(self, "_identity", _model_identity(
            self.configuration, identity, self.prize_plan,
            self.opponent_profiles))

    @classmethod
    def build(cls, *, configuration: ValuationConfiguration | None = None,
              overlay: DeckOverlay | None = None,
              prize_plan: PrizePlan | None = None,
              opponent_profiles: Mapping[str, "OpponentProfile"] | None = None,
              ) -> "EvaluationModel":
        configured = (configuration or ValuationConfiguration.general()).resolve(
            overlay or DeckOverlay())
        store = card_store()
        for facts in store.values():
            clauses = list(getattr(facts, "clauses", ()) or ())
            for ability in getattr(facts, "abilities", ()) or ():
                clauses.extend(ability.clauses)
            for attack in getattr(facts, "attacks", ()) or ():
                clauses.extend(attack.clauses)
            FUNCTION_CATALOG.compile(clauses)
        profiles = MappingProxyType(dict(sorted((opponent_profiles or {}).items())))
        return cls(configuration=configured, store=store,
                   prize_plan=prize_plan or PrizePlan(), opponent_profiles=profiles)

    @property
    def identity(self) -> str:
        return self._identity

    def facts(self, card_id: int):
        return self.store.get(int(card_id))

def _canonical(value):
    if is_dataclass(value) and not isinstance(value, type):
        return tuple((item.name, _canonical(getattr(value, item.name)))
                     for item in fields(value))
    if isinstance(value, Mapping):
        return tuple((_canonical(key), _canonical(child))
                     for key, child in sorted(value.items(), key=lambda item: repr(item[0])))
    if isinstance(value, Enum):
        return _canonical(value.value)
    if isinstance(value, (tuple, list)):
        return tuple(_canonical(child) for child in value)
    if isinstance(value, (set, frozenset)):
        return tuple(sorted((_canonical(child) for child in value), key=repr))
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if hasattr(value, "kind") and isinstance(getattr(value, "params", None), Mapping):
        return (("kind", str(value.kind)), ("params", _canonical(value.params)))
    raise TypeError(f"unsupported Evaluation Model identity input {type(value).__name__}")


def content_identity(value) -> str:
    blob = json.dumps(_canonical(value), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.blake2b(blob, digest_size=CONTENT_ID_DIGEST_BYTES).hexdigest()


def _model_identity(configuration, store_identity, prize_plan, opponent_profiles):
    payload = {
        "configuration": configuration.identity,
        "prize_plan": prize_plan.identity,
        "store": store_identity,
        "opponent_profiles": {
            name: profile.canonical_data()
            for name, profile in opponent_profiles.items()},
    }
    blob = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.blake2b(blob, digest_size=MODEL_ID_DIGEST_BYTES).hexdigest()


@lru_cache(maxsize=1)
def _default_store_identity() -> str:
    return content_identity(card_store())


# --- energy usability -------------------------------------------------------------------

@lru_cache(maxsize=1)
def _forward_lines() -> Mapping[str, tuple[int, ...]]:
    """name -> ids of every card in the store that evolves (transitively) from that name."""
    return _compile_forward_lines(card_store())


def _compile_forward_lines(store) -> Mapping[str, tuple[int, ...]]:
    parents: dict[str, str | None] = {}
    for card in store.values():
        if not isinstance(card, PokemonCard):
            continue
        previous = parents.setdefault(card.name, card.evolves_from)
        if previous != card.evolves_from:
            raise ValueError(f"conflicting evolution parents for {card.name!r}")
    forward: dict[str, list[int]] = {}
    for card_id, card in store.items():
        if not isinstance(card, PokemonCard):
            continue
        base = card.evolves_from
        seen: set[str] = set()
        while base is not None:
            if base in seen or base == card.name:
                raise ValueError(f"evolution relationships contain a cycle at {base!r}")
            seen.add(base)
            forward.setdefault(base, []).append(card_id)
            base = parents.get(base)
    return {name: tuple(ids) for name, ids in forward.items()}


def _line_entries(body_facts, ctx: EvaluationModel):
    """(attack, evolution id or None for the body's own attacks) over the forward line."""
    for attack in getattr(body_facts, "attacks", ()) or ():
        yield attack, None
    if body_facts is None:
        return
    for evo_id in _forward_lines().get(body_facts.name, ()):
        for attack in getattr(ctx.facts(evo_id), "attacks", ()) or ():
            yield attack, evo_id


class Reach(str, Enum):
    HAND = "hand"
    FETCHABLE = "fetchable"
    NEXT_TURN = "next_turn"
    ABSENT = "absent"


class DemandState(str, Enum):
    LIVE = "live"
    DEAD = "dead"
    SETUP = "setup"
    COLORLESS_ONLY = "colorless_only"


_DEMAND_PRIORITY = {
    DemandState.DEAD: 0,
    DemandState.COLORLESS_ONLY: 1,
    DemandState.SETUP: 1,
    DemandState.LIVE: 2,
}


def line_reach(hand_name_counts, deck_counts, ctx: EvaluationModel, *, hand=(), turn=None) -> Mapping[int, Reach]:
    """Forward evolutions visible in hand now or still present for a later turn."""
    in_deck = None if deck_counts is None else {
        int(card_id) for card_id, count in deck_counts if count > 0}
    gates: dict[int, Reach] = {}
    for ids in _forward_lines().values():
        for evo_id in ids:
            facts = ctx.facts(evo_id)
            if facts is not None and hand_name_counts.get(facts.name, 0):
                gates[evo_id] = Reach.HAND
            elif (facts is not None and in_deck is not None and evo_id in in_deck
                  and _held_fetch_reaches(hand, turn, facts, ctx)):
                gates[evo_id] = Reach.FETCHABLE
            elif in_deck is None or evo_id in in_deck:
                gates[evo_id] = Reach.NEXT_TURN if in_deck is not None else Reach.ABSENT
            else:
                gates[evo_id] = Reach.ABSENT
    return gates


def _reach_scale(status: Reach) -> float:
    if status in {Reach.HAND, Reach.FETCHABLE}:
        return 1.0
    if isinstance(status, (int, float)):
        return max(0.0, min(1.0, float(status)))
    return 0.0


def legal_line_reach(body, reach, ctx: EvaluationModel, hand=(), turn=None) -> Mapping[int, Reach | float]:
    card = getattr(body, "card", None)
    facts = ctx.facts(card.card_id) if card is not None else body
    if facts is None:
        return {}
    direct = {card_id for card_id in _forward_lines().get(facts.name, ())
              if getattr(card_store().get(card_id), "evolves_from", None) == facts.name}
    legal = {card_id: status for card_id, status in reach.items() if card_id in direct}
    if getattr(body, "appeared_this_turn", False):
        return {card_id: (status if isinstance(status, (int, float)) else Reach.NEXT_TURN)
                for card_id, status in legal.items()}
    candy = any(
        clause.kind == "fetch" and clause.zone == "hand" and clause.rider == "skip_stage1"
        for card in hand for clause in play_clauses(ctx.facts(card.card_id)))
    if candy and turn is not None and turn.number > 1 and getattr(facts, "stage", None) == "basic":
        for card_id in _forward_lines().get(facts.name, ()):
            target = card_store().get(card_id)
            if getattr(target, "stage", None) == "stage2" and reach.get(card_id) is Reach.HAND:
                legal[card_id] = Reach.HAND
    return legal


@dataclass(frozen=True)
class OpponentEvaluation:
    candidates: tuple[ArchetypeBelief, ...]
    unknown_mass: float
    failures: tuple[str, ...] = ()


@dataclass(frozen=True)
class OpponentProfile:
    roles: Mapping[int, tuple[str, ...]]
    traits: tuple[OpponentTrait, ...]
    mechanics: tuple[OpponentMechanic, ...]
    resources: Mapping[int, float]

    def canonical_data(self):
        return {
            "roles": tuple(sorted(self.roles.items())),
            "traits": tuple((item.name, item.value) for item in self.traits),
            "mechanics": tuple((item.name, item.probability) for item in self.mechanics),
            "resources": tuple(sorted(self.resources.items())),
        }


def opponent_evaluation(board, ctx: EvaluationModel) -> OpponentEvaluation | None:
    evidence = board.knowledge.opponent.decision_evidence
    if evidence is None:
        return None
    def probability(value):
        return (value / PROBABILITY_SCALE if isinstance(value, int) else float(value))

    missing = tuple(candidate.archetype for candidate in evidence.candidates
                    if candidate.archetype not in ctx.opponent_profiles)
    candidates = tuple(ArchetypeBelief(
        probability(candidate.probability),
        roles=profile.roles,
        traits=profile.traits,
        mechanics=profile.mechanics,
        archetype=candidate.archetype,
        resources=profile.resources,
    ) for candidate in evidence.candidates
      for profile in (ctx.opponent_profiles.get(
          candidate.archetype, OpponentProfile({}, (), (), {})),))
    unknown = probability(evidence.unknown_mass)
    failures = tuple(f"missing opponent profile: {archetype}" for archetype in missing)
    return OpponentEvaluation(candidates, unknown, failures)


def opponent_line_reach(ctx: EvaluationModel, opponent=None) -> Mapping[int, float]:
    if opponent is None:
        return {}
    ids = {evo_id for line in _forward_lines().values() for evo_id in line}
    return {evo_id: sum(candidate.probability * candidate.resources.get(evo_id, 0.0)
                        for candidate in opponent.candidates)
            for evo_id in ids
            if any(candidate.resources.get(evo_id, 0.0)
                   for candidate in opponent.candidates)}


def _held_fetch_reaches(hand, turn, target, ctx: EvaluationModel) -> bool:
    for card in hand:
        facts = ctx.facts(card.card_id)
        if not isinstance(facts, TrainerCard):
            continue
        if facts.kind == SUPPORTER and (turn is None or turn.supporter_played):
            continue
        if any(clause.kind == "fetch" and clause.zone == "deck"
               and _fetch_cost_payable(clause, len(hand) - 1)
               and fetch_target_matches(clause, target)
               for clause in play_clauses(facts)):
            return True
    return False


def _fetch_cost_payable(clause, other_hand_cards: int) -> bool:
    cost = str(clause.cost or "")
    if cost.startswith("discard_") and cost.removeprefix("discard_").isdigit():
        return other_hand_cards >= int(cost.removeprefix("discard_"))
    return not clause.cost_required or cost in {"", "discard_hand"}


def _unfilled(cost, attached: Counter) -> tuple[Counter, int]:
    """Typed slots still open after the attached units fill their own colors, and colorless
    slots still open after the leftovers spill into them."""
    need = Counter(unit for unit in cost if unit != COLORLESS)
    colorless = sum(1 for unit in cost if unit == COLORLESS)
    spent = 0
    open_typed = Counter()
    for unit, count in need.items():
        used = min(count, attached.get(unit, 0))
        spent += used
        if count > used:
            open_typed[unit] = count - used
    leftovers = sum(attached.values()) - spent
    return open_typed, max(0, colorless - leftovers)


def any_attack_payable(body_facts, attached) -> bool:
    """Can the body pay some printed attack of its own with what is already attached?"""
    counts = Counter(attached)
    for attack in getattr(body_facts, "attacks", ()) or ():
        open_typed, open_colorless = _unfilled(attack.cost, counts)
        if not open_typed and open_colorless == 0:
            return True
    return False


def _slot_fill(unit: int, body_facts, attached, ctx: EvaluationModel, reach=None) -> str:
    """Classify the slot filled by one more Energy unit on this body or forward line.
    Forward-line colorless slots require positive reach; typed slots do not."""
    counts = Counter(attached)
    gates = reach or {}
    for attack, evo_id in _line_entries(body_facts, ctx):
        if (evo_id is not None
                and _reach_scale(gates.get(evo_id, Reach.ABSENT)) <= 0.0):
            continue
        open_typed, _ = _unfilled(attack.cost, counts)
        if open_typed.get(unit, 0) > 0:
            return "typed"
    for attack, evo_id in _line_entries(body_facts, ctx):
        if (evo_id is not None
                and _reach_scale(gates.get(evo_id, Reach.ABSENT)) <= 0.0):
            continue
        _, open_colorless = _unfilled(attack.cost, counts)
        if open_colorless > 0:
            return "colorless"
    return "dead"


def _wr_adjusted(damage: int, attacker_type, defender_facts) -> int:
    """Printed damage through the defender's weakness (x2) / resistance (-30) record."""
    if defender_facts is not None and attacker_type is not None:
        if getattr(defender_facts, "weakness", None) == attacker_type:
            damage *= WEAKNESS_MULTIPLIER
        if getattr(defender_facts, "resistance", None) == attacker_type:
            damage = max(0, damage - RESISTANCE_REDUCTION)
    return damage


def best_payable_damage(attacker_facts, attached, defender_facts) -> int:
    """Largest damage the attacker can land THIS turn on the defender: fully-paid printed
    attacks only, weakness doubled / resistance -30 where the defender's record shows them."""
    counts = Counter(attached)
    attacker_type = getattr(attacker_facts, "energy_type", None)
    best = 0
    for attack in getattr(attacker_facts, "attacks", ()) or ():
        open_typed, open_colorless = _unfilled(attack.cost, counts)
        if open_typed or open_colorless:
            continue
        damage = int(getattr(attack, "damage", 0) or 0)
        if damage > 0:
            best = max(best, _wr_adjusted(damage, attacker_type, defender_facts))
    return best


def usable_units(body_facts, attached, ctx: EvaluationModel, reach=None) -> float:
    """Return the largest attached-unit count one attack absorbs.
    Forward-line colorless absorption scales by that evolution's reach gate."""
    counts = Counter(attached)
    total = sum(counts.values())
    if total == 0 or body_facts is None:
        return 0
    gates = reach or {}
    best = 0.0
    for attack, evo_id in _line_entries(body_facts, ctx):
        typed = sum(min(count, counts.get(unit, 0))
                    for unit, count in Counter(u for u in attack.cost if u != COLORLESS).items())
        colorless_slots = min(sum(1 for u in attack.cost if u == COLORLESS), total - typed)
        status = Reach.HAND if evo_id is None else gates.get(evo_id, Reach.ABSENT)
        scale = _reach_scale(status)
        best = max(best, (typed + colorless_slots) * scale)
        if best >= total:
            return total
    return best


def development_reach_units(body_facts, attached, ctx: EvaluationModel, reach=None):
    counts = Counter(attached)
    total = sum(counts.values())
    visible = future = 0.0
    for attack, evo_id in _line_entries(body_facts, ctx):
        if evo_id is None:
            continue
        status = (reach or {}).get(evo_id, Reach.ABSENT)
        typed = sum(min(count, counts.get(unit, 0))
                    for unit, count in Counter(u for u in attack.cost if u != COLORLESS).items())
        colorless = min(sum(1 for unit in attack.cost if unit == COLORLESS), total - typed)
        units = typed + colorless
        if status in {Reach.HAND, Reach.FETCHABLE}:
            visible = max(visible, units)
        elif status is Reach.NEXT_TURN:
            future = max(future, units)
        elif isinstance(status, (int, float)):
            future = max(future, units * max(0.0, min(1.0, float(status))))
    return visible, future


# --- demand -----------------------------------------------------------------------------

@dataclass(frozen=True)
class Demand:
    """What my side of the board is currently asking for, read once per evaluation."""

    body_name_counts: Mapping[str, int]
    body_id_counts: Mapping[int, int]
    hand_name_counts: Mapping[str, int]
    bodies: tuple = ()
    free_bench: int = 0
    hand: tuple = ()
    turn: object = None

    @classmethod
    def read(cls, side, ctx: EvaluationModel, turn=None) -> "Demand":
        bodies = side.bodies
        names = Counter(facts.name for body in bodies
                        if (facts := ctx.facts(body.card.card_id)) is not None)
        hand_names = Counter(facts.name for card in (side.hand or ())
                             if (facts := ctx.facts(card.card_id)) is not None)
        return cls(body_name_counts=names,
                   body_id_counts=Counter(body.card.card_id for body in bodies),
                   hand_name_counts=hand_names, bodies=bodies,
                   free_bench=max(0, side.bench_max - len(side.bench)),
                   hand=tuple(side.hand or ()), turn=turn)


def _liveness(card_id, facts, demand: Demand, ctx: EvaluationModel, deck_counts):
    """Semantic demand state and number of copies the board can consume."""
    if facts is None:
        return DemandState.LIVE, None
    if isinstance(facts, PokemonCard):
        if facts.evolves_from is None:
            live = demand.free_bench > 0
            return (DemandState.LIVE if live else DemandState.DEAD), max(1, demand.free_bench)
        targets = demand.body_name_counts.get(facts.evolves_from, 0)
        if targets:
            return DemandState.LIVE, max(1, targets)
        # The pair term: base in HAND is setup pending — worth more together than apart.
        if demand.hand_name_counts.get(facts.evolves_from, 0):
            return DemandState.SETUP, 1
        return DemandState.DEAD, 1
    if isinstance(facts, EnergyCard):
        reach = line_reach(demand.hand_name_counts, deck_counts, ctx,
                           hand=demand.hand, turn=demand.turn)
        colorless_only = False
        for body in demand.bodies:
            body_reach = legal_line_reach(body, reach, ctx, demand.hand, demand.turn)
            fills = _slot_fill(facts.provides, ctx.facts(body.card.card_id),
                               body.energies, ctx, body_reach)
            if fills == "typed" or _multi_provision_live(facts, body, ctx):
                return DemandState.LIVE, None
            colorless_only = colorless_only or fills == "colorless"
        return (DemandState.COLORLESS_ONLY if colorless_only
                else DemandState.DEAD), None
    if isinstance(facts, TrainerCard):
        clauses = tuple(getattr(facts, "clauses", ()) or ())
        fetches = tuple(c for c in clauses if c.kind == "fetch" and c.zone == "deck")
        if fetches and len(fetches) == len(clauses):
            return _fetch_liveness(fetches, demand, ctx, deck_counts), (
                1 if facts.kind == SUPPORTER else None)
        if facts.kind == SUPPORTER:
            return DemandState.LIVE, 1
    return DemandState.LIVE, None


def _multi_provision_live(facts, body, ctx: EvaluationModel) -> bool:
    """Return whether this body can absorb at least two units from one special Energy.
    Ignore speculative multi-provision that only a future evolution could absorb."""
    body_facts = ctx.facts(body.card.card_id)
    if not isinstance(body_facts, PokemonCard):
        return False
    provided = provision_units(facts, evolved=body_facts.evolves_from is not None)
    if provided < MULTI_PROVISION_UNITS:
        return False
    counts = Counter(body.energies)
    for attack in getattr(body_facts, "attacks", ()) or ():
        _, open_colorless = _unfilled(attack.cost, counts)
        if open_colorless >= MULTI_PROVISION_UNITS:
            return True
    return False


def _fetch_liveness(fetches, demand: Demand, ctx: EvaluationModel, deck_counts) -> DemandState:
    """A deck fetch is as live as its best reachable target."""
    if deck_counts is None:
        return DemandState.LIVE
    best = DemandState.DEAD
    for target_id, count in deck_counts:
        if count <= 0:
            continue
        target = ctx.facts(target_id)
        if not any(fetch_target_matches(clause, target, reading=DEADNESS)
                   for clause in fetches):
            continue
        state, _ = _liveness(target_id, target, demand, ctx, None)
        if _DEMAND_PRIORITY[state] > _DEMAND_PRIORITY[best]:
            best = state
        if best is DemandState.LIVE:
            break
    return best

WEAKNESS_MULTIPLIER = 2
RESISTANCE_REDUCTION = 30


__all__ = ("Demand", "EvaluationModel",
           "any_attack_payable", "legal_line_reach", "line_reach", "opponent_line_reach",
           "usable_units")
