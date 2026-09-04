"""``cg.api`` twin backed by cgpy, no DLL (ADR-0059 M3). The dataclasses are VERBATIM copies of
``src/cg/api.py``'s — the agent-facing wire contract — and error strings match the native shim.

NOTE: no ``from __future__ import annotations`` here — ``to_dataclass`` walks real type objects on
the dataclass fields, exactly like the native shim.
"""
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .. import search as _search
from ..schema import (AreaType, CardType, EnergyType, LogType, OptionType,  # noqa: F401
                      SelectContext, SelectType, SpecialConditionType)
from .utils import to_dataclass

ENGINE_IMPLEMENTATION_IDENTITY = "cgpy-compat-api-v1"

_DEFS = Path(__file__).resolve().parents[1] / "defs"


#region Observation class

@dataclass
class Card:
    id: int
    serial: int
    playerIndex: int


@dataclass
class Pokemon:
    id: int
    serial: int
    hp: int
    maxHp: int
    appearThisTurn: bool
    energies: list[EnergyType]
    energyCards: list[Card]
    tools: list[Card]
    preEvolution: list[Card]


@dataclass
class PlayerState:
    active: list[Pokemon | None]
    bench: list[Pokemon]
    benchMax: int
    deckCount: int
    discard: list[Card]
    prize: list[Card | None]
    handCount: int
    hand: list[Card] | None
    poisoned: bool
    burned: bool
    asleep: bool
    paralyzed: bool
    confused: bool


@dataclass
class State:
    turn: int
    turnActionCount: int
    yourIndex: int
    firstPlayer: int
    supporterPlayed: bool
    stadiumPlayed: bool
    energyAttached: bool
    retreated: bool
    result: int
    stadium: list[Card]
    looking: list[Card | None] | None
    players: list[PlayerState]


@dataclass
class Option:
    type: OptionType
    number: int | None = None
    area: AreaType | None = None
    index: int | None = None
    playerIndex: int | None = None
    toolIndex: int | None = None
    energyIndex: int | None = None
    count: int | None = None
    inPlayArea: AreaType | None = None
    inPlayIndex: int | None = None
    attackId: int | None = None
    cardId: int | None = None
    serial: int | None = None
    specialConditionType: SpecialConditionType | None = None


@dataclass
class SelectData:
    type: SelectType
    context: SelectContext
    minCount: int
    maxCount: int
    remainDamageCounter: int
    remainEnergyCost: int
    option: list[Option]
    deck: list[Card] | None
    contextCard: Card | None
    effect: Card | None


@dataclass
class Log:
    type: LogType
    playerIndex: int | None = None
    hasBasicPokemon: bool | None = None
    cardId: int | None = None
    serial: int | None = None
    fromArea: AreaType | None = None
    toArea: AreaType | None = None
    cardIdActive: int | None = None
    serialActive: int | None = None
    cardIdBench: int | None = None
    serialBench: int | None = None
    cardIdBefore: int | None = None
    serialBefore: int | None = None
    cardIdAfter: int | None = None
    serialAfter: int | None = None
    cardIdTarget: int | None = None
    serialTarget: int | None = None
    attackId: int | None = None
    value: int | None = None
    putDamageCounter: bool | None = None
    isRecover: bool | None = None
    head: bool | None = None
    result: int | None = None
    reason: int | None = None


@dataclass
class Observation:
    select: SelectData | None
    logs: list[Log]
    current: State | None
    search_begin_input: str | None = None

#endregion Observation class


@dataclass
class SearchState:
    observation: Observation
    searchId: int


@dataclass
class ApiResult:
    state: SearchState | None
    error: int


@dataclass
class Skill:
    name: str
    text: str


@dataclass
class CardData:
    cardId: int
    name: str
    cardType: CardType
    retreatCost: int
    hp: int
    weakness: EnergyType | None
    resistance: EnergyType | None
    energyType: EnergyType
    basic: bool
    stage1: bool
    stage2: bool
    ex: bool
    megaEx: bool
    tera: bool
    aceSpec: bool
    evolvesFrom: str | None
    skills: list[Skill]
    attacks: list[int]


@dataclass
class Attack:
    attackId: int
    name: str
    text: str
    damage: int
    energies: list[EnergyType]


#region functions

def all_card_data() -> list[CardData]:
    """Return all cards (from the committed engine-table snapshot)."""
    cards = json.loads((_DEFS / "card_data.json").read_text(encoding="utf-8"))
    return [to_dataclass(v, CardData) for v in cards]


def all_attack() -> list[Attack]:
    """Return all attacks (from the committed engine-table snapshot)."""
    attacks = json.loads((_DEFS / "attack_data.json").read_text(encoding="utf-8"))
    return [to_dataclass(v, Attack) for v in attacks]


def to_observation_class(obs: dict) -> Observation:
    """dict to Observation class."""
    return to_dataclass(obs, Observation)


def _search_state(engine, search_id: int) -> SearchState:
    seat = engine.select_seat if engine.select_seat is not None else 0
    obs = engine.observation(viewer=seat, sbi_token=None)
    return SearchState(observation=to_dataclass(obs, Observation), searchId=search_id)


def search_begin(agent_observation: Observation,
                 your_deck: list[int],
                 your_prize: list[int],
                 opponent_deck: list[int],
                 opponent_prize: list[int],
                 opponent_hand: list[int],
                 opponent_active: list[int],
                 manual_coin: bool = False) -> SearchState:
    """Begin search (native contract; hidden zones from the predictions)."""
    sbi = agent_observation.search_begin_input
    if sbi is None:
        raise ValueError("Not agent observation.")
    obs = asdict(agent_observation)
    engine = _search.state_from_obs(obs, your_deck, your_prize, opponent_deck,
                                    opponent_prize, opponent_hand, opponent_active,
                                    manual_coin)
    return _search_state(engine, _search.session_begin(engine))


def search_step(search_id: int, select: list[int]) -> SearchState:
    """Proceed to the next selection (clone-per-step; the old id stays valid)."""
    sid, engine = _search.session_step(search_id, [int(i) for i in select])
    return _search_state(engine, sid)


def search_end() -> None:
    """Terminate the search; every held state is released."""
    _search.session_end()


def search_release(search_id: int) -> None:
    """Delete the state with the specified ID."""
    _search.session_release(search_id)

#endregion functions
