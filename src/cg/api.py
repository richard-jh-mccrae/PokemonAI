from dataclasses import dataclass
from enum import IntEnum
import json
import ctypes

from .sim import lib
from .utils import to_dataclass, json_to_dataclass

#region Enums

class AreaType(IntEnum):
    DECK = 1,
    HAND = 2,
    DISCARD = 3, # discard pile
    ACTIVE = 4, # active spot
    BENCH = 5,
    PRIZE = 6,
    STADIUM = 7,
    ENERGY = 8,
    TOOL = 9,
    PRE_EVOLUTION = 10, # pre-evolved form of the in-play Pokemon
    PLAYER = 11,
    LOOKING = 12, # card currently being looked at

class EnergyType(IntEnum):
    COLORLESS = 0,
    GRASS = 1,
    FIRE = 2,
    WATER = 3,
    LIGHTNING = 4,
    PSYCHIC = 5,
    FIGHTING = 6,
    DARKNESS = 7,
    METAL = 8,
    DRAGON = 9,
    RAINBOW = 10, # all types
    TEAM_ROCKET = 11, # PSYCHIC + DARKNESS

class CardType(IntEnum):
    POKEMON = 0,
    ITEM = 1,
    TOOL = 2, # Pokemon Tool
    SUPPORTER = 3,
    STADIUM = 4,
    BASIC_ENERGY = 5,
    SPECIAL_ENERGY = 6,

class SpecialConditionType(IntEnum):
    POISON = 0,
    BURN = 1,
    SLEEP = 2,
    PARALYZE = 3,
    CONFUSE = 4,

class SelectType(IntEnum):
    MAIN = 0, # OptionType: PLAY, ATTACH, EVOLVE, ABILITY, DISCARD, RETREAT, ATTACK, END
    CARD = 1, # OptionType: CARD
    ATTACHED_CARD = 2, # OptionType: TOOL_CARD, ENERGY_CARD
    CARD_OR_ATTACHED_CARD = 3, # OptionType: CARD, TOOL_CARD, ENERGY_CARD
    ENERGY = 4, # OptionType: ENERGY
    SKILL = 5, # OptionType: SKILL
    ATTACK = 6, # OptionType: ATTACK
    EVOLVE = 7, # OptionType: EVOLVE
    COUNT = 8, # OptionType: NUMBER
    YES_NO = 9, # OptionType: YES, NO
    SPECIAL_CONDITION = 10, # OptionType: SPECIAL_CONDITION
    
