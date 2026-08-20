"""Serializable strategy declarations: the language decks and Briefs author hints in."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import re

_SCOPES = frozenset({"general", "deck", "opponent"})
_DEADLINES = frozenset({"immediate", "this_turn", "next_turn"})
_CONVICTIONS = frozenset({"high", "medium", "low"})
#: Prefix of the card-named Bench recipient selector: ``own.bench.card:<card_id>``.
_BENCH_CARD = "own.bench.card:"
_OPERATORS = frozenset({
    "eq", "ne", "lt", "le", "gt", "ge", "contains", "not_contains", "missing",
})
# Binding selectors resolved by _recipient_body plus the declared non-binding
# ones ("own.bench", "turn"); a typo here would otherwise bind nothing, silently.
_RECIPIENT_SELECTORS = frozenset({
    "own.active", "own.bench", "own.bench.evolvable:first",
    "opponent.bench.highest_role", "turn",
})
#: The parameterised families, which name a card id and so cannot be enumerated. Their SHAPE is
#: still closed, so a misspelt suffix or a non-numeric id is rejected exactly as a misspelt fixed
#: selector is -- which is the whole point of the closed set.
_PARAMETERISED_SELECTORS = (
    re.compile(r"^own\.bench\.card:\d+$"),
    re.compile(r"^own\.body\.card:\d+:(?:first|readiest|weakest)$"),
)


def known_recipient_selector(selector) -> bool:
    selector = str(selector)
    return (selector in _RECIPIENT_SELECTORS
            or any(pattern.match(selector) for pattern in _PARAMETERISED_SELECTORS))


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
        if not known_recipient_selector(self.recipient_selector):
            raise ValueError(
                f"unknown strategy recipient selector: {self.recipient_selector!r}")
        if (not self.identifier or self.scope not in _SCOPES
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


__all__ = (
    "ActivationCondition", "DesiredFact", "StrategyHint", "StrategyOverride",
    "known_recipient_selector", "strategy_hint_from_dict",
)
