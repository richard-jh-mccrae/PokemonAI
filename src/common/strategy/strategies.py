"""Serializable strategy declarations that form the first Bellman search beam."""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import json


_SCOPES = frozenset({"general", "deck", "opponent"})
_DEADLINES = frozenset({"immediate", "this_turn", "next_turn"})
_CONVICTIONS = frozenset({"high", "medium", "low"})
_OPERATORS = frozenset({
    "eq", "ne", "lt", "le", "gt", "ge", "contains", "not_contains", "missing",
})


@dataclass(frozen=True)
class ActivationCondition:
    fact: str
    operator: str
    value: object = None

    def __post_init__(self) -> None:
        if not self.fact or self.operator not in _OPERATORS:
            raise ValueError("invalid strategy activation condition")


@dataclass(frozen=True)
class DesiredFact:
    kind: str
    recipient: str
    amount: int = 1
    target_card_ids: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if not self.kind or not self.recipient or int(self.amount) <= 0:
            raise ValueError("invalid desired board fact")
        object.__setattr__(self, "amount", int(self.amount))
        object.__setattr__(self, "target_card_ids", tuple(
            int(card_id) for card_id in self.target_card_ids))


@dataclass(frozen=True)
class StrategyHint:
    identifier: str
    scope: str
    conditions: tuple[ActivationCondition, ...]
    desired_facts: tuple[DesiredFact, ...]
    recipient_selector: str
    deadline: str
    conviction: str
    provenance: str
    enabled: bool = True
    bundle_id: str | None = None
    waypoint: int = 0

    def __post_init__(self) -> None:
        if (not self.identifier or self.scope not in _SCOPES or not self.recipient_selector
                or self.deadline not in _DEADLINES or self.conviction not in _CONVICTIONS
                or not self.provenance or not self.desired_facts or int(self.waypoint) < 0):
            raise ValueError("invalid strategy declaration")
        object.__setattr__(self, "conditions", tuple(self.conditions))
        object.__setattr__(self, "desired_facts", tuple(self.desired_facts))
        object.__setattr__(self, "waypoint", int(self.waypoint))
        if self.bundle_id is not None and not self.bundle_id:
            raise ValueError("invalid strategy bundle")
        if any(fact.recipient != self.recipient_selector for fact in self.desired_facts):
            raise ValueError("desired fact recipient must match strategy recipient selector")

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class StrategyOverride:
    strategy_id: str
    enabled: bool | None = None
    additional_conditions: tuple[ActivationCondition, ...] = ()

    def __post_init__(self) -> None:
        if not self.strategy_id or (self.enabled is None and not self.additional_conditions):
            raise ValueError("empty strategy override")
        object.__setattr__(self, "additional_conditions", tuple(self.additional_conditions))

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ResolvedStrategies:
    general: tuple[StrategyHint, ...]
    deck: tuple[StrategyHint, ...]
    opponent: tuple[StrategyHint, ...]
    overrides: tuple[StrategyOverride, ...]
    effective: tuple[StrategyHint, ...]
    content_hash: str

    def as_dict(self) -> dict:
        return {
            "general": [row.as_dict() for row in self.general],
            "deck": [row.as_dict() for row in self.deck],
            "opponent": [row.as_dict() for row in self.opponent],
            "overrides": [row.as_dict() for row in self.overrides],
            "effective": [row.as_dict() for row in self.effective],
            "content_hash": self.content_hash,
        }


@dataclass(frozen=True)
class ActivatedStrategy:
    strategy_id: str
    kind: str
    recipient: str
    recipient_card_id: int | None
    recipient_serial: int | None
    target_card_ids: tuple[int, ...]
    deadline: str
    conviction: str
    bundle_id: str | None = None
    waypoint: int = 0
    amount: int = 1


@dataclass(frozen=True)
class StrategySnapshot:
    turn: int
    seat: int
    strategy_hash: str
    snapshot_id: str
    active_ids: tuple[str, ...]
    inactive_ids: tuple[str, ...]
    hints: tuple[ActivatedStrategy, ...]