class SelectContext(IntEnum):
    MAIN = 0, # Main. main selection.
    SETUP_ACTIVE_POKEMON = 1, # Card. pick Pokemon for Active Spot during Set Up.
    SETUP_BENCH_POKEMON = 2, # Card. pick Pokemon for Bench during Set Up.
    SWITCH = 3, # Card. pick Pokemon to swap into Active Spot.
    TO_ACTIVE = 4, # Card. pick Pokemon to put in Active Spot.
    TO_BENCH = 5, # Card. pick Pokemon to put on Bench.
    TO_FIELD = 6, # Card. pick Pokemon to put into play.
    TO_HAND = 7, # Card. pick card to add to hand.
    DISCARD = 8, # Card. pick card to discard.
    TO_DECK = 9, # Card. pick card to return to deck.
    TO_DECK_BOTTOM = 10, # Card. pick card to return to bottom of deck.
    TO_PRIZE = 11, # Card. pick card to add to prize.
    NOT_MOVE = 12, # Card. pick card that stays put.
    DAMAGE_COUNTER = 13, # Card. pick Pokemon to place damage counters on.
    DAMAGE_COUNTER_ANY = 14, # Card. pick Pokemon to place damage counters on (free placement effect).
    DAMAGE = 15, # Card. pick Pokemon to deal damage to.
    REMOVE_DAMAGE_COUNTER = 16, # Card. pick Pokemon to remove damage counters from.
    HEAL = 17, # Card. pick Pokemon to heal.
    EVOLVES_FROM = 18, # Card. pick the pre-evolution Pokemon.
    EVOLVES_TO = 19, # Card. pick the evolution target.
    DEVOLVE = 20, # Card. pick Pokemon to devolve.
    ATTACH_FROM = 21, # Card. pick Pokemon the card attaches to.
    ATTACH_TO = 22, # Card. pick card to attach to the Pokemon.
    DETACH_FROM = 23, # Card. pick Pokemon to remove the card from.
    LOOK = 24, # Card. pick card to look at.
    EFFECT_TARGET = 25, # Card. pick card the effect applies to.
    DISCARD_ENERGY_CARD = 26, # AttachedCard. pick Energy card to discard.
    DISCARD_TOOL_CARD = 27, # AttachedCard. pick Pokemon Tool to trash.
    SWITCH_ENERGY_CARD = 28, # AttachedCard. pick energy card to replace.
    DISCARD_CARD_OR_ATTACHED_CARD = 29, # CardOrAttachedCard. pick card to discard.
    DISCARD_ENERGY = 30, # Energy. pick energy to discard.
    TO_HAND_ENERGY = 31, # Energy. pick energy to return to hand.
    TO_DECK_ENERGY = 32, # Energy. pick energy to return to deck.
    SWITCH_ENERGY = 33, # Energy. pick energy to switch.
    SKILL_ORDER = 34, # Skill. pick order effects activate in.
    ATTACK = 35, # Attack. pick the Attack to use.
    DISABLE_ATTACK = 36, # Attack. pick the Attack to disable.
    EVOLVE = 37, # Evolve. pick evolution source Pokemon + target Pokemon.
    DRAW_COUNT = 38, # Count. pick how many cards to draw.
    DAMAGE_COUNTER_COUNT = 39, # Count. pick how many damage counters to place.
    REMOVE_DAMAGE_COUNTER_COUNT = 40, # Count. pick how many damage counters to remove.
    IS_FIRST = 41, # YesNo. go first?
    MULLIGAN = 42, # YesNo. redraw?
    ACTIVATE = 43, # YesNo. activate the effect?
    FIRST_EFFECT = 44, # YesNo. pick the first effect?
    MORE_DEVOLVE = 45, # YesNo. devolve further?
    COIN_HEAD = 46, # YesNo. choose heads?
    AFFECT_SPECIAL_CONDITION = 47, # SpecialCondition. pick special condition to affect.
    RECOVER_SPECIAL_CONDITION = 48, # SpecialCondition. pick special condition to recover.
    # more elements may get appended to this Enum during the competition

class OptionType(IntEnum):
    # number (int): count.
    NUMBER = 0, # pick a number.

    YES = 1, # pick Yes.

    NO = 2, # pick No.

    # area (AreaType): where the card is.
    # index (int): index within the area.
    # playerIndex (int): owning player.
    CARD = 3, # pick a card.

    # area (AreaType): area of the attached Pokemon.
    # index (int): its index within the area.
    # playerIndex (int): owning player of the Pokemon.
    # toolIndex (int): index within the tool.
    TOOL_CARD = 4, # pick a Pokemon Tool Card.

    # area (AreaType): area of the attached Pokemon.
    # index (int): its index within the area.
    # playerIndex (int): owning player of the Pokemon.
    # energyIndex (int): index within the energy card.
    ENERGY_CARD = 5, # pick an Energy Card.

    # area (AreaType): area of the attached Pokemon.
    # index (int): its index within the area.
    # playerIndex (int): owning player of the Pokemon.
    # energyIndex (int): index within the energy card.
    # count (int): how many energy units it's worth.
    ENERGY = 6, # pick energy.

    # index (int): index within the hand.
    PLAY = 7, # play a card from hand.

    # area (AreaType): area of the card to attach.
    # index (int): its index within the area.
    # inPlayArea (AreaType): area of the target Pokemon on the field.
    # inPlayIndex (int): its index within the area.
    ATTACH = 8, # attach a card to a Pokemon.

    # area (AreaType): area of the evolved card.
    # index (int): its index within the area.
    # inPlayArea (AreaType): area of the target Pokemon on the field.
    # inPlayIndex (int): its index within the area.
    EVOLVE = 9, # pick an evolution.

    # area (AreaType): where the card is.
    # index (int): index within the area.
    ABILITY = 10, # use an Ability.

    # area (AreaType): where the card is.
    # index (int): index within the area.
    DISCARD = 11, # discard a card in play.

    RETREAT = 12, # retreat Active Pokemon.

    # attackId (int): Attack ID.
    ATTACK = 13, # pick an Attack.

    END = 14, # end turn.

    # cardId (int): Card ID. 0 means it's handling a Special Condition instead.
    # serial (int): card serial.
    SKILL = 15, # pick order of card skills.

    # specialConditionType (SpecialConditionType): which condition.
    SPECIAL_CONDITION = 16, # pick the Special Condition.

