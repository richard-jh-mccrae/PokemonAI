"""Frozen typed nodes of one player-visible observation."""
from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass, field

DIGEST_BYTES = 16


def feed(update, value) -> None:
    """Feed one normalized value (None/bool/int/str/bytes or a tuple of them) into a hasher."""
    if value is None:
        update(b"N")
    elif value is True or value is False:
        update(b"B1" if value else b"B0")
    elif type(value) is int:
        update(b"I%d;" % value)
    elif type(value) is float:
        update(b"F")
        update(repr(value).encode("ascii"))
        update(b";")
    elif type(value) is str:
        data = value.encode("utf-8", "surrogatepass")
        update(b"S%d:" % len(data))
        update(data)
    elif type(value) is bytes:
        update(b"D%d:" % len(value))
        update(value)
    elif type(value) is tuple:
        update(b"(")
        for child in value:
            feed(update, child)
        update(b")")
    else:
        raise TypeError(f"unhashable board value {value!r}")


def digest(*parts) -> bytes:
    hasher = hashlib.blake2b(digest_size=DIGEST_BYTES)
    feed(hasher.update, parts)
    return hasher.digest()


def canon(value):
    """A JSON-ish subtree as nested hashable tuples; dict keys str-coerced and sorted."""
    if isinstance(value, dict):
        return tuple((str(key), canon(child)) for key, child in
                     sorted(value.items(), key=lambda item: str(item[0])))
    if isinstance(value, (list, tuple)):
        return tuple(canon(child) for child in value)
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise TypeError(f"unsupported observation value {type(value).__name__}")


@dataclass(frozen=True, slots=True)
class Card:
    """One visible card instance; equality is the printing, serial/owner are alignment only."""
    card_id: int
    serial: int | None = field(compare=False)
    owner: int | None = field(compare=False)

    def __post_init__(self):
        object.__setattr__(self, "card_id", int(self.card_id))
        object.__setattr__(self, "serial", None if self.serial is None else int(self.serial))
        object.__setattr__(self, "owner", None if self.owner is None else int(self.owner))


def card_node(entry) -> Card | None:
    if not entry:
        return None
    card_id = entry.get("id")
    if card_id is None:
        return None                    # an id-less row degrades like an unknown id: absent
    card_id = int(card_id)
    return Card(card_id, entry.get("serial"), entry.get("playerIndex"))


def card_tuple(entries) -> tuple[Card, ...]:
    return tuple(node for node in (card_node(entry) for entry in entries or ())
                 if node is not None)


@dataclass(frozen=True, slots=True)
class CardBag:
    """An order-free zone (hand, discard): render order is not identity."""
    cards: tuple[Card, ...] = field(compare=False)
    counts: tuple[tuple[int, int], ...]
    digest: bytes = field(compare=False)

    def count(self, card_id: int) -> int:
        return next((n for cid, n in self.counts if cid == int(card_id)), 0)

    def __len__(self) -> int:
        return len(self.cards)

    def __iter__(self):
        return iter(self.cards)


@dataclass(frozen=True, slots=True)
class VisibleHand:
    bag: CardBag

    @property
    def cards(self) -> tuple[Card, ...]:
        return self.bag.cards

    @property
    def counts(self) -> tuple[tuple[int, int], ...]:
        return self.bag.counts

    def count(self, card_id: int) -> int:
        return self.bag.count(card_id)

    def __len__(self) -> int:
        return len(self.bag)

    def __iter__(self):
        return iter(self.bag)


@dataclass(frozen=True, slots=True)
class HiddenHand:
    count: int

    def __iter__(self):
        return iter(())

    def __len__(self) -> int:
        return self.count


def card_bag(entries) -> CardBag:
    cards = card_tuple(entries)
    counts = tuple(sorted(Counter(card.card_id for card in cards).items()))
    return CardBag(cards, counts, digest(counts))


@dataclass(frozen=True, slots=True)
class Body:
    """One in-play Pokémon: the top card plus everything riding it."""
    card: Card
    hp: int
    max_hp: int
    appeared_this_turn: bool
    energies: tuple[int, ...]
    energy_cards: tuple[Card, ...]
    tools: tuple[Card, ...]
    pre_evolution: tuple[Card, ...]
    digest: bytes = field(compare=False)


def body_node(entry) -> Body | None:
    if not entry:
        return None
    card = card_node(entry)
    if card is None:
        return None
    hp, max_hp = int(entry.get("hp") or 0), int(entry.get("maxHp") or 0)
    appeared = bool(entry.get("appearThisTurn"))
    energies = tuple(int(unit) for unit in entry.get("energies") or () if unit is not None)
    energy_cards = card_tuple(entry.get("energyCards"))
    tools = card_tuple(entry.get("tools"))
    pre_evolution = card_tuple(entry.get("preEvolution"))
    body_digest = digest(
        card.card_id, hp, max_hp, appeared, energies,
        tuple(c.card_id for c in energy_cards), tuple(c.card_id for c in tools),
        tuple(c.card_id for c in pre_evolution))
    return Body(card, hp, max_hp, appeared, energies, energy_cards, tools, pre_evolution,
                body_digest)