def strategy_hint_from_dict(raw: dict, *, scope: str, provenance: str) -> StrategyHint:
    """Build one serialized Strategy Hint with caller-owned scope and provenance."""
    return StrategyHint(
        identifier=str(raw["identifier"]),
        scope=scope,
        conditions=tuple(ActivationCondition(**row) for row in raw.get("conditions", ())),
        desired_facts=tuple(DesiredFact(**row) for row in raw.get("desired_facts", ())),
        recipient_selector=str(raw["recipient_selector"]),
        deadline=str(raw["deadline"]),
        conviction=str(raw.get("conviction", raw.get("confidence", ""))),
        provenance=provenance,
        enabled=bool(raw.get("enabled", True)),
        bundle_id=(str(raw["bundle_id"]) if raw.get("bundle_id") is not None else None),
        waypoint=int(raw.get("waypoint", 0)),
    )


def _player(observation: dict, seat: int) -> dict:
    players = ((observation.get("current") or {}).get("players") or ())
    return players[seat] if 0 <= seat < len(players) and players[seat] else {}


def _active_body(player: dict) -> dict:
    active = player.get("active") or ()
    return active[0] if active and active[0] else {}


def _attack_ready(body: dict, stats) -> bool:
    if not body or stats is None:
        return False
    stat = stats.get(body.get("id")) if body.get("id") is not None else None
    attacks = tuple(getattr(stat, "attacks", ()) or ()) if stat is not None else ()
    attack_lookup = (getattr(stats, "attack", None)
                     or getattr(stats, "get_attack", None))
    if not attacks or attack_lookup is None:
        return False
    from common.energy import unmet_cost_slots

    provisions = body.get("energies") or ()
    requirements = tuple(
        tuple(getattr(attack_lookup(attack_id), "energyTypes", ()) or ())
        for attack_id in attacks)
    maximum = max((len(cost) for cost in requirements), default=0)
    return any(len(cost) == maximum and not unmet_cost_slots(provisions, cost)
               for cost in requirements)


def _visible_facts(observation: dict, *, roles, stats=None,
                   opponent_role_worth=None) -> dict:
    current = observation.get("current") or {}
    seat = int(current.get("yourIndex", 0))
    player = _player(observation, seat)
    active = _active_body(player)
    card_id = int(active["id"]) if active.get("id") is not None else None
    card_roles = tuple(roles.get(card_id, ())) if card_id is not None else ()
    bench = tuple(body for body in player.get("bench") or () if body)
    opponent = _player(observation, 1 - seat)
    opponent_bench = tuple(body for body in opponent.get("bench") or () if body)
    opponent_role_worth = opponent_role_worth or {}
    options = tuple((observation.get("select") or {}).get("option") or ())
    can_attack = any(int(option.get("type", -1)) == 13 for option in options)
    commitment_available = (not bool(current.get("energyAttached"))
                            or (card_id in roles.evolves if card_id is not None else False))
    facts = {
        "own.active.card_id": card_id,
        "own.active.role": card_roles,
        "own.active.is_attacker": bool(
            {"primary_attacker", "backup_attacker"}.intersection(card_roles)),
        "own.active.energy_count": len(active.get("energies") or ()),
        "own.active.hp_fraction": (
            int(active.get("hp", 0)) / max(1, int(active.get("maxHp", active.get("hp", 1))))
            if active else 0.0),
        "own.active.attack_ready": _attack_ready(active, stats),
        "own.active.can_attack": can_attack,
        "own.active.evolvable": card_id in roles.evolves if card_id is not None else False,
        "own.bench.evolvable_count": sum(
            1 for body in bench if body.get("id") in roles.evolves),
        "own.bench.card_ids": tuple(int(body.get("id", 0)) for body in bench),
        "own.bench.space": max(0, int(player.get("benchMax", 5)) - len(bench)),
        "opponent.bench.card_ids": tuple(
            int(body.get("id", 0)) for body in opponent_bench),
        "opponent.bench.role_target_count": sum(
            float(opponent_role_worth.get(int(body.get("id", 0)), 0.0)) > 0.0
            for body in opponent_bench),
        "opponent.bench.highest_role.hp": int(_recipient_body(
            observation, seat, "opponent.bench.highest_role", roles,
            opponent_role_worth).get("hp", 0)),
        "turn.commitment_available": commitment_available,
        # The condition language has no OR; a boost pays off while a commitment can still create
        # an attack OR one is already offered (PR #533 review: the post-attach committed case).
        "turn.boostable_attack_available": commitment_available or can_attack,
    }
    return facts