class LogType(IntEnum):
    # playerIndex (int)
    SHUFFLE = 0, # shuffle deck.

    # playerIndex (int)
    # hasBasicPokemon (bool): false -> no Basic Pokemon exist.
    HAS_BASIC_POKEMON = 1,

    # playerIndex (int)
    TURN_START = 2, # start turn.

    # playerIndex (int)
    TURN_END = 3, # end turn.

    # playerIndex (int)
    # cardId (int): drawn card ID
    # serial (int): drawn card serial
    DRAW = 4, # drew a card from deck.

    # playerIndex (int)
    DRAW_REVERSE = 5, # opponent drew a card from their deck.

    # playerIndex (int)
    # cardId (int): moved card ID
    # serial (int): moved card serial
    # fromArea (AreaType): area before move.
    # toArea (AreaType): area after move.
    MOVE_CARD = 6, # a card moved.

    # playerIndex (int)
    # fromArea (AreaType): area before move.
    # toArea (AreaType): area after move.
    MOVE_CARD_REVERSE = 7, # a card moved face-down.

    # playerIndex (int)
    # cardIdActive (int): ID of Pokemon moving to Bench
    # serialActive (int): serial of Pokemon moving to Bench
    # cardIdBench (int): ID of Pokemon moving to Active
    # serialBench (int): serial of Pokemon moving to Active
    SWITCH = 8, # Pokemon were switched.

    # playerIndex (int)
    # cardIdBefore (int): Pokemon before change, ID
    # serialBefore (int): Pokemon before change, serial
    # cardIdAfter (int): Pokemon after change, ID
    # serialAfter (int): Pokemon after change, serial
    CHANGE = 9, # Pokemon changed.

    # playerIndex (int)
    # cardId (int): played card ID
    # serial (int): played card serial
    PLAY = 10, # played a card from hand.

    # playerIndex (int)
    # cardId (int): attached card ID
    # serial (int): attached card serial
    # cardIdTarget (int): Pokemon card ID
    # serialTarget (int): Pokemon card serial
    ATTACH = 11, # attached a card to a Pokemon.

    # playerIndex (int)
    # cardId (int): evolved card ID
    # serial (int): evolved card serial
    # cardIdTarget (int): Pokemon card ID
    # serialTarget (int): Pokemon card serial
    EVOLVE = 12, # evolved a Pokemon.

    # playerIndex (int)
    # cardId (int): devolved card ID
    # serial (int): devolved card serial
    # cardIdTarget (int): Pokemon card ID
    # serialTarget (int): Pokemon card serial
    DEVOLVE = 13, # devolved a Pokemon.

    # playerIndex (int)
    # cardId (int): attached card ID
    # serial (int): attached card serial
    # cardIdBefore (int): ID of Pokemon that held the cards before
    # serialBefore (int): serial of Pokemon that held the cards before
    # cardIdAfter (int): ID of Pokemon newly holding the cards
    # serialAfter (int): serial of Pokemon newly holding the cards
    MOVE_ATTACHED = 14, # moved the attached card.

    # playerIndex (int)
    # cardId (int): ID of attacking Pokemon
    # serial (int): serial of attacking Pokemon
    # attackId (int): Attack ID
    ATTACK = 15, # Pokemon attacked.

    # playerIndex (int)
    # cardId (int): HP-changed card ID
    # serial (int): HP-changed card serial
    # value (int): amount of change.
    # putDamageCounter (bool): true if change came from placing a damage counter.
    HP_CHANGE = 16, # a Pokemon's HP changed.

    # playerIndex (int)
    # isRecover (bool): true if the special condition got cured.
    # cardId (int): ID
    # serial (int): serial
    POISONED = 17, # poisoned.

    # playerIndex (int)
    # isRecover (bool): true if the special condition got cured.
    # cardId (int): ID
    # serial (int): serial
    BURNED = 18, # burned.

    # playerIndex (int)
    # isRecover (bool): true if the special condition got cured.
    # cardId (int): ID
    # serial (int): serial
    ASLEEP = 19, # fell asleep.

    # playerIndex (int)
    # isRecover (bool): true if the special condition got cured.
    # cardId (int): ID
    # serial (int): serial
    PARALYZED = 20, # paralyzed.

    # playerIndex (int)
    # isRecover (bool): true if the special condition got cured.
    # cardId (int): ID
    # serial (int): serial
    CONFUSED = 21, # confused.

    # playerIndex (int)
    # head (bool): true if coin landed heads.
    COIN = 22, # coin flip result.

    # result (int): 0 -> player 0 wins, 1 -> player 1 wins, 2 -> draw.
    # reason (int): 1 = 0 prize cards. 2 = started turn with 0 deck cards. 3 = no Pokemon in Active Spot. 4 = card effect.
    RESULT = 23, # match result.

    # more elements may get appended to this Enum during the competition

