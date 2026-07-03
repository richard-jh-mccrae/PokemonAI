"""Supporter sequencing in `_finish_turn_last` — the commitment ladder that makes "play your free
Item digs, THEN commit your one-per-turn Supporter, THEN spend the blind Energy attach, and only
nuke your hand last" a STRUCTURAL property, not a fragile score race (the Pokegear-before-Salvatore
misplay: a Supporter scored as if it were a free dig). Verified through the PUBLIC Pilot interface
(`decide` picks the sequenced option). Tiers: free dev 0 -> Supporter 1 -> attach / cost_discard 2
-> shuffle_hand Supporter 3 -> turn-enders 4.
"""
import pytest

from common.cards import CardFunctions
from common.strategy.general_strategy import GENERAL_STRATEGY
from common.pilot import Pilot
from common.scouting.provider import CardStat, DictCardStatProvider
from common.strategy import Hypothesis, Line, Strategy
from pilot_helpers import ACTIVE, HAND, PLAY, make_select, opt, poke, state

ATTACH = 8
ITEM, SUPPORTER = 1, 3        # CardType (cg/api.py): Pokegear is an Item, Salvatore a Supporter
POKEGEAR = 1122              # Item — dig/draw: look top 7, may take Supporter to hand (a FREE dig)
SALVATORE = 1189            # Supporter — search/rush_evolve: the one-per-turn commitment
DRAWSUP = 1224              # Cheren — plain draw Supporter (draw, NOT shuffle_hand)
LILLIES = 1227             # Lillie's Determination — shuffle_hand Supporter (nukes the hand)
WINCON = 900               # Mega-ex win-condition (evolves from the pre-evo)
PREEVO = 800               # its pre-evolution (Staryu-like) — a rush_evolve target
WATER = 3                  # a reusable Basic Energy


def _stats():
    return DictCardStatProvider({
        WINCON: CardStat(WINCON, name="Mega Starmie ex", hp=330, megaEx=True, maxDamage=210,
                         maxDamageCost=3, minAttackCost=1, minCostDamage=120, attacks=(10, 11),
                         evolvesFrom="Staryu", energyType=3),
        PREEVO: CardStat(PREEVO, name="Staryu", hp=70, maxDamage=20, maxDamageCost=1,
                         minAttackCost=1, attacks=(12,), evolvesFrom=None),
        WATER: CardStat(WATER, name="Basic {W} Energy", hp=0, energyType=3),
        POKEGEAR: CardStat(POKEGEAR, name="Pokegear 3.0", hp=0, cardType=ITEM),
        SALVATORE: CardStat(SALVATORE, name="Salvatore", hp=0, cardType=SUPPORTER),
        DRAWSUP: CardStat(DRAWSUP, name="Cheren", hp=0, cardType=SUPPORTER),
        LILLIES: CardStat(LILLIES, name="Lillie's Determination", hp=0, cardType=SUPPORTER),
    })


def _funcs():
    return CardFunctions({POKEGEAR: ["dig", "draw"], SALVATORE: ["search", "rush_evolve"],
                          DRAWSUP: ["draw"], LILLIES: ["draw", "shuffle_hand"]})


def _pilot(strat=None, **kw):
    strat = strat or Strategy(roles={WINCON: ["win_condition", "primary_attacker"]},
                              lines=[Line(path=[PREEVO, WINCON], payoff=WINCON)])
    return Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=_stats(),
                 functions=_funcs(), attacks={10: 210, 11: 120, 12: 20},
                 attack_costs={10: 3, 11: 1, 12: 1}, **kw)


# ---------------------------------------------------------------- (a) free Item dig before Supporter
@pytest.mark.req("REQ-PILOT-0023")
def test_a_free_item_dig_is_sequenced_before_the_one_per_turn_supporter():
    """Pokegear-before-Salvatore. SETUP with a pre-evolution (Staryu) in play: Salvatore's rush_evolve
    fires, so the Supporter strongly OUTSCORES a Pokegear that gets only the dig bonus. Yet playing
    your one Supporter is a commitment — the free Item dig (tier 0) is sequenced ahead of the Supporter
    (tier 1), so Pokegear is played first and may upgrade which Supporter you commit."""
    pilot = _pilot()
    play_salvatore = opt(PLAY, area=HAND, index=0)
    play_pokegear = opt(PLAY, area=HAND, index=1)
    obs = make_select([play_salvatore, play_pokegear],
                      current=state(active=poke(PREEVO, hp=70), hand=[SALVATORE, POKEGEAR]))
    traces = pilot.explain(obs).options
    assert traces[0].score > traces[1].score        # Salvatore (rush_evolve + search) outscores Pokegear
    assert pilot.decide(obs) == [1]                 # ... yet free Item dig sequenced first