def _recipient_body(observation: dict, seat: int, selector: str, roles,
                    opponent_role_worth=None) -> dict:
    player = _player(observation, seat)
    if selector == "own.active":
        return _active_body(player)
    if selector == "own.bench.evolvable:first":
        return next((body for body in player.get("bench") or ()
                     if body and body.get("id") in roles.evolves), {})
    if selector == "opponent.bench.highest_role":
        opponent = _player(observation, 1 - seat)
        worth = opponent_role_worth or {}
        return max(
            (body for body in opponent.get("bench") or () if body),
            key=lambda body: (
                float(worth.get(int(body.get("id", 0)), 0.0)),
                -int(body.get("hp", 0)),
                -int(body.get("serial", body.get("id", 0))),
            ),
            default={},
        )
    return {}


def _condition_matches(condition: ActivationCondition, facts: dict) -> bool:
    present = condition.fact in facts
    actual = facts.get(condition.fact)
    expected = condition.value
    operations = {
        "eq": lambda: actual == expected,
        "ne": lambda: actual != expected,
        "lt": lambda: present and actual < expected,
        "le": lambda: present and actual <= expected,
        "gt": lambda: present and actual > expected,
        "ge": lambda: present and actual >= expected,
        "contains": lambda: present and expected in actual,
        "not_contains": lambda: present and expected not in actual,
        "missing": lambda: not present,
    }
    try:
        return bool(operations[condition.operator]())
    except (TypeError, ValueError):
        return False


def activate_strategies(observation: dict, resolved: ResolvedStrategies, *, roles,
                        stats=None, opponent_role_worth=None) -> StrategySnapshot:
    current = observation.get("current") or {}
    turn = int(current.get("turn", 0))
    seat = int(current.get("yourIndex", 0))
    facts = _visible_facts(
        observation, roles=roles, stats=stats,
        opponent_role_worth=opponent_role_worth)
    active_rows = tuple(
        row for row in resolved.effective
        if all(_condition_matches(condition, facts) for condition in row.conditions)
    )
    active_ids = tuple(row.identifier for row in active_rows)
    inactive_ids = tuple(
        row.identifier for row in resolved.effective if row.identifier not in active_ids)
    hints = []
    for row in active_rows:
        for desired in row.desired_facts:
            recipient_body = _recipient_body(
                observation, seat, desired.recipient, roles, opponent_role_worth)
            recipient_card_id = (int(recipient_body["id"])
                                 if recipient_body.get("id") is not None else None)
            recipient_serial = (int(recipient_body["serial"])
                                if recipient_body.get("serial") is not None else None)
            targets = desired.target_card_ids
            if (not targets and desired.kind == "evolve"
                    and recipient_card_id in roles.evolves):
                targets = (int(roles.evolves[recipient_card_id]),)
            hints.append(ActivatedStrategy(
                row.identifier, desired.kind, desired.recipient,
                recipient_card_id, recipient_serial,
                targets, row.deadline, row.conviction, row.bundle_id, row.waypoint,
                int(desired.amount),
            ))
    payload = {
        "turn": turn,
        "seat": seat,
        "strategy_hash": resolved.content_hash,
        "active_ids": active_ids,
        "inactive_ids": inactive_ids,
        "hints": [asdict(row) for row in hints],
    }
    snapshot_id = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return StrategySnapshot(
        turn, seat, resolved.content_hash, snapshot_id,
        active_ids, inactive_ids, tuple(hints),
    )