#endregion Enums


# classes may get new attributes appended during the competition

#region Observation class

@dataclass
class Card:
    id: int  # CardData ID.
    serial: int  # serial number: unique per card in the match.
    playerIndex: int  # which player owns the card.

@dataclass
class Pokemon:
    id: int  # CardData ID.
    serial: int  # serial number: unique per card in the match.
    hp: int  # current HP.
    maxHp: int  # current max HP.
    appearThisTurn: bool  # true if played this turn.
    energies: list[EnergyType]  # energies array
    energyCards: list[Card]  # attached energy card array
    tools: list[Card]  # attached Pokemon Tool array
    preEvolution: list[Card]  # pre-evolution card array

@dataclass
class PlayerState:
    active: list[Pokemon | None]  # active Pokemon (None if facedown). size 0 or 1.
    bench: list[Pokemon]  # bench Pokemon.
    benchMax: int  # max bench count.
    deckCount: int  # cards remaining in deck.
    discard: list[Card]  # discard pile card array.
    prize: list[Card | None]  # prize cards (None if facedown). first elem = bottom of prize, last = top.
    handCount: int  # number of cards in hand.
    hand: list[Card] | None  # hand card array. None for the opponent.
    poisoned: bool # active Pokemon is Poisoned.
    burned: bool # active Pokemon is Burned.
    asleep: bool # active Pokemon is Asleep.
    paralyzed: bool # active Pokemon is Paralyzed.
    confused: bool # active Pokemon is Confused.

@dataclass
class State:
    turn: int  # turn count: 1 = starting player's 1st turn, 2 = 2nd player's 1st turn, 3 = starting player's 2nd turn... 0 = before starting player's first turn.
    turnActionCount: int  # actions taken this turn.
    yourIndex: int  # your player index (who's making the selection). 0 or 1.
    firstPlayer: int  # starting player index. -1 if not yet determined.
    supporterPlayed: bool  # true if a supporter already used this turn.
    stadiumPlayed: bool  # true if a stadium already used this turn.
    energyAttached: bool  # true if manual energy attach already used this turn.
    retreated: bool  # true if retreated this turn.
    result: int # winning player index. -1 if battle not finished.
    stadium: list[Card]  # stadium card. size 0 or 1.
    looking: list[Card | None] | None  # cards being looked at (None entry = facedown). None if not looking at any.
    players: list[PlayerState]  # per-player states, always 2 elements.

