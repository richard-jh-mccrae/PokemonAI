"""Prize-economy promote: interpose a cheap attacker to preserve a higher-prize win-condition.

When my Active is Knocked Out and both a cheap 1-prize attacker (Cinderace) and a second, higher-prize
win-condition (Mega Starmie ex) sit on the Bench with Energy, the forced promote is a prize-race
decision, not "promote the best attacker". Leading with the 3-prize Mega feeds the opponent the game if
they can KO it; interposing the 1-prize Cinderace soaks the hit for a single prize and keeps the fresh
finisher on the Bench. `interpose-the-cheap-attacker-to-preserve-the-wincon` fires on three drivers —
(a) the cheap body hits the opponent's Active Weakness (x2 chip), (b) it accelerates an under-built
finisher off the Bench, (c) the opponent has shown a gust — and is HARD-VETOED when the opponent needs
only one prize (any KO wins for them then). Deck-agnostic; the signals live on Board/Context.
"""
import pytest

from common.cards import CardFunctions
from common.pilot import Pilot
from common.scouting.provider import CardStat, DictCardStatProvider
from common.strategy import Line, Strategy
from common.strategy.context import _BASIC_ENERGY
from common.strategy.general_strategy import GENERAL_STRATEGY

TO_ACTIVE = 4
FIRE, WATER, LIGHTNING, METAL = 2, 3, 4, 6
MEGA, STARYU, CINDERACE = 1031, 1030, 666
ARCHALUDON, NEUTRAL = 190, 999
WATER_ENERGY, BOSS_ORDERS = 3, 1182

RULE = "interpose-the-cheap-attacker-to-preserve-the-wincon"


def _fired(t):
    return {h.id for h, _ in t.fired}


def _pilot(deck_has_basic=True):
    stats = DictCardStatProvider({
        MEGA: CardStat(MEGA, name="Mega Starmie ex", hp=330, megaEx=True, minAttackCost=1,
                       minCostDamage=120, maxDamage=210, maxDamageCost=3, energyType=WATER,
                       weakness=LIGHTNING, evolvesFrom="Staryu"),
        STARYU: CardStat(STARYU, name="Staryu", hp=70, minAttackCost=1, minCostDamage=20),
        CINDERACE: CardStat(CINDERACE, name="Cinderace", hp=160, minAttackCost=1, minCostDamage=50,
                            maxDamage=50, maxDamageCost=1, energyType=FIRE, weakness=WATER),
        ARCHALUDON: CardStat(ARCHALUDON, name="Archaludon ex", hp=300, ex=True, energyType=METAL,
                             weakness=FIRE, minAttackCost=3, minCostDamage=160),
        NEUTRAL: CardStat(NEUTRAL, name="Neutral Wall", hp=300, energyType=METAL, weakness=LIGHTNING,
                          minAttackCost=2, minCostDamage=100),
        WATER_ENERGY: CardStat(WATER_ENERGY, name="Water Energy", hp=0, energyType=WATER,
                               cardType=_BASIC_ENERGY),
    })
    strat = Strategy(lines=[Line(path=[STARYU, MEGA], payoff=MEGA, role="win_condition")],
                     roles={MEGA: ["win_condition", "primary_attacker"],
                            CINDERACE: ["accel_source", "starter"], STARYU: ["starter"]})
    deck = ([WATER_ENERGY] * 8 + [1] * 52) if deck_has_basic else [1] * 60
    return Pilot(strat, deck=deck, general_strategy=GENERAL_STRATEGY, stats=stats,
                 functions=CardFunctions({CINDERACE: ["opener"], BOSS_ORDERS: ["gust"]}),
                 attacks={}, attack_costs={})


def _obs(bench, opp_active, opp_prizes, opp_discard=()):
    me = {"active": [None], "bench": bench, "hand": [], "prize": [None] * 6, "discard": []}
    opp = {"active": [opp_active], "bench": [], "prize": [None] * opp_prizes,
           "discard": [{"id": c} for c in opp_discard]}
    return {"current": {"players": [me, opp], "yourIndex": 0, "turn": 8},
            "select": {"context": TO_ACTIVE, "minCount": 1, "maxCount": 1,
                       "option": [{"type": 3, "area": 5, "index": i, "playerIndex": 0}
                                  for i in range(len(bench))]}}


# idx0 = the cheap 1-prize attacker (Cinderace); idx1 = the second, 3-prize finisher (Mega Starmie ex).
def _bench(cinderace_energy=1, mega_energy=3):
    return [{"id": CINDERACE, "energies": [1] * cinderace_energy, "hp": 160},
            {"id": MEGA, "energies": [1] * mega_energy, "hp": 330}]