def resolve_strategies(general, deck=(), opponent=(), overrides=()) -> ResolvedStrategies:
    general = tuple(general)
    deck = tuple(deck)
    opponent = tuple(opponent)
    overrides = tuple(overrides)
    declared = (*general, *deck, *opponent)
    by_id = {row.identifier: row for row in declared}
    if len(by_id) != len(declared):
        raise ValueError("duplicate strategy identifier")
    unknown = {row.strategy_id for row in overrides} - set(by_id)
    if unknown:
        raise ValueError(f"unknown strategy override: {sorted(unknown)}")
    override_by_id = {row.strategy_id: row for row in overrides}
    if len(override_by_id) != len(overrides):
        raise ValueError("duplicate strategy override")
    effective = []
    for row in declared:
        override = override_by_id.get(row.identifier)
        if override is not None:
            row = replace(
                row,
                enabled=row.enabled if override.enabled is None else override.enabled,
                conditions=(*row.conditions, *override.additional_conditions),
            )
        if row.enabled:
            effective.append(row)
    effective = tuple(sorted(effective, key=lambda row: row.identifier))
    payload = {
        "general": [row.as_dict() for row in general],
        "deck": [row.as_dict() for row in deck],
        "opponent": [row.as_dict() for row in opponent],
        "overrides": [row.as_dict() for row in overrides],
        "effective": [row.as_dict() for row in effective],
    }
    content_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return ResolvedStrategies(general, deck, opponent, overrides, effective, content_hash)


GENERAL_STRATEGIES = (
    StrategyHint(
        "general.fund_active_attacker",
        "general",
        (
            ActivationCondition("own.active.is_attacker", "eq", True),
            # Below half health the body is a heal-or-replace question; above it funding
            # stays live — exact viability of the recipient is Bellman's call.
            ActivationCondition("own.active.hp_fraction", "ge", 0.5),
            ActivationCondition("own.active.attack_ready", "eq", False),
        ),
        (DesiredFact("fund_attack", "own.active"),),
        "own.active",
        "this_turn",
        "high",
        "shared-general",
    ),
    StrategyHint(
        "general.evolve_active_attacker",
        "general",
        (
            ActivationCondition("own.active.evolvable", "eq", True),
        ),
        (DesiredFact("evolve", "own.active"),),
        "own.active",
        "this_turn",
        "high",
        "shared-general",
    ),
    StrategyHint(
        "general.heal_damaged_active_attacker",
        "general",
        (
            ActivationCondition("own.active.role", "contains", "primary_attacker"),
            ActivationCondition("own.active.hp_fraction", "lt", 0.70),
        ),
        (DesiredFact("heal", "own.active"),),
        "own.active",
        "immediate",
        "high",
        "shared-general",
    ),
    StrategyHint(
        "general.low_cost_information_access_before_commitment",
        "general",
        (ActivationCondition("turn.commitment_available", "eq", True),),
        (DesiredFact("low_cost_information_access", "turn"),),
        "turn",
        "immediate",
        "high",
        "shared-general",
    ),
    StrategyHint(
        # A this-turn damage boost pays off only if the boosted attack is still ahead of it in
        # the same epoch; schedule it early so search reaches that attack before the caps.
        "general.boost_the_committed_attack",
        "general",
        (ActivationCondition("turn.boostable_attack_available", "eq", True),),
        (DesiredFact("damage_boost", "turn"),),
        "turn",
        "this_turn",
        "medium",
        "shared-general",
    ),
)


__all__ = (
    "ActivationCondition", "DesiredFact", "GENERAL_STRATEGIES", "StrategyHint",
    "ActivatedStrategy", "ResolvedStrategies", "StrategyOverride", "StrategySnapshot",
    "activate_strategies", "resolve_strategies", "strategy_hint_from_dict",
)