@dataclass
class Option:
    type: OptionType  # tells you which option this is.
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
    type: SelectType  # selection type.
    context: SelectContext  # what's being selected.
    minCount: int  # min selections, can be 0.
    maxCount: int  # max selections, never exceeds len(option).
    remainDamageCounter: int  # damage counters still placeable.
    remainEnergyCost: int  # type Energy only: remaining required energy count.
    option: list[Option]  # array of options.
    deck: list[Card] | None  # card array; None unless selecting from the deck.
    contextCard: Card | None  # card the selection concerns; sent for context "Activate", else null.
    effect: Card | None  # card activating the effect currently being processed.

@dataclass
class Log:
    type: LogType  # tells you which log this is.
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
    select: SelectData | None  # selection info. None during initial deck selection.
    logs: list[Log]  # events since the last selection.
    current: State | None  # current state. None during initial deck selection.
    search_begin_input: str | None = None # input to the search_begin function.

#endregion Observation class

@dataclass
class SearchState:
    observation: Observation  # new observation. search_begin_input is None.
    searchId: int  # search state ID.
    
@dataclass
class ApiResult:
    state: SearchState | None # search state.
    error: int # error code if not 0.

# abilities and effects present at time of card play.
@dataclass
class Skill:
    name: str  # skill name.
    text: str  # explanation.

@dataclass
class CardData:
    cardId: int  # Card ID.
    name: str  # card name.
    cardType: CardType  # card type
    retreatCost: int  # energy cost to retreat.
    hp: int  # Pokemon HP.
    weakness: EnergyType | None  # Pokemon weakness.
    resistance: EnergyType | None  # Pokemon resistance.
    energyType: EnergyType  # Pokemon or Basic Energy type.
    basic: bool # true if Basic Pokemon.
    stage1: bool # true if Stage1 Pokemon.
    stage2: bool # true if Stage2 Pokemon.
    ex: bool # true if Pokemon ex (incl. Mega Evolution Pokemon ex). KO'd ex gives opponent 2 prizes (Mega ex excluded from this count).
    megaEx: bool # true if Mega Evolution Pokemon ex. KO'd Mega ex gives opponent 3 prizes.
    tera: bool  # true if Tera Pokemon. Tera Pokemon on the Bench take no attack damage.
    aceSpec: bool  # true if ACE SPEC. deck can hold at most 1 ACE SPEC card.
    evolvesFrom: str | None  # pre-evolution name if evolved, else None.
    skills: list[Skill]  # skills this card has.
    attacks: list[int]  # IDs of usable attacks.

@dataclass
class Attack:
    attackId: int  # Attack ID.
    name: str  # attack name.
    text: str  # explanation.
    damage: int  # attack damage
    energies: list[EnergyType]  # energy required to use.
    

#region functions

def all_card_data() -> list[CardData]:
    """Return all cards."""
    bs = lib.AllCard()
    js = bs.decode()
    cards = json.loads(js)
    return [to_dataclass(v, CardData) for v in cards]

def all_attack() -> list[Attack]:
    """Return all attacks."""
    bs = lib.AllAttack()
    js = bs.decode()
    cards = json.loads(js)
    return [to_dataclass(v, Attack) for v in cards]

def to_observation_class(obs: dict) -> Observation:
    """dict to Observation class.

    Returns:
        Observation: Observation dataclass instance.
    """
    return to_dataclass(obs, Observation)