@pytest.mark.req("REQ-GEN-0054")
def test_interpose_cheap_attacker_over_wincon_on_weakness():
    # The worked case: first Mega KO'd, Bench = Cinderace + a fully-built second Mega, opponent's Active is
    # a Fire-weak Archaludon ex, opponent needs 3 prizes. Promote CINDERACE (50 -> 100 on Weakness, 1 prize
    # if it trades) and keep the 3-prize finisher fresh — not the second Mega (feeding it can lose the game).
    p = _pilot()
    obs = _obs(_bench(mega_energy=3), {"id": ARCHALUDON, "hp": 300, "energies": [1, 1]}, opp_prizes=3)
    board = p._board(obs, obs["select"])
    assert board.bench_wincon_prize_value == 3
    assert board.opp_prizes_remaining == 3
    dec = p.explain(obs)
    assert RULE in _fired(dec.options[0])                       # fires on the cheap Cinderace
    assert "promote-the-ready-wincon" in _fired(dec.options[1])  # the wincon rule still fires on the Mega
    assert RULE not in _fired(dec.options[1])                   # but never on the wincon itself
    assert p.decide(obs) == [0]                                 # Cinderace, not the second Mega


@pytest.mark.req("REQ-GEN-0054")
def test_interpose_accelerator_to_power_the_underbuilt_finisher():
    # Neutral matchup (no Weakness), but the benched finisher is only 1/3 Energy and Basic Energy remains in
    # deck: promote the accelerator so Turbo Flare loads the finisher to full off the Bench — which promoting
    # the finisher directly (one attach/turn) can't.
    p = _pilot()
    obs = _obs(_bench(mega_energy=1), {"id": NEUTRAL, "hp": 300, "energies": [1, 1]}, opp_prizes=3)
    board = p._board(obs, obs["select"])
    assert board.bench_wincon_underpowered                     # 1 Energy < maxDamageCost 3
    assert board.basic_energy_in_deck                          # deck still holds Water Energy to fetch
    dec = p.explain(obs)
    assert RULE in _fired(dec.options[0])
    assert p.decide(obs) == [0]


@pytest.mark.req("REQ-GEN-0054")
def test_no_interpose_accelerator_when_deck_has_no_basic_energy():
    # Same under-built finisher, but no Basic Energy left in deck -> Turbo Flare would whiff, so driver (b)
    # stands down. With no other driver, lead with the finisher.
    p = _pilot(deck_has_basic=False)
    obs = _obs(_bench(mega_energy=1), {"id": NEUTRAL, "hp": 300, "energies": [1, 1]}, opp_prizes=3)
    assert not p._board(obs, obs["select"]).basic_energy_in_deck
    dec = p.explain(obs)
    assert RULE not in _fired(dec.options[0])
    assert p.decide(obs) == [1]


@pytest.mark.req("REQ-GEN-0054")
def test_interpose_when_opponent_has_shown_a_gust():
    # Neutral matchup, finisher fully built: only the gust driver applies. A Boss's Orders in the opponent's
    # discard means they can drag the benched finisher out anyway -> interpose the cheap body to tax it.
    p = _pilot()
    obs = _obs(_bench(mega_energy=3), {"id": NEUTRAL, "hp": 300, "energies": [1, 1]}, opp_prizes=3,
               opp_discard=[BOSS_ORDERS])
    board = p._board(obs, obs["select"])
    assert board.opp_has_played_gust
    assert not board.bench_wincon_underpowered                 # full finisher: driver (b) is off
    dec = p.explain(obs)
    assert RULE in _fired(dec.options[0])
    assert p.decide(obs) == [0]


@pytest.mark.req("REQ-GEN-0054")
def test_never_interpose_when_opponent_needs_one_prize():
    # HARD VETO: opponent needs a single prize. Even Fire-weak (driver a would fire), interposing a 1-prize
    # body just hands them the win -- lead with the strongest body (the Mega), which might survive / KO back.
    p = _pilot()
    obs = _obs(_bench(mega_energy=3), {"id": ARCHALUDON, "hp": 300, "energies": [1, 1]}, opp_prizes=1)
    dec = p.explain(obs)
    assert RULE not in _fired(dec.options[0])
    assert p.decide(obs) == [1]


@pytest.mark.req("REQ-GEN-0054")
def test_no_interpose_when_no_driver_applies():
    # Neutral matchup, finisher fully powered, no gust shown -> none of (a)/(b)/(c). The proven default
    # holds: promote the ready win-condition. Guards against the rule over-firing.
    p = _pilot()
    obs = _obs(_bench(mega_energy=3), {"id": NEUTRAL, "hp": 300, "energies": [1, 1]}, opp_prizes=3)
    dec = p.explain(obs)
    assert RULE not in _fired(dec.options[0])
    assert p.decide(obs) == [1]
