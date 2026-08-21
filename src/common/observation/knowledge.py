from __future__ import annotations

from dataclasses import dataclass, replace


PROBABILITY_SCALE = 1_000_000


@dataclass(frozen=True, slots=True)
class UnknownOwnPrizes:
    pass


@dataclass(frozen=True, slots=True)
class KnownOwnPrizes:
    cards: tuple[tuple[int, int], ...]

    def __post_init__(self):
        cards = tuple(sorted((int(card_id), int(count)) for card_id, count in self.cards))
        if any(count < 0 for _card_id, count in cards):
            raise ValueError("negative known prize count")
        object.__setattr__(self, "cards", cards)


@dataclass(frozen=True, slots=True)
class UnknownDeckTop:
    pass


@dataclass(frozen=True, slots=True)
class KnownDeckTop:
    cards: tuple[tuple[int, int], ...]

    def __post_init__(self):
        object.__setattr__(self, "cards", tuple(
            tuple(int(value) for value in row) for row in self.cards))


@dataclass(frozen=True, slots=True)
class UnknownAttackLocks:
    pass


@dataclass(frozen=True, slots=True)
class KnownAttackLocks:
    locks: tuple

    def __post_init__(self):
        object.__setattr__(self, "locks", tuple(_freeze(self.locks)))


@dataclass(frozen=True, slots=True)
class OpponentBelief:
    evidence: tuple[tuple[str, object], ...] = ()
    probabilities: tuple[tuple[int, int], ...] = ()

    def __post_init__(self):
        evidence = tuple(sorted((str(key), _freeze(value)) for key, value in self.evidence))
        probabilities = tuple(sorted((int(card_id), int(value))
                                     for card_id, value in self.probabilities))
        if len({card_id for card_id, _value in probabilities}) != len(probabilities):
            raise ValueError("duplicate opponent belief card")
        if any(value < 0 or value > PROBABILITY_SCALE for _card_id, value in probabilities):
            raise ValueError("belief probability outside fixed-point range")
        object.__setattr__(self, "evidence", evidence)
        object.__setattr__(self, "probabilities", probabilities)


@dataclass(frozen=True, slots=True)
class LegalKnowledge:
    own_prizes: UnknownOwnPrizes | KnownOwnPrizes = UnknownOwnPrizes()
    known_top: UnknownDeckTop | KnownDeckTop = UnknownDeckTop()
    attack_locks: UnknownAttackLocks | KnownAttackLocks = UnknownAttackLocks()
    opponent: OpponentBelief = OpponentBelief()

    def __post_init__(self):
        if not isinstance(self.own_prizes, (UnknownOwnPrizes, KnownOwnPrizes)):
            raise TypeError("own_prizes must be a knowledge variant")
        if not isinstance(self.known_top, (UnknownDeckTop, KnownDeckTop)):
            raise TypeError("known_top must be a knowledge variant")
        if not isinstance(self.attack_locks, (UnknownAttackLocks, KnownAttackLocks)):
            raise TypeError("attack_locks must be a knowledge variant")
        if not isinstance(self.opponent, OpponentBelief):
            raise TypeError("opponent must be an OpponentBelief")


def reduce_knowledge(knowledge: LegalKnowledge, *, own_prizes=None, known_top=None,
                     attack_locks=None, opponent=None) -> LegalKnowledge:
    return replace(
        knowledge,
        own_prizes=knowledge.own_prizes if own_prizes is None else KnownOwnPrizes(tuple(own_prizes)),
        known_top=knowledge.known_top if known_top is None else KnownDeckTop(tuple(known_top)),
        attack_locks=(knowledge.attack_locks if attack_locks is None
                      else KnownAttackLocks(tuple(attack_locks))),
        opponent=knowledge.opponent if opponent is None else opponent,
    )


def _freeze(value):
    if isinstance(value, dict):
        return tuple(sorted((str(key), _freeze(child)) for key, child in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(child) for child in value)
    if value is None or isinstance(value, (bool, int, str)):
        return value
    raise TypeError(f"unsupported belief evidence {type(value).__name__}")


@dataclass(frozen=True, slots=True)
class TransitionTrace:
    schema_version: int
    start_position_key: str
    actions: tuple
    terminal_position_key: str


__all__ = ("KnownAttackLocks", "KnownDeckTop", "KnownOwnPrizes", "LegalKnowledge",
           "OpponentBelief", "PROBABILITY_SCALE", "TransitionTrace", "UnknownAttackLocks",
           "UnknownDeckTop", "UnknownOwnPrizes", "reduce_knowledge")