def search_begin(agent_observation: Observation,
                 your_deck: list[int],
                 your_prize: list[int],
                 opponent_deck: list[int],
                 opponent_prize: list[int],
                 opponent_hand: list[int],
                 opponent_active: list[int],
                 manual_coin: bool = False
    ) -> SearchState:
    """Begin search.

    Args:
        agent_observation: You must input the observation argument passed to your agent function exactly as is.
        your_deck: Predicted Card ID your Deck. It must have the same number of cards as your deck. If Observation.select.deck != None, ignored this.
        your_prize: Predicted Card ID your Prize cards. It must have the same number of cards as your prize.
        opponent_deck: Predicted Card ID opponent's deck. It must have the same number of cards as opponent's deck. At setup, at least one Basic Pokémon card is required.
        opponent_prize: Predicted Card ID opponent's prize cards. It must have the same number of cards as opponent's prize.
        opponent_hand: Predicted Card ID opponent's hand. It must have the same number of cards as opponent's hand.
        opponent_active: Predicted Card ID opponent's Active Pokémon. Only if there is a face-down Pokémon in your opponent’s Active Spot. This ID must be a Pokémon card ID.
        manual_coin: If True, the coin's heads or tails can be chosen.

    Returns:
        SearchState: Root search state.
    """
    global agent_ptr
    
    if "agent_ptr" not in globals():
        agent_ptr = lib.AgentStart()
    
    sbi = agent_observation.search_begin_input
    if sbi == None:
        raise ValueError("Not agent observation.")

    state = agent_observation.current
    your_index = state.yourIndex

    if agent_observation.select.deck != None:
        your_deck = []
    elif len(your_deck) < state.players[your_index].deckCount:
        raise ValueError("your_deck does not match the number of cards in your deck.")
    
    if len(your_prize) < len(state.players[your_index].prize):
        raise ValueError("your_prize does not match the number of cards in your prize.")
    elif len(opponent_deck) < state.players[1 - your_index].deckCount:
        raise ValueError("opponent_deck does not match the number of cards in opponent's deck.")
    elif len(opponent_prize) < len(state.players[1 - your_index].prize):
        raise ValueError("opponent_prize does not match the number of cards in opponent's prize.")
    elif len(opponent_hand) < state.players[1 - your_index].handCount:
        raise ValueError("opponent_hand does not match the number of cards in opponent's hand.")
    
    active = state.players[1 - your_index].active
    if len(active) > 0 and active[0] == None:
        if len(opponent_active) == 0:
            raise ValueError("You need to predict the opponent's Active Pokémon.")
    else:
        opponent_active = []
    
    bs = lib.SearchBegin(agent_ptr,
                         sbi.encode("ascii"),
                         len(sbi),
                         (ctypes.c_int*len(your_deck))(*your_deck),
                         (ctypes.c_int*len(your_prize))(*your_prize),
                         (ctypes.c_int*len(opponent_deck))(*opponent_deck),
                         (ctypes.c_int*len(opponent_prize))(*opponent_prize),
                         (ctypes.c_int*len(opponent_hand))(*opponent_hand),
                         (ctypes.c_int*len(opponent_active))(*opponent_active),
                         int(manual_coin))
    result = json_to_dataclass(bs, ApiResult)
    if result.error != 0:
        if result.error == 1:
            raise ValueError("Invalid Card ID.")
        elif result.error == 2:
            raise ValueError("Active card must be the ID of a Pokémon card.")
        elif result.error == 30:
            raise ValueError("agent_ptr broken.")
        else:
            raise RuntimeError()

    return result.state

def search_step(search_id: int, select: list[int]) -> SearchState:
    """Proceed to the next selection.
    
    Args:
        search_id: Search ID.
        select: Chosen option index.

    Returns:
        SearchSate: State for the next selection.
    """
    bs = lib.SearchStep(agent_ptr, search_id, (ctypes.c_int*len(select))(*select), len(select))
    result = json_to_dataclass(bs, ApiResult)
    if result.error != 0:
        if result.error == 1:
            raise ValueError("There is no element with the specified search_id.")
        elif result.error == 2:
            raise ValueError("Released item.")
        elif result.error == 3:
            raise ValueError("Cannot be selected because the battle has ended.")
        elif result.error == 4:
            raise ValueError("Must be Observation.select.minCount <= len(select) <= Observation.select.maxCount.")
        elif result.error == 5:
            raise ValueError("Must be 0 <= select elements < len(Observation.select.option).")
        elif result.error == 6:
            raise ValueError("Duplicate select elements.")
        elif result.error == 30:
            raise ValueError("agent_ptr broken.")
        else:
            raise RuntimeError()
    
    return result.state

def search_end() -> None:
    """Terminate the search. Memory used during the search will be reused in the next search."""
    lib.SearchEnd(agent_ptr)

def search_release(search_id: int) -> None:
    """Delete the state with the specified ID and make the memory available for reuse.
    
    Args:
        search_id: Search ID.
    """
    lib.SearchRelease(agent_ptr, search_id)

#endregion functions

