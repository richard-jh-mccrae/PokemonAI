"""`_finish_turn_last`'s commitment ladder, asserted through the public `decide` rather than a score.

Tiers: free dev 0 -> Supporter 1 -> attach / cost_discard 2 -> shuffle_hand Supporter 3 -> turn-enders 4.
"""
import pytest

from common.cards import CardFunctions
from common.strategy.general_strategy import GENERAL_STRATEGY
from common.pilot import Pilot
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy import Hypothesis, Line, Strategy
from pilot_helpers import ACTIVE, HAND, PLAY, make_select, opt, poke, state

ATTACH = 8
ITEM, SUPPORTER, BASIC_ENERGY = 1, 3, 5        # CardType (cg/api.py)
POKEGEAR = 1122
SALVATORE = 1189
DRAWSUP = 1224
LILLIES = 1227
WINCON = 900               # synthetic
PREEVO = 800               # synthetic
WATER = 3


def _stats():
    return DictCardStatProvider({
        WINCON: CardStat(WINCON, synthetic=True, name="Mega Starmie ex", hp=330, megaEx=True, maxDamage=210,
                         maxDamageCost=3, minAttackCost=1, minCostDamage=120, attacks=(10, 11),
                         evolvesFrom="Staryu", energyType=3),
        PREEVO: CardStat(PREEVO, synthetic=True, name="Staryu", hp=70, maxDamage=20, maxDamageCost=1,
                         minAttackCost=1, attacks=(12,), evolvesFrom=None),
        WATER: CardStat(WATER, name="Basic {W} Energy", hp=0, energyType=3, cardType=BASIC_ENERGY),
        POKEGEAR: CardStat(POKEGEAR, synthetic=True, name="Pokegear 3.0", hp=0, cardType=ITEM),
        SALVATORE: CardStat(SALVATORE, name="Salvatore", hp=0, cardType=SUPPORTER),
        DRAWSUP: CardStat(DRAWSUP, name="Cheren", hp=0, cardType=SUPPORTER),
        LILLIES: CardStat(LILLIES, name="Lillie's Determination", hp=0, cardType=SUPPORTER),
    }, attacks={10: AttackStat(10, damage=210, cost=3),
                11: AttackStat(11, damage=120, cost=1),
                12: AttackStat(12, damage=20, cost=1)})


def _funcs():
    return CardFunctions({POKEGEAR: ["dig", "draw"], SALVATORE: ["search", "rush_evolve"],
                          DRAWSUP: ["draw"], LILLIES: ["draw", "shuffle_hand"]})


def _pilot(strat=None, **kw):
    strat = strat or Strategy(roles={WINCON: ["win_condition", "primary_attacker"]},
                              lines=[Line(path=[PREEVO, WINCON], payoff=WINCON)])
    return Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=_stats(),
                 functions=_funcs(), **kw)


@pytest.mark.req("REQ-PILOT-0023")
def test_a_free_item_dig_is_sequenced_before_the_one_per_turn_supporter():
    pilot = _pilot()
    play_salvatore = opt(PLAY, area=HAND, index=0)
    play_pokegear = opt(PLAY, area=HAND, index=1)
    obs = make_select([play_salvatore, play_pokegear],
                      current=state(active=poke(PREEVO, hp=70), hand=[SALVATORE, POKEGEAR]))
    traces = pilot.explain(obs).options
    assert traces[0].score > traces[1].score        # Salvatore outscores Pokegear
    assert pilot.decide(obs) == [1]                 # ... yet the free Item dig goes first


@pytest.mark.req("REQ-PILOT-0024")
def test_an_unmodelled_draw_supporter_does_not_preempt_a_closed_energy_attach():
    """A generic draw has no joint distribution, so it cannot claim a sequencing slot (Issue #456)."""
    strat = Strategy(roles={WINCON: ["win_condition", "primary_attacker"]},
                     lines=[Line(path=[PREEVO, WINCON], payoff=WINCON)],
                     hypotheses=[Hypothesis(id="t-endorse-attach", rationale="test", weight=100,
                                            when=lambda c: c.option_type == ATTACH and c.card_id == WATER)])
    pilot = _pilot(strat=strat)
    play_draw_sup = opt(PLAY, area=HAND, index=0)
    attach = opt(ATTACH, area=HAND, index=1, inPlayArea=ACTIVE, inPlayIndex=0)
    obs = make_select([play_draw_sup, attach],
                      current=state(active=poke(PREEVO, energy=0, hp=70), hand=[DRAWSUP, WATER]))
    traces = pilot.explain(obs).options
    assert traces[1].score > traces[0].score        # attach outscores the Supporter ...
    assert pilot.decide(obs) == [1]                 # ... and the closed attachment remains selectable


@pytest.mark.req("REQ-PILOT-0025")
def test_a_hand_shuffle_supporter_is_sequenced_after_the_energy_attach():
    """Structural (tier 3 vs tier 2), not the -60 `attach-before-hand-shuffle` weight: the endorsement
    below overpowers that weight and the shuffle is still held until after the attach."""
    strat = Strategy(roles={WINCON: ["win_condition", "primary_attacker"]},
                     lines=[Line(path=[PREEVO, WINCON], payoff=WINCON)],
                     hypotheses=[Hypothesis(id="t-endorse-shuffle", rationale="test", weight=100,
                                            when=lambda c: c.card_id == LILLIES),
                                 Hypothesis(id="t-endorse-attach", rationale="test", weight=30,
                                            when=lambda c: c.option_type == ATTACH and c.card_id == WATER)])
    pilot = _pilot(strat=strat)
    play_shuffle = opt(PLAY, area=HAND, index=0)
    attach = opt(ATTACH, area=HAND, index=1, inPlayArea=ACTIVE, inPlayIndex=0)
    obs = make_select([play_shuffle, attach],
                      current=state(active=poke(PREEVO, energy=0, hp=70), hand=[LILLIES, WATER]))
    traces = pilot.explain(obs).options
    assert traces[0].score > 0                       # shuffle endorsed (positive) despite the -60 ...
    assert pilot.decide(obs) == [1]                  # ... yet the Energy attach goes first


BOSS = 1182
OPPFRAIL = 678
OPPBENCHIE = 679


@pytest.mark.req("REQ-PILOT-0026")
def test_a_gust_play_is_never_sequenced_ahead_of_a_menu_ko():
    """A gust changes the defender, so with a KO on the menu it drops to the last tier; a gust that
    UNLOCKS a KO (KO_SCORE-class tactical) still rides tier 0."""
    stats = _stats()
    stats._stats[BOSS] = CardStat(BOSS, synthetic=True, name="Boss's Orders", hp=0, cardType=SUPPORTER)
    stats._stats[OPPFRAIL] = CardStat(OPPFRAIL, synthetic=True, name="opp mega", hp=330, energyType=7)
    stats._stats[OPPBENCHIE] = CardStat(OPPBENCHIE, synthetic=True, name="opp benchie", hp=70, energyType=7)
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