@dataclass(frozen=True, slots=True)
class Side:
    """One player's half of the board, as the root seat may legally see it."""
    active: Body | None
    active_hidden: bool
    bench: tuple[Body, ...]
    bench_max: int
    deck_count: int
    hand: VisibleHand | HiddenHand
    hand_count: int
    discard: CardBag
    prize_count: int
    poisoned: bool
    burned: bool
    asleep: bool
    paralyzed: bool
    confused: bool

    @property
    def bodies(self) -> tuple[Body, ...]:
        return ((self.active,) if self.active is not None else ()) + self.bench


def active_node(raw_active) -> tuple[Body | None, bool]:
    """The render's three shapes: [] no active, [None] facedown even to its owner, [body]."""
    entries = raw_active if isinstance(raw_active, (list, tuple)) else ()
    if not entries:
        return None, False
    if entries[0] is None:
        return None, True
    return body_node(entries[0]), False


@dataclass(frozen=True, slots=True)
class Turn:
    """The turn-scoped facts and spent allowances shared by both sides."""
    number: int
    first_player: int | None
    supporter_played: bool
    stadium_played: bool
    energy_attached: bool
    retreated: bool
    result: int | None

    def scalars(self) -> tuple:
        return (self.number, self.first_player, self.supporter_played, self.stadium_played,
                self.energy_attached, self.retreated, self.result)


def turn_node(current) -> Turn:
    return Turn(int(current.get("turn") or 0), current.get("firstPlayer"),
                bool(current.get("supporterPlayed")), bool(current.get("stadiumPlayed")),
                bool(current.get("energyAttached")), bool(current.get("retreated")),
                None if current.get("result") is None else int(current["result"]))


@dataclass(frozen=True, slots=True)
class Looking:
    """Cards mid-effect under inspection; `cards` is None when the viewer may not see them."""
    count: int
    cards: tuple[Card, ...] | None


def looking_node(raw) -> Looking | None:
    if raw is None:
        return None
    entries = tuple(raw)
    if any(entry is None for entry in entries):
        return Looking(len(entries), None)
    return Looking(len(entries), card_tuple(entries))


#: Every field of an engine option; the deployed engine pads absent ones with None, the offline
#: twin omits them, and this record flattens both dialects to one shape.
OPTION_FIELDS = (
    "area", "attackId", "cardId", "count", "energyIndex", "inPlayArea", "inPlayIndex",
    "index", "number", "playerIndex", "serial", "specialConditionType", "toolIndex", "type",
)

@dataclass(frozen=True, slots=True)
class Option:
    area: object = None
    attackId: object = None
    cardId: object = None
    count: object = None
    energyIndex: object = None
    inPlayArea: object = None
    inPlayIndex: object = None
    index: object = None
    number: object = None
    playerIndex: object = None
    serial: object = None
    specialConditionType: object = None
    toolIndex: object = None
    type: object = None


def option_node(entry) -> Option:
    return Option(**{name: canon(entry.get(name)) for name in OPTION_FIELDS})


@dataclass(frozen=True, slots=True)
class SelectPrompt:
    """The pending engine question. Options and the deck listing are menu material, not position
    identity, so `identity()` excludes both."""
    type: int | None
    context: int | None
    min_count: int | None
    max_count: int | None
    remain_damage_counter: int | None
    remain_energy_cost: int | None
    options: tuple[Option, ...]
    deck: tuple[Card, ...] | None
    context_card: Card | None
    effect: Card | None

    def identity(self) -> tuple:
        return (self.type, self.context, self.min_count, self.max_count,
                self.remain_damage_counter, self.remain_energy_cost,
                None if self.context_card is None else self.context_card.card_id,
                None if self.effect is None else self.effect.card_id)


def select_node(raw) -> SelectPrompt | None:
    if raw is None:
        return None
    deck = raw.get("deck")
    return SelectPrompt(
        raw.get("type"), raw.get("context"), raw.get("minCount"), raw.get("maxCount"),
        raw.get("remainDamageCounter"), raw.get("remainEnergyCost"),
        tuple(option_node(entry) for entry in raw.get("option") or ()
              if isinstance(entry, dict)),
        None if deck is None else card_tuple(deck),
        card_node(raw.get("contextCard")), card_node(raw.get("effect")))


__all__ = ("Body", "Card", "CardBag", "HiddenHand", "Looking", "Option", "OPTION_FIELDS",
           "SelectPrompt", "Side", "Turn", "VisibleHand", "active_node", "body_node", "canon",
           "card_bag", "card_node", "card_tuple",
           "digest", "feed", "looking_node", "option_node", "select_node", "turn_node")
