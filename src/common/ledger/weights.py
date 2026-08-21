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
import math
from dataclasses import dataclass, field, fields, replace
from typing import Mapping


#: Worth of carrying each Role, in prizes. Vocabulary = `POKEMON_ROLES` plus the Brief target
#: roles (disruption_target / support_pokemon / engine), carried only by scouted opponents.
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
    "disruption_target": 0.35,
    "support_pokemon": 0.25,
    "engine": 0.40,
}

#: Worth by behavioural tag for cards whose Role table has nothing to say (mostly Trainers).
#: A 0.0 entry is a live lever the rounds have not raised: the kind fallback still prices it.
TAG_WORTH: dict[str, float] = {
    "draw": 0.18,
    "search": 0.15,
    "tutor_pokemon": 0.15,
    "energy_accel": 0.20,
    "hand_disruption": 0.15,
    "gust": 0.25,
    "heal": 0.12,
    "switch": 0.12,
    "bench_fill": 0.0,
    "clutch_heal": 0.0,
    "cost_discard": 0.0,
    "dig": 0.0,
    "dig:2": 0.0,
    "dig:3": 0.0,
    "discard_energy_recur": 0.0,
    "discard_eot": 0.0,
    "energy_denial": 0.0,
    "item_lock": 0.0,
    "opener": 0.0,
    "recycle": 0.0,
    "recycle_line": 0.0,
    "rush_evolve": 0.0,
    "shuffle_hand": 0.0,
    "spread": 0.0,
    "stall": 0.0,
    "supporter_tutor": 0.0,
    "tutor_energy": 0.0,
    "tutor_mega": 0.0,
    "tutor_trainer": 0.0,
}

#: Fallback worth by card class when neither Roles nor tags price it.
KIND_WORTH: dict[str, float] = {
    "pokemon": 0.12,
    "item": 0.10,
    "supporter": 0.15,
    "tool": 0.08,
    "stadium": 0.10,
    "energy": 0.10,
    # 0.05 adopted 2026-08-20: below basic, so Ignition-vs-{W} exact ties break on demand.
    # mega_starmie dissents (keeps 0.10) — docs/tuning/runs/ledger_20260820_round1.md.
    "special_energy": 0.05,
}


@dataclass(frozen=True)
class LedgerWeights:
    # Zone multipliers on a card's worth: where it sits is most of what it is currently worth.
    zone_in_play: float = 1.0
    zone_in_hand: float = 0.65
    zone_in_deck: float = 0.15
    zone_in_discard: float = 0.10
    #: 0.65 adopted 2026-08-20 (ADR-0151): the card invested UNDER an evolution keeps most of
    #: its worth — line continuity, the fix for evolves pricing negative at role parity.
    zone_under_body: float = 0.65
    zone_attached_usable: float = 1.0
    zone_attached_useless: float = 0.0
    zone_tool_attached: float = 0.90

    # Demand discounts on hand/deck worth.
    #: 0.25 adopted 2026-08-20; mega_starmie dissents — docs/tuning/runs/ledger_20260820_round1.md.
    demand_dead: float = 0.25
    demand_colorless_only: float = 0.70
    #: An evolution whose base is in HAND, not yet in play: the pair is worth more together
    #: than either alone — the nonlinearity the sampled-hand chance model feeds on.
    demand_setup: float = 0.70
    #: The reach gate on a future evolution's colorless slots while that evolution sits in the
    #: DECK (or the side's knowledge is absent). 0.80 encodes the owner's ruling: pre-charge
    #: Staryu for Nebula Beam with Mega Starmie merely in the deck — the damage blend then
    #: refuses the same attach on a doomed carrier by itself.
    reach_in_deck: float = 0.80
    surplus_copy: float = 0.60

    # A damaged body keeps this fraction of its worth even at 1 HP; HP below zero counts as zero.
    damage_floor: float = 0.30
    #: Prizes per 100 printed max HP, on every body, inside the damage multiplier (ADR-0151):
    #: SIZE becomes worth, so an evolution out-values its basic and chip damage prices real.
    hp_value: float = 0.0

    # The scarce goods and liabilities of having bodies in play.
    bench_slot_value: float = 0.06
    prize_liability: float = 0.04

    #: Concentration (ADR-0150): extra credit for a body's progress toward its LARGEST attack,
    #: squared — so finishing a started attacker outprices starting a fresh one. Armed at the
    #: owner-ordered seed; the flips it buys are accepted, not gate-clean (2026-08-21 ruling).
    concentration: float = 0.1

    #: Fraction of its worth THEIR active loses when OUR active's payable attack can KO it
    #: outright (weakness applied) — the 1-ply doomed read: gust up what you can kill.
    doomed_active_discount: float = 0.0

    # The Active Spot: worth extra when its occupant can actually pay an attack.
    active_premium: float = 0.08
    #: 0.15 adopted 2026-08-20 (docs/tuning/runs/ledger_20260820_145141.md): an unready
    #: Active keeps less premium, so readying or replacing it prices higher.
    active_unready_fraction: float = 0.15

    # Game-level terms.
    prize_race: float = 1.00
    win_value: float = 100.0
    unknown_card_worth: float = 0.05
    opponent_unknown_card_worth: float = 0.12
    #: The swing a turn-continuing option must clear to act; 0.0 = the historical any-positive
    #: bar. The float-noise floor still applies underneath, so this never sharpens ties.
    act_threshold: float = 0.0

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
            # Tier names are closed vocabularies: a typo must raise, never train nothing.
            if prefix == "role" and name:
                if name not in roles and name not in _role_vocabulary():
                    raise KeyError(f"unknown ledger weight {key!r}")
                roles[name] = _finite(key, value)
            elif prefix == "tag" and name:
                if name not in tags and name not in _tag_vocabulary():
                    raise KeyError(f"unknown ledger weight {key!r}")
                tags[name] = _finite(key, value)
            elif prefix == "kind" and name:
                if name not in kinds:
                    raise KeyError(f"unknown ledger weight {key!r}")
                kinds[name] = _finite(key, value)
            elif prefix == "card" and name:
                cards[int(name)] = _finite(key, value)
            elif str(key) in scalar_names:
                scalars[str(key)] = _finite(key, value)
            else:
                raise KeyError(f"unknown ledger weight {key!r}")
        return replace(self, roles=tuple(sorted(roles.items())),
                       tags=tuple(sorted(tags.items())), kinds=tuple(sorted(kinds.items())),
                       card_worth=tuple(sorted(cards.items())), **scalars)


def _finite(key, value) -> float:
    """A non-finite weight poisons every swing into an unrankable NaN/inf: refuse at resolve
    time, where the typo is one line away, not mid-match where it reads as a brain crash."""
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"ledger weight {key!r} must be finite, got {value!r}")
    return number


def _role_vocabulary() -> frozenset:
    from common.cards.pokemon_roles import POKEMON_ROLES
    return frozenset(POKEMON_ROLES)


def _tag_vocabulary() -> frozenset:
    from common.cards import card_store
    return frozenset(tag for card in card_store().values()
                     for tag in (getattr(card, "tags", ()) or ()))


__all__ = ("KIND_WORTH", "LedgerWeights", "ROLE_WORTH", "TAG_WORTH")
