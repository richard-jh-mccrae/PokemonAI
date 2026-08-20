"""The Ledger's one trainable weight vector, denominated in PRIZES.

Every number the evaluator uses lives here and nowhere else: zone multipliers, worth tiers,
demand discounts, the game-level terms. General play is the defaults; a deck bends them through
`resolve(overrides)` and only where it genuinely dissents — the override layer is meant to stay
thin. Scalar overrides use the field name verbatim (`"zone_in_hand"`, `"prize_race"`); tier
entries use a dotted map key (`"role.primary_attacker"`, `"tag.draw"`, `"kind.item"`,
`"card.121"`). `identity` hashes the resolved vector so a decision or a replayed frame can name
exactly which weights judged it."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, fields, replace
from typing import Mapping


#: Worth of carrying each Role, in prizes (`pokemon_roles.POKEMON_ROLES` is the vocabulary).
ROLE_WORTH: dict[str, float] = {
    "primary_attacker": 0.50,
    "backup_attacker": 0.35,
    "sniper": 0.35,
    "draw_engine": 0.40,
    "supporter_tutor": 0.30,
    "accel_source": 0.35,
    "counter_mover": 0.25,
    "item_locker": 0.30,
    "retreat_assist": 0.20,
    "gust": 0.30,
}

#: Worth by behavioural tag for cards whose Role table has nothing to say (mostly Trainers).
TAG_WORTH: dict[str, float] = {
    "draw": 0.18,
    "search": 0.15,
    "tutor_pokemon": 0.15,
    "energy_accel": 0.20,
    "hand_disruption": 0.15,
    "gust": 0.25,
    "heal": 0.12,
    "switch": 0.12,
    "recovery": 0.12,
}

#: Fallback worth by card class when neither Roles nor tags price it.
KIND_WORTH: dict[str, float] = {
    "pokemon": 0.12,
    "item": 0.10,
    "supporter": 0.15,
    "tool": 0.08,
    "stadium": 0.10,
    "energy": 0.10,
}


@dataclass(frozen=True)
class LedgerWeights:
    # Zone multipliers on a card's worth: where it sits is most of what it is currently worth.
    zone_in_play: float = 1.0
    zone_in_hand: float = 0.65
    zone_in_deck: float = 0.15
    zone_in_discard: float = 0.10
    zone_under_body: float = 0.10
    zone_attached_usable: float = 1.0
    zone_attached_useless: float = 0.0
    zone_tool_attached: float = 0.90

    # Demand discounts on hand/deck worth.
    demand_dead: float = 0.40
    surplus_copy: float = 0.60

    # A damaged body keeps this fraction of its worth even at 1 HP; HP below zero counts as zero.
    damage_floor: float = 0.30

    # The scarce goods and liabilities of having bodies in play.
    bench_slot_value: float = 0.06
    prize_liability: float = 0.04

    # Game-level terms.
    prize_race: float = 1.00
    win_value: float = 100.0
    unknown_card_worth: float = 0.05
    opponent_unknown_card_worth: float = 0.12

    # Flat penalties for the active body's special conditions.
    status_asleep: float = 0.15
    status_paralyzed: float = 0.15
    status_confused: float = 0.08
    status_poisoned: float = 0.08
    status_burned: float = 0.08

    roles: tuple[tuple[str, float], ...] = tuple(sorted(ROLE_WORTH.items()))
    tags: tuple[tuple[str, float], ...] = tuple(sorted(TAG_WORTH.items()))
    kinds: tuple[tuple[str, float], ...] = tuple(sorted(KIND_WORTH.items()))
    #: Per-card worth pins, `{card_id: prizes}` — the deck saying THIS card is its plan.
    card_worth: tuple[tuple[int, float], ...] = ()

    role_worth: Mapping[str, float] = field(init=False, compare=False, repr=False)
    tag_worth: Mapping[str, float] = field(init=False, compare=False, repr=False)
    kind_worth: Mapping[str, float] = field(init=False, compare=False, repr=False)
    card_worth_map: Mapping[int, float] = field(init=False, compare=False, repr=False)

    def __post_init__(self):
        object.__setattr__(self, "role_worth", dict(self.roles))
        object.__setattr__(self, "tag_worth", dict(self.tags))
        object.__setattr__(self, "kind_worth", dict(self.kinds))
        object.__setattr__(self, "card_worth_map", dict(self.card_worth))

    @property
    def identity(self) -> str:
        payload = {name.name: getattr(self, name.name) for name in fields(self) if name.init}
        blob = json.dumps(payload, sort_keys=True, default=list).encode("utf-8")
        return hashlib.blake2b(blob, digest_size=8).hexdigest()

    def resolve(self, overrides: Mapping[str, float] | None) -> "LedgerWeights":
        """The general vector bent by one deck's flat dotted overrides; unknown keys raise so a
        typo cannot silently train nothing."""
        if not overrides:
            return self
        scalars: dict = {}
        roles, tags, kinds = dict(self.roles), dict(self.tags), dict(self.kinds)
        cards = dict(self.card_worth)
        scalar_names = {f.name for f in fields(self)
                        if f.init and f.name not in ("roles", "tags", "kinds", "card_worth")}
        for key, value in overrides.items():
            prefix, _, name = str(key).partition(".")
            if prefix == "role" and name:
                roles[name] = float(value)
            elif prefix == "tag" and name:
                tags[name] = float(value)
            elif prefix == "kind" and name:
                kinds[name] = float(value)
            elif prefix == "card" and name:
                cards[int(name)] = float(value)
            elif str(key) in scalar_names:
                scalars[str(key)] = float(value)
            else:
                raise KeyError(f"unknown ledger weight {key!r}")
        return replace(self, roles=tuple(sorted(roles.items())),
                       tags=tuple(sorted(tags.items())), kinds=tuple(sorted(kinds.items())),
                       card_worth=tuple(sorted(cards.items())), **scalars)


__all__ = ("KIND_WORTH", "LedgerWeights", "ROLE_WORTH", "TAG_WORTH")