# ------------------------------------------------------------ (b) Supporter before a non-KO attach
@pytest.mark.req("REQ-PILOT-0024")
def test_a_supporter_is_sequenced_before_a_non_ko_energy_attach():
    """A Supporter is informative (draws / searches / tutors), so play it before you blind-commit your
    one Energy attach — it may reveal the better attach target or the Energy you'd rather place. Even
    when the attach OUTSCORES the Supporter, the Supporter (tier 1) is sequenced ahead of the attach
    (tier 2). A plain draw Supporter vs a (synthetically endorsed) attach to a Pokemon that needs Energy."""
    strat = Strategy(roles={WINCON: ["win_condition", "primary_attacker"]},
                     lines=[Line(path=[PREEVO, WINCON], payoff=WINCON)],
                     hypotheses=[Hypothesis(id="t-endorse-attach", rationale="test", weight=100,
                                            when=lambda c: c.option_type == ATTACH and c.card_id == WATER)])
    pilot = _pilot(strat=strat)
    play_draw_sup = opt(PLAY, area=HAND, index=0)                                # Cheren (draw Supporter)
    attach = opt(ATTACH, area=HAND, index=1, inPlayArea=ACTIVE, inPlayIndex=0)   # W -> Staryu (needs energy)
    obs = make_select([play_draw_sup, attach],
                      current=state(active=poke(PREEVO, energy=0, hp=70), hand=[DRAWSUP, WATER]))
    traces = pilot.explain(obs).options
    assert traces[1].score > traces[0].score        # attach outscores the Supporter ...
    assert pilot.decide(obs) == [0]                 # ... yet Supporter sequenced first


# --------------------------------------------------- (c) Energy attach before a hand-shuffle Supporter
@pytest.mark.req("REQ-PILOT-0025")
def test_a_hand_shuffle_supporter_is_sequenced_after_the_energy_attach():
    """Attach the Energy you're holding BEFORE a Supporter that shuffles your hand into the deck
    (Lillie's / Harlequin) — else you shuffle away the Energy you needed. This is STRUCTURAL (the
    shuffle is tier 3, the attach tier 2), not merely the -60 `attach-before-hand-shuffle` weight: even
    a shuffle endorsed POSITIVE (here by a stand-in rule that overpowers the -60, with a reusable
    Energy still in hand) is held until after the attach. Both plays are synthetically endorsed so only
    the commitment tiers decide the order."""
    strat = Strategy(roles={WINCON: ["win_condition", "primary_attacker"]},
                     lines=[Line(path=[PREEVO, WINCON], payoff=WINCON)],
                     hypotheses=[Hypothesis(id="t-endorse-shuffle", rationale="test", weight=100,
                                            when=lambda c: c.card_id == LILLIES),
                                 Hypothesis(id="t-endorse-attach", rationale="test", weight=30,
                                            when=lambda c: c.option_type == ATTACH and c.card_id == WATER)])
    pilot = _pilot(strat=strat)
    play_shuffle = opt(PLAY, area=HAND, index=0)                                 # Lillie's (shuffle_hand)
    attach = opt(ATTACH, area=HAND, index=1, inPlayArea=ACTIVE, inPlayIndex=0)   # W -> Staryu (needs energy)
    obs = make_select([play_shuffle, attach],
                      current=state(active=poke(PREEVO, energy=0, hp=70), hand=[LILLIES, WATER]))
    traces = pilot.explain(obs).options
    assert traces[0].score > 0                       # shuffle endorsed (positive) despite the -60 ...
    assert pilot.decide(obs) == [1]                  # ... yet Energy attach sequenced first


# ----------------------------------------------- (d) a gust never sequences ahead of a menu KO
BOSS = 1182                                          # Boss's Orders — gust Supporter
OPPFRAIL = 678                                       # opponent's Active: 190 HP (Nebula 210 KOs it)
OPPBENCHIE = 679                                     # opponent's benched 70-HP body (the gust bait)


@pytest.mark.req("REQ-PILOT-0026")
def test_a_gust_play_is_never_sequenced_ahead_of_a_menu_ko():
    """ep83456015 f38: my Mega can Nebula-KO the opponent's 190-HP Active (3 prizes), but the
    endorsed Boss's Orders — an 'informative Supporter' by the old ladder — sequenced FIRST, and the
    gust SWAPPED the defender: the KO the menu offered was forfeited for a 1-prize bait. A gust is a
    defender-changing commitment, so with a KO on the menu it drops to the last tier; its own
    KO-UNLOCK path (KO_SCORE-class gust tactical) still rides tier 0."""
    stats = _stats()
    stats._stats[BOSS] = CardStat(BOSS, name="Boss's Orders", hp=0, cardType=SUPPORTER)
    stats._stats[OPPFRAIL] = CardStat(OPPFRAIL, name="opp mega", hp=330, energyType=7)
    stats._stats[OPPBENCHIE] = CardStat(OPPBENCHIE, name="opp benchie", hp=70, energyType=7)
    strat = Strategy(roles={WINCON: ["win_condition", "primary_attacker"]},
                     lines=[Line(path=[PREEVO, WINCON], payoff=WINCON)],
                     hypotheses=[Hypothesis(id="t-endorse-gust", rationale="test", weight=100,
                                            when=lambda c: c.card_id == BOSS)])
    pilot = _pilot(strat=strat)
    pilot.stats = stats
    pilot.functions = CardFunctions({BOSS: ["gust"]})
    play_boss = opt(PLAY, area=HAND, index=0)
    board = state(active=poke(WINCON, energy=3, hp=330), hand=[BOSS],
                  opp_active=poke(OPPFRAIL, hp=190), opp_bench=[poke(OPPBENCHIE, hp=70)],
                  prizes=6, opp_prizes=6)
    obs = make_select([play_boss, opt(type=13, attackId=10), opt(type=14)], current=board)
    traces = pilot.explain(obs).options
    assert traces[1].tactical >= 1000                # the Nebula KO is on the menu
    assert traces[0].score > 0                       # the gust is endorsed ...
    assert pilot.decide(obs) == [1]                  # ... yet the KO goes first; the gust never forfeits it
