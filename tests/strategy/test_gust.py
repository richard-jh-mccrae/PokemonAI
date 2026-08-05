"""Gust (Boss's Orders) — the whether-to-play line (general doctrine, ADR-0022, docs/general-strategy.md).

Behaviour through the Pilot's PUBLIC interface (`decide` / `explain`): the agent plays a gust Supporter
exactly when it converts to a KO this turn that beats its best non-gust line, and holds it otherwise.
Lib-free: observations built by hand via `pilot_helpers`.
"""
import pytest

from common.cards import CardFunctions
from common.strategy.general_strategy import GENERAL_STRATEGY
from common.pilot import KO_SCORE, Board, Pilot
from common.scouting.matchup_plan import build_matchup_plan
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy import Strategy
from pilot_helpers import (
    BENCH, HAND, MAIN, PLAY, SWITCH, attack_opt, card_opt, make_select, opt, poke, state)

END = 14  # OptionType.END (pilot_helpers doesn't export it)

BOSS = 1182        # Boss's Orders — Supporter, Function Tag `gust`
WINCON = 901       # my Active attacker / win-condition
WALL = 800         # opp Active: high-HP wall, can't KO
BENCHIE = 700      # opp benched: low HP, KO-able after gust (1 prize)
KOABLE_ACTIVE = 810  # opp Active: low HP, KO-able by my cheap attack now (1 prize)
EX_BENCHIE = 702   # opp benched ex: KO-able after gust, worth 2 prizes
OFF_WINCON = 902   # my Active: attacker that is NOT the deck's win-condition
TUTOR = 903        # a setup search Supporter (Function Tag `search`)
BIG_BENCHIE = 703  # opp benched: too much HP to KO after gust
MEGA_WINCON = 904  # my Active: 3-prize Mega ex win-condition (what a live attacker threatens)
LIVE_ATTACKER = 705  # opp benched 1-prize attacker, energized, hits hard enough to KO my Active
DOOM_ACTIVE = 811  # opp Active: wall I can't KO, but KOs my Active next turn
STALL_TARGET = 706  # opp benched: energyless + high retreat — defensive stall-gust pick
PREEVO_THREAT = 707  # opp benched pre-evo whose LINE becomes an attacker (forward-evolution)
EVO_FORM = 708     # attacker PREEVO_THREAT evolves into (high forward_max_damage)
DEAD_END = 709     # opp benched mon that evolves into nothing (forward_max_damage 0)
SCALER_PREEVO = 740  # opp benched pre-evo whose line's threat is a SCALER — printed index reads 10
SCALER_FORM = 741    # ...the Alakazam-shaped form it becomes (printed 10, board-priced far higher)
A_SCALE = 8130       # that form's attack: printed 10 + 20 per card in the attacker's hand
WEAK_ATTACKER = 905  # my Active: 10-damage attacker, can't KO a 20-HP body by attacking
ITEM_GUST = 1183   # synthetic Item gust (cardType ITEM) — doesn't cost the one Supporter slot
FIGHT_GUST = 906   # my Active: Fighting attacker (120) — exercises Resistance in gust oracle
RESIST_BENCHIE = 710  # opp benched: HP 100, RESISTS Fighting (survives 120-30=90) — a false KO
SNIPER_WINCON = 907  # my Active: win-condition whose attack ALSO snipes bench (Jetting Blow-like)
DWEB_HI = 720      # opp benched, KO-able, removal lets my snipe finish DWEB_LO (2-prize line)
DWEB_LO = 721      # opp benched, KO-able, low HP — finished by 50 snipe only if DWEB_HI gusted
A_SNIPE_G = 104    # my Active's snipe attack id (120 damage + 50 bench rider)
DOOM_ATK, KADA_ATK = 8100, 8110   # per-attack ids: the doom Actives DO damage us now (register `opp_active_can_damage_us`)
# my-side cheapest-attack ids (ADR-0052: the card-level minCostDamage fallback is retired, so every
# attacker's cheapest attack is a real record — same damage/cost the old fallback read)
A_WIN, A_OFF, A_MEGA, A_FIGHT, A_WEAK, A_FRAG = 9010, 9020, 9040, 9060, 9050, 9080
MY_FRAGILE = 908   # my Active: 130 HP — KO'd by opp's FORWARD hand-size evolution, not now
KADA = 911         # opp Active: weak pre-evo (30 dmg) that EVOLVES into a hand-size attacker
ALAK = 912         # hand_size_attacker KADA evolves into (Alakazam: 20 dmg/card via handSizeDamage)
STALL1 = 711       # opp benched body: energyless, retreat 1 — valid stall target (can't pay retreat)
SPREADER = 909     # my Active: 200-damage attacker with a 60 bench SPREAD rider (Phantom Dive-like)
A_SPREAD = 9090    # its attack id
KOABLE_DOOM = 812  # opp Active: KO-able by my 120 AND dooms my Active next turn (200 incoming)
DURA_W = 730       # opp energyless retreat-2 wall PRE-EVO whose line becomes a 270 attacker (Duraludon-like)
EVO_DURA = 731     # the attacker DURA_W evolves into (forward danger, ADR-0066 wall-swap tests)
PSYCHIC = 7        # energy type for the opp pre-evo
WATER, LIGHTNING, FIRE, FIGHTING = 3, 4, 2, 6
SUPPORTER, ITEM = 3, 1   # CardType values (cg/api.py)

_CARDS = {
    BOSS: CardStat(BOSS, hp=0, cardType=SUPPORTER),
    ITEM_GUST: CardStat(ITEM_GUST, synthetic=True, hp=0, cardType=ITEM),
    WINCON: CardStat(WINCON, synthetic=True, energyType=WATER, minAttackCost=1, minCostDamage=120,
                     attacks=(A_WIN,)),
    WALL: CardStat(WALL, synthetic=True, hp=330),
    BENCHIE: CardStat(BENCHIE, synthetic=True, hp=60),
    KOABLE_ACTIVE: CardStat(KOABLE_ACTIVE, synthetic=True, hp=100),
    EX_BENCHIE: CardStat(EX_BENCHIE, synthetic=True, hp=60, ex=True),
    OFF_WINCON: CardStat(OFF_WINCON, synthetic=True, energyType=WATER, minAttackCost=1, minCostDamage=120,
                         attacks=(A_OFF,)),
    TUTOR: CardStat(TUTOR, synthetic=True, hp=0),
    BIG_BENCHIE: CardStat(BIG_BENCHIE, synthetic=True, hp=200),
    MEGA_WINCON: CardStat(MEGA_WINCON, synthetic=True, energyType=WATER, weakness=LIGHTNING, megaEx=True,
                          minAttackCost=1, minCostDamage=120, attacks=(A_MEGA,)),
    LIVE_ATTACKER: CardStat(LIVE_ATTACKER, synthetic=True, energyType=WATER, maxDamage=200),
    DOOM_ACTIVE: CardStat(DOOM_ACTIVE, synthetic=True, energyType=FIRE, hp=330, maxDamage=200, attacks=(DOOM_ATK,)),
    STALL_TARGET: CardStat(STALL_TARGET, synthetic=True, hp=200, retreatCost=2),
    PREEVO_THREAT: CardStat(PREEVO_THREAT, synthetic=True, name="Riolu", hp=60),
    EVO_FORM: CardStat(EVO_FORM, synthetic=True, name="MegaLucario", evolvesFrom="Riolu", maxDamage=270,
                       megaEx=True),   # a Mega ex: 3 prizes. Unset until ADR-TEMP-398 made the
                                       # line's PRIZE load-bearing; the card always was one.
    DEAD_END: CardStat(DEAD_END, synthetic=True, name="Ditto", hp=60),
    # An ALAKAZAM-SHAPED line: the forward form's printed `maxDamage` is a trivial 10 because its
    # whole output is a Damage Formula scaler (`per_unit x count(variable)`). The printed forward
    # index therefore reads this line at 10 and the pre-ADR-TEMP-398 `_gust_forward_denial` scored
    # it exactly 0, while the board-priced `forward_threat_ceiling` sees the real number.
    SCALER_PREEVO: CardStat(SCALER_PREEVO, synthetic=True, name="Abra", hp=60),
    SCALER_FORM: CardStat(SCALER_FORM, synthetic=True, name="Alakazam", evolvesFrom="Abra", hp=140,
                          maxDamage=10, attacks=(A_SCALE,)),
    WEAK_ATTACKER: CardStat(WEAK_ATTACKER, synthetic=True, energyType=WATER, minAttackCost=1, minCostDamage=10,
                            attacks=(A_WEAK,)),
    FIGHT_GUST: CardStat(FIGHT_GUST, synthetic=True, energyType=FIGHTING, minAttackCost=1, minCostDamage=120,
                         attacks=(A_FIGHT,)),
    RESIST_BENCHIE: CardStat(RESIST_BENCHIE, synthetic=True, hp=100, resistance=FIGHTING),
    SNIPER_WINCON: CardStat(SNIPER_WINCON, synthetic=True, energyType=WATER, minAttackCost=1, minCostDamage=120,
                            attacks=(A_SNIPE_G,)),
    DWEB_HI: CardStat(DWEB_HI, synthetic=True, hp=70),
    DWEB_LO: CardStat(DWEB_LO, synthetic=True, hp=20),
    MY_FRAGILE: CardStat(MY_FRAGILE, synthetic=True, energyType=WATER, hp=130, minAttackCost=1, minCostDamage=50,
                         attacks=(A_FRAG,)),
    KADA: CardStat(KADA, synthetic=True, name="TKadabra", hp=80, energyType=PSYCHIC, maxDamage=30,
                   minAttackCost=1, minCostDamage=30, attacks=(KADA_ATK,)),  # opp Active: weak pre-evo…
    ALAK: CardStat(ALAK, synthetic=True, name="TAlakazam", evolvesFrom="TKadabra", hp=140, minAttackCost=1,
                   handSizeDamage=20),                                  # …evolves into hand-size KO
    STALL1: CardStat(STALL1, synthetic=True, hp=70, retreatCost=1),                     # energyless retreat-1 stall body
    SPREADER: CardStat(SPREADER, synthetic=True, energyType=WATER, minAttackCost=1, minCostDamage=200,
                       attacks=(A_SPREAD,)),
    KOABLE_DOOM: CardStat(KOABLE_DOOM, synthetic=True, hp=100, energyType=FIRE, maxDamage=200,
                          attacks=(DOOM_ATK,)),
    DURA_W: CardStat(DURA_W, synthetic=True, name="TDura", hp=130, retreatCost=2),
    EVO_DURA: CardStat(EVO_DURA, synthetic=True, name="TArcha", evolvesFrom="TDura", maxDamage=270),
}
_ATTACKS = {   # every attacker's cheapest attack as a real record (fallback retired, ADR-0052)
    A_SPREAD: AttackStat(A_SPREAD, damage=200, cost=1, benchSpread=60),
    A_WIN: AttackStat(A_WIN, damage=120, cost=1),
    A_OFF: AttackStat(A_OFF, damage=120, cost=1),
    A_MEGA: AttackStat(A_MEGA, damage=120, cost=1),
    # Printed 10, but 20 more per card in the ATTACKER's hand — the shape whose whole threat lives
    # in the Damage Formula and which the printed forward index cannot see.
    A_SCALE: AttackStat(A_SCALE, damage=10, cost=1, scaleVar="atk_hand", scalePerUnit=20),
    A_FIGHT: AttackStat(A_FIGHT, damage=120, cost=1),
    A_WEAK: AttackStat(A_WEAK, damage=10, cost=1),
    A_FRAG: AttackStat(A_FRAG, damage=50, cost=1),
    A_SNIPE_G: AttackStat(A_SNIPE_G, damage=120, cost=1, benchSnipe=50),
    DOOM_ATK: AttackStat(DOOM_ATK, damage=200, cost=1),
    KADA_ATK: AttackStat(KADA_ATK, damage=30, cost=1),
}
_STATS = DictCardStatProvider(_CARDS, attacks=_ATTACKS)
_TAGS = CardFunctions({BOSS: ["gust"], ITEM_GUST: ["gust"], TUTOR: ["search"],
                       ALAK: ["hand_size_attacker"]})


def _pilot():
    return Pilot(Strategy(roles={WINCON: ["win_condition"]}), deck=[1] * 60,
                 general_strategy=GENERAL_STRATEGY, stats=_STATS, functions=_TAGS)


def _fired(option_trace):
    return {h.id for h, _ in option_trace.fired}


@pytest.mark.req("REQ-GUST-0001")
def test_gust_for_the_ko_plays_bosss_to_reach_a_benched_ko():
    """Opp Active is a wall I can't KO (120 < 330) but a benched mon is KO-able (120 >= 60) and Boss's
    is in hand → play Boss's Orders to drag the benched mon up. Options: [chip attack, play Boss's,
    End] → choose the Boss's play (index 1)."""
    obs = make_select(
        [attack_opt(555), opt(PLAY, area=HAND, index=0), opt(END)],
        context=MAIN,
        current=state(active=poke(WINCON, energy=1, hp=200),
                      opp_active=poke(WALL, hp=330),
                      opp_bench=[poke(BENCHIE, hp=60)],
                      hand=[BOSS]))
    p = _pilot()
    assert "gust-for-the-ko" in _fired(p.explain(obs).options[1])
    assert p.decide(obs) == [1]


@pytest.mark.req("REQ-GUST-0012")
def test_gust_for_the_ko_needs_a_payable_attack_this_turn():
    """ep83457493 f31: my Active had NO Energy and the hand held none — no attack was payable, so
    'gust for the KO' had no KO to convert (it fired anyway and Boss's beat the hand-refresh the
    dead hand needed). The whether-to-play signal now gates on the Energy the Active can actually
    pay this turn (attached + the best unspent hand attach): with none the gust is silent; hand
    the Active a {W} Energy and the same board endorses it again."""
    WATER_CARD = 3
    stats = DictCardStatProvider(dict(_STATS._stats), attacks=_ATTACKS)
    stats._stats[WATER_CARD] = CardStat(WATER_CARD, name="Basic {W} Energy", hp=0, energyType=WATER)

    def _obs(hand):
        return make_select(
            [opt(PLAY, area=HAND, index=0), opt(END)], context=MAIN,
            current=state(active=poke(WINCON, energy=0, hp=200),
                          opp_active=poke(WALL, hp=330),
                          opp_bench=[poke(BENCHIE, hp=60)], hand=hand))

    p = Pilot(Strategy(roles={WINCON: ["win_condition"]}), deck=[1] * 60,
              general_strategy=GENERAL_STRATEGY, stats=stats, functions=_TAGS)
    assert "gust-for-the-ko" not in _fired(p.explain(_obs([BOSS])).options[0])   # unpayable: silent
    assert "gust-for-the-ko" in _fired(p.explain(_obs([BOSS, WATER_CARD])).options[0])  # payable: fires


@pytest.mark.req("REQ-GUST-0001")
def test_gust_for_the_ko_stands_down_in_setup_before_the_wincon_is_online():
    """SETUP with no win-condition in play: a cheap gustable prize must not preempt developing the
    win-condition — gust-for-the-ko stands down so a setup tutor wins the one Supporter slot."""
    obs = make_select(
        [opt(PLAY, area=HAND, index=0), opt(PLAY, area=HAND, index=1), opt(END)],
        context=MAIN,
        current=state(active=poke(OFF_WINCON, energy=1, hp=200),
                      opp_active=poke(WALL, hp=330),
                      opp_bench=[poke(BENCHIE, hp=60)],
                      hand=[TUTOR, BOSS]))
    p = _pilot()
    assert "gust-for-the-ko" not in _fired(p.explain(obs).options[1])
    assert p.decide(obs) == [0]   # play tutor, develop win-condition first


@pytest.mark.req("REQ-GUST-0005")
def test_item_gust_into_a_ko_fires_in_setup_unlike_a_supporter():
    """#12 Item/Supporter split: an ITEM gust (cardType ITEM, e.g. Pokémon Catcher) doesn't cost your
    one Supporter slot, so the SETUP-before-wincon damping that holds back a Supporter gust does NOT
    apply — a free Item gust into a benched KO fires even in setup. (Same board as the Supporter
    stand-down test above, but the gust card is an Item.)"""
    obs = make_select(
        [opt(PLAY, area=HAND, index=0), opt(PLAY, area=HAND, index=1), opt(END)],
        context=MAIN,
        current=state(active=poke(OFF_WINCON, energy=1, hp=200),
                      opp_active=poke(WALL, hp=330),
                      opp_bench=[poke(BENCHIE, hp=60)],
                      hand=[ITEM_GUST, TUTOR]))
    p = _pilot()
    assert "gust-for-the-ko" in _fired(p.explain(obs).options[0])   # Item gust fires even in setup, unlike Supporter


@pytest.mark.req("REQ-GUST-0001")
def test_gust_for_the_lethal_fires_even_through_the_setup_damping():
    """A gust that takes my last prize WINS — it must fire even in SETUP before the win-condition is
    online (where a non-lethal gust stands down). The wall Active is un-KO-able, but a benched mon is
    KO-able for my final prize → take the game over a setup tutor."""
    obs = make_select(
        [opt(PLAY, area=HAND, index=0), opt(PLAY, area=HAND, index=1), opt(END)],
        context=MAIN,
        current=state(active=poke(OFF_WINCON, energy=1, hp=200),
                      opp_active=poke(WALL, hp=330),
                      opp_bench=[poke(BENCHIE, hp=60)],
                      hand=[TUTOR, BOSS], prizes=1))
    p = _pilot()
    assert p.explain(obs).options[1].tactical >= KO_SCORE   # lethal gust = KO_SCORE-class (Tactical)
    assert p.decide(obs) == [1]                             # take game over a setup tutor


@pytest.mark.req("REQ-GUST-0001")
def test_gust_for_the_ko_silent_when_no_benched_mon_is_ko_able():
    """No gustable KO (the only benched mon, 200 HP, survives my 120) → HOLD Boss's: the rule stays
    silent and the agent does not spend its Supporter to gift the opponent a free switch."""
    obs = make_select(
        [attack_opt(555), opt(PLAY, area=HAND, index=0), opt(END)],
        context=MAIN,
        current=state(active=poke(WINCON, energy=1, hp=200),
                      opp_active=poke(WALL, hp=330),
                      opp_bench=[poke(BENCHIE, hp=200)],
                      hand=[BOSS]))
    p = _pilot()
    assert "gust-for-the-ko" not in _fired(p.explain(obs).options[1])
    assert p.decide(obs) != [1]


@pytest.mark.req("REQ-GUST-0001")
def test_gust_for_the_ko_silent_when_current_active_ko_is_at_least_as_good():
    """Net-of-baseline: I can KO the current Active for 1 prize (120 >= 100) and the gust only reaches
    another 1-prize KO → don't gust (the direct KO is free and gusting would bench their Active safe).
    The rule fires only when the gust beats the current-Active KO."""
    obs = make_select(
        [attack_opt(555), opt(PLAY, area=HAND, index=0), opt(END)],
        context=MAIN,
        current=state(active=poke(WINCON, energy=1, hp=200),
                      opp_active=poke(KOABLE_ACTIVE, hp=100),
                      opp_bench=[poke(BENCHIE, hp=60)],
                      hand=[BOSS]))
    p = _pilot()
    assert "gust-for-the-ko" not in _fired(p.explain(obs).options[1])
    assert p.decide(obs) != [1]


@pytest.mark.req("REQ-GUST-0001")
def test_gust_for_the_ko_fires_to_reach_a_higher_prize_than_the_current_active():
    """Prize-grab: I could KO the current Active for 1 prize, but a benched ex is KO-able for 2 → gust
    to reach the bigger prize (the gust beats the baseline KO)."""
    obs = make_select(
        [attack_opt(555), opt(PLAY, area=HAND, index=0), opt(END)],
        context=MAIN,
        current=state(active=poke(WINCON, energy=1, hp=200),
                      opp_active=poke(KOABLE_ACTIVE, hp=100),
                      opp_bench=[poke(EX_BENCHIE, hp=60)],
                      hand=[BOSS]))
    p = _pilot()
    assert "gust-for-the-ko" in _fired(p.explain(obs).options[1])
    assert p.decide(obs) == [1]


# --- #10 condition-rescue guard: never gust off a working special condition (ADR-0022) ------------

@pytest.mark.req("REQ-GUST-0004")
@pytest.mark.parametrize("cond", ["poisoned", "burned", "asleep", "paralyzed", "confused"])
def test_gust_for_the_stall_silent_when_opp_active_has_a_condition(cond):
    """The S1 stall scenario, but the opponent's Active carries a special condition → HOLD Boss's:
    gusting it off to the bench would CLEAR the condition (a free cure), so the stall stands down for
    every one of the five conditions (any condition is a gift). Mirror of the firing case below."""
    obs = make_select(
        [attack_opt(555), opt(PLAY, area=HAND, index=0), opt(END)],
        context=MAIN,
        current=state(active=poke(OFF_WINCON, energy=1, hp=100),
                      opp_active=poke(DOOM_ACTIVE, hp=330, energy=1),
                      opp_bench=[poke(STALL_TARGET, hp=200, energy=0)],
                      hand=[BOSS], opp_conditions=(cond,)))
    p = _pilot()
    assert "gust-for-the-stall" not in _fired(p.explain(obs).options[1])
    assert p.decide(obs) != [1]


@pytest.mark.req("REQ-GUST-0004")
def test_gust_for_the_stall_still_fires_with_no_condition():
    """Control: same stall scenario, opponent's Active has NO condition → the stall-gust fires (the
    guard only suppresses when a condition is present)."""
    obs = make_select(
        [attack_opt(555), opt(PLAY, area=HAND, index=0), opt(END)],
        context=MAIN,
        current=state(active=poke(OFF_WINCON, energy=1, hp=100),
                      opp_active=poke(DOOM_ACTIVE, hp=330, energy=1),
                      opp_bench=[poke(STALL_TARGET, hp=200, energy=0)],
                      hand=[BOSS]))
    p = _pilot()
    assert "gust-for-the-stall" in _fired(p.explain(obs).options[1])


@pytest.mark.req("REQ-GUST-0004")
def test_gust_for_the_ko_stands_down_when_burn_will_KO_the_active_for_the_same_prize():
    """Offensive baseline: my weak Active (10) can't KO the opponent's 20-HP Active by attacking, but
    it is BURNED — burn's 20 KOs it this Checkup for a free 1 prize. A gust reaching another 1-prize KO
    must NOT fire: gusting the burned Active off to the bench CURES it, trading my Supporter for a prize
    I'd already get. (The wincon is benched so the SETUP-damping can't confound the result.)"""
    obs = make_select(
        [attack_opt(555), opt(PLAY, area=HAND, index=0), opt(END)],
        context=MAIN,
        current=state(active=poke(WEAK_ATTACKER, energy=1, hp=200),
                      bench=[poke(WINCON, energy=1)],
                      opp_active=poke(KOABLE_ACTIVE, hp=20),
                      opp_bench=[poke(BENCHIE, hp=10)],
                      hand=[BOSS], opp_conditions=("burned",)))
    p = _pilot()
    assert "gust-for-the-ko" not in _fired(p.explain(obs).options[1])
    assert p.decide(obs) != [1]


@pytest.mark.req("REQ-GUST-0004")
def test_gust_for_the_ko_fires_past_the_condition_baseline_for_a_bigger_prize():
    """Contrast: same burn-doomed 1-prize Active, but the gust reaches a 2-prize benched ex → fire.
    The gust must beat the free condition-KO (1), and 2 > 1, so it's worth the Supporter."""
    obs = make_select(
        [attack_opt(555), opt(PLAY, area=HAND, index=0), opt(END)],
        context=MAIN,
        current=state(active=poke(WEAK_ATTACKER, energy=1, hp=200),
                      bench=[poke(WINCON, energy=1)],
                      opp_active=poke(KOABLE_ACTIVE, hp=20),
                      opp_bench=[poke(EX_BENCHIE, hp=10)],
                      hand=[BOSS], opp_conditions=("burned",)))
    p = _pilot()
    assert "gust-for-the-ko" in _fired(p.explain(obs).options[1])
    assert p.decide(obs) == [1]


# --- the gust TARGET-select: which benched Pokémon to drag up (SWITCH context, ADR-0022) -----------

@pytest.mark.req("REQ-GUST-0002")
def test_gust_target_drags_up_a_ko_able_bench_mon():
    """At the gust target-select (SWITCH, opponent-owned bench options), drag up a Pokémon my Active
    can KO (120 >= 60), not one it can't (120 < 200). Options index opp bench [big, KO-able]."""
    obs = make_select(
        [card_opt(BENCH, 0, player=1), card_opt(BENCH, 1, player=1)],
        context=SWITCH,
        current=state(active=poke(WINCON, energy=1, hp=200),
                      opp_bench=[poke(BIG_BENCHIE, hp=200), poke(BENCHIE, hp=60)]))
    p = _pilot()
    opts = p.explain(obs).options
    assert opts[1].tactical >= KO_SCORE     # KO-able target -> KO_SCORE-class (Tactical)
    assert opts[0].tactical < KO_SCORE      # un-KO-able target -> no boost
    assert p.decide(obs) == [1]


@pytest.mark.req("REQ-GUST-0002")
def test_gust_target_prefers_the_higher_prize_ko():
    """Two KO-able targets → drag up the bigger prize: a 2-prize ex over a 1-prize basic."""
    obs = make_select(
        [card_opt(BENCH, 0, player=1), card_opt(BENCH, 1, player=1)],
        context=SWITCH,
        current=state(active=poke(WINCON, energy=1, hp=200),
                      opp_bench=[poke(BENCHIE, hp=60), poke(EX_BENCHIE, hp=60)]))
    p = _pilot()
    opts = p.explain(obs).options
    assert opts[1].tactical > opts[0].tactical    # ex (2 prizes) outscores basic (1)
    assert p.decide(obs) == [1]


@pytest.mark.req("REQ-GUST-0002")
def test_gust_target_denial_outranks_a_bigger_inert_prize():
    """Prizes-first is a trap: an inert 2-prize ex vs a live 1-prize attacker that KOs my 3-prize
    win-condition next turn → drag up the live attacker (prizes + denial), not the fat inert prize."""
    obs = make_select(
        [card_opt(BENCH, 0, player=1), card_opt(BENCH, 1, player=1)],
        context=SWITCH,
        current=state(active=poke(MEGA_WINCON, energy=1, hp=200),
                      opp_bench=[poke(EX_BENCHIE, hp=60),                  # 2-prize, no Energy: inert
                                 poke(LIVE_ATTACKER, hp=60, energy=2)]))   # 1-prize, energized: threat
    p = _pilot()
    opts = p.explain(obs).options
    assert opts[1].tactical > opts[0].tactical    # denial lifts live attacker above bigger prize
    assert p.decide(obs) == [1]


@pytest.mark.req("REQ-GUST-0002")
def test_gust_target_breaks_ties_toward_an_evolving_threat():
    """Two equal-prize, inert, KO-able targets → drag up the one whose evolution line becomes an
    attacker (forward-evolution index), denying the latent threat. A sub-prize tie-break that never
    overrides a real prize difference."""
    obs = make_select(
        [card_opt(BENCH, 0, player=1), card_opt(BENCH, 1, player=1)],
        context=SWITCH,
        current=state(active=poke(WINCON, energy=1, hp=200),
                      opp_bench=[poke(DEAD_END, hp=60), poke(PREEVO_THREAT, hp=60)]))
    p = _pilot()
    opts = p.explain(obs).options
    assert opts[1].tactical > opts[0].tactical    # evolving-threat pre-evo edges the dead-end
    assert p.decide(obs) == [1]


@pytest.mark.req("REQ-GUST-0013")
def test_gust_matchup_priority_is_a_subprize_tiebreak_over_the_plan():
    # ADR-0051: the gust target tie-break reads the unified MatchupPlan — prefer dragging up the
    # higher-priority body (wincon > its pre-evo), sub-prize (never overrides a real prize gap), and
    # clamped to POSITIVE so a KO-able draw engine (`avoid`) is still worth its prize (0, not negative).
    plan = build_matchup_plan(brief_roles={WINCON: "prize_liability", PREEVO_THREAT: "fragile_preevo"},
                              draw_engine_ids={DEAD_END}, gamma=1.0)
    board = Board(matchup_plan=plan)
    p = _pilot()
    pl = p._gust_matchup_priority(board, {"id": WINCON})
    pe = p._gust_matchup_priority(board, {"id": PREEVO_THREAT})
    assert 0 < pe < pl < 1                                          # ordered, both sub-prize
    assert p._gust_matchup_priority(board, {"id": DEAD_END}) == 0   # avoid clamps to 0 (a KO is a KO)
    assert p._gust_matchup_priority(board, {"id": 999}) == 0        # unroled body


@pytest.mark.req("REQ-GUST-0002")
def test_gust_target_does_not_fire_on_my_own_retreat():
    """SWITCH is ALSO my own retreat (playerIndex == yourIndex) — the gust target scoring must stay
    silent on my own benched Pokémon (resolved by the owner guard), never treating a retreat as a gust."""
    obs = make_select(
        [card_opt(BENCH, 0, player=0)],
        context=SWITCH,
        current=state(active=poke(WINCON, energy=1, hp=200), bench=[poke(BENCHIE, hp=60)]))
    p = _pilot()
    trace = p.explain(obs).options[0]
    # `tactical` is a SUM across layers, and since ADR-0100 (#141) my OWN retreat destination is also
    # priced by the promote/retreat decider — so net that residual out to isolate the gust claim.
    residual = trace.promote_retreat_working["tactical"]
    assert trace.tactical - residual == 0            # my own bench -> no gust KO_SCORE boost


@pytest.mark.req("REQ-GUST-0009")
def test_gust_oracle_respects_resistance_no_false_ko():
    """The gust KO oracle (`_can_ko`) subtracts the defender's Resistance (flat -30, simulator-verified):
    a benched mon that RESISTS my Fighting attacker survives my 120 (120-30=90 < 100) → NOT a KO target,
    while an equal-HP non-resisting mon IS. Drag up the one I can actually KO, never the resisted body."""
    obs = make_select(
        [card_opt(BENCH, 0, player=1), card_opt(BENCH, 1, player=1)],
        context=SWITCH,
        current=state(active=poke(FIGHT_GUST, energy=1),
                      opp_bench=[poke(RESIST_BENCHIE, hp=100), poke(BENCHIE, hp=100)]))
    p = _pilot()
    opts = p.explain(obs).options
    assert opts[0].tactical < KO_SCORE      # resisted: 90 < 100, not a KO target
    assert opts[1].tactical >= KO_SCORE     # non-resisting equal-HP mon: KO-able
    assert p.decide(obs) == [1]


@pytest.mark.req("REQ-GUST-0002")
def test_gust_target_prefers_the_two_prize_snipe_synergy():
    """Two equal-prize KO-able targets, but gusting the 70-HP one lets my Active's 50 bench-snipe
    finish the 20-HP one for a SECOND prize, while gusting the 20-HP one leaves the snipe unable to
    reach the 70-HP body. Drag up the target that banks 2 prizes (ep82523164 f55)."""
    obs = make_select(
        [card_opt(BENCH, 0, player=1), card_opt(BENCH, 1, player=1)],
        context=SWITCH,
        current=state(active=poke(SNIPER_WINCON, energy=1),
                      opp_bench=[poke(DWEB_HI, hp=70), poke(DWEB_LO, hp=20)]))
    p = Pilot(Strategy(roles={SNIPER_WINCON: ["win_condition"]}), deck=[1] * 60,
              general_strategy=GENERAL_STRATEGY,
              stats=_STATS,
              functions=_TAGS)
    opts = p.explain(obs).options
    assert opts[0].tactical > opts[1].tactical   # 70-HP gust enables the 2-prize snipe synergy
    assert p.decide(obs) == [0]


# --- forward-doom Posture: anticipate opp's next-turn EVOLUTION threat (ep82754875 f52) -----------

@pytest.mark.req("REQ-GUST-0003")
def test_active_doomed_by_forward_hand_size_evolution():
    """Posture: the opp's Active (Kadabra, 30 dmg) can EVOLVE into a hand_size_attacker (Alakazam,
    20 dmg/card) whose Powerful Hand KOs my 130-HP Active next turn. `active_doomed` must see the
    forward threat — handCount 10 → 20 × (10 − 1 played) = 180 ≥ 130 — though Kadabra's own attack
    can't (ep82754875 f52). We play AS IF the opponent evolves and attaches."""
    obs = make_select([opt(END)],
                      current=state(active=poke(MY_FRAGILE, hp=130),
                                    opp_active=poke(KADA, energy=1), opp_hand_count=10))
    assert _pilot()._board(obs).active_doomed is True


@pytest.mark.req("REQ-GUST-0003")
def test_not_doomed_when_hand_too_small_for_the_forward_attacker():
    """Control: a 1-card hand (0 after the evolution is played) → 20 × 0 = 0 forward damage, and
    Kadabra's own 30 < 130, so my Active is NOT doomed. The threat is the hand SIZE, not the bare
    evolution — the read stays quiet when the hand can't back it up."""
    obs = make_select([opt(END)],
                      current=state(active=poke(MY_FRAGILE, hp=130),
                                    opp_active=poke(KADA, energy=1), opp_hand_count=1))
    assert _pilot()._board(obs).active_doomed is False


@pytest.mark.req("REQ-GUST-0013")
def test_active_doomed_by_general_forward_evolution_attack():
    """ep83457493 f20: the opp's Active (Riolu-like, tiny printed attack) EVOLVES into a 270-damage
    attacker next turn — `active_doomed` must see the general printed forward threat (not just the
    hand_size special case): 270 ≥ my 130. Same affordability gate (their Energy + one attach)."""
    obs = make_select([opt(END)],
                      current=state(active=poke(MY_FRAGILE, hp=130),
                                    opp_active=poke(PREEVO_THREAT, energy=1, hp=60),
                                    opp_hand_count=4))
    assert _pilot()._board(obs).active_doomed is True


@pytest.mark.req("REQ-GUST-0013")
def test_starved_stall_gust_outranks_development_only_under_the_energy_famine():
    """ep83457493 f20 end to end: forward-doomed (Riolu → 270 attacker) AND a provable energy famine
    (0 attached, none in hand — no attack payable), so `stall-gust-over-dev-when-starved` lifts
    Boss's over a strongly-endorsed tutor. Hand the Active one {W} Energy (attack payable again) and
    the rule stands down — normal development resumes."""
    stats = DictCardStatProvider(dict(_STATS._stats), attacks=_ATTACKS)
    # cardType 5 = BASIC_ENERGY (`cg.api.CardType`). Required, not decorative: the Attach Budget's
    # manual-attach leg counts hand Energy through `is_typed_basic_energy`, which is exactly
    # `cardType == 5 and energyType is not None`. Without it this card is not an Energy to the typed
    # reader at all, and the "fed" board below would still read as a famine.
    stats._stats[3] = CardStat(3, name="Basic {W} Energy", hp=0, energyType=WATER, cardType=5)
    p = Pilot(Strategy(roles={WINCON: ["win_condition"]}), deck=[1] * 60,
              general_strategy=GENERAL_STRATEGY, stats=stats, functions=_TAGS)

    def _obs(hand):
        return make_select(
            [opt(PLAY, area=HAND, index=0), opt(END)], context=MAIN,
            current=state(active=poke(MY_FRAGILE, energy=0, hp=130),
                          opp_active=poke(PREEVO_THREAT, energy=1, hp=60),
                          opp_bench=[poke(STALL_TARGET, hp=200, energy=0)],
                          hand=hand, opp_hand_count=4))

    starved = _obs([BOSS])
    assert "stall-gust-over-dev-when-starved" in _fired(p.explain(starved).options[0])
    assert p.decide(starved) == [0]
    fed = _obs([BOSS, 3])                              # a {W} in hand: cheapest attack payable again
    assert "stall-gust-over-dev-when-starved" not in _fired(p.explain(fed).options[0])


# --- tier-5 defensive stall-gust: strand an energyless high-retreat body (ADR-0022) ---------------

@pytest.mark.req("REQ-GUST-0003")
def test_stall_gust_strands_an_energyless_retreat_one_body_when_forward_doomed():
    """f52 end to end: doomed by the forward Kadabra→Alakazam, no KO available, and the opp's benched
    body is ENERGYLESS retreat-1 — it still can't pay that retreat (no Energy to discard), so play
    Boss's to strand it and buy a turn. The energyless retreat-1 target now qualifies (was retreat≥2)."""
    obs = make_select(
        [attack_opt(555), opt(PLAY, area=HAND, index=0), opt(END)],
        context=MAIN,
        current=state(active=poke(MY_FRAGILE, energy=1, hp=130),
                      opp_active=poke(KADA, energy=1),
                      opp_bench=[poke(STALL1, hp=70, energy=0)],
                      hand=[BOSS], opp_hand_count=10))
    p = _pilot()
    assert "gust-for-the-stall" in _fired(p.explain(obs).options[1])
    assert p.decide(obs) == [1]


@pytest.mark.req("REQ-GUST-0003")
def test_gust_for_the_stall_fires_when_stuck_with_an_energyless_high_retreat_target():
    """My Active is doomed, I have NO gustable KO and can't KO their Active, but they have an
    energyless, high-retreat benched mon → play Boss's to strand it Active and buy a setup turn."""
    obs = make_select(
        [attack_opt(555), opt(PLAY, area=HAND, index=0), opt(END)],
        context=MAIN,
        current=state(active=poke(OFF_WINCON, energy=1, hp=100),
                      opp_active=poke(DOOM_ACTIVE, hp=330, energy=1),
                      opp_bench=[poke(STALL_TARGET, hp=200, energy=0)],
                      hand=[BOSS]))
    p = _pilot()
    assert "gust-for-the-stall" in _fired(p.explain(obs).options[1])
    assert p.decide(obs) == [1]


@pytest.mark.req("REQ-GUST-0003")
def test_gust_for_the_stall_silent_when_not_under_threat():
    """Not doomed (the Active survives) → don't spend the Supporter on a marginal stall; hold it."""
    obs = make_select(
        [attack_opt(555), opt(PLAY, area=HAND, index=0), opt(END)],
        context=MAIN,
        current=state(active=poke(OFF_WINCON, energy=1, hp=300),   # 200 incoming < 300 → not doomed
                      opp_active=poke(DOOM_ACTIVE, hp=330, energy=1),
                      opp_bench=[poke(STALL_TARGET, hp=200, energy=0)],
                      hand=[BOSS]))
    p = _pilot()
    assert "gust-for-the-stall" not in _fired(p.explain(obs).options[1])
    assert p.decide(obs) != [1]


@pytest.mark.req("REQ-GUST-0003")
def test_gust_stall_target_picks_the_energyless_high_retreat_body():
    """In a stall (no KO-able target), drag up the energyless high-retreat body — never an energized
    attacker (gusting a live attacker into the Active Spot would gift them tempo)."""
    obs = make_select(
        [card_opt(BENCH, 0, player=1), card_opt(BENCH, 1, player=1)],
        context=SWITCH,
        current=state(active=poke(OFF_WINCON, energy=1, hp=100),
                      opp_bench=[poke(LIVE_ATTACKER, hp=200, energy=2),    # energized: would gift tempo
                                 poke(STALL_TARGET, hp=200, energy=0)]))   # energyless, retreat 2: stall
    p = _pilot()
    assert p.decide(obs) == [1]


# --- ADR-0066 (gusting Round 0): snipe-aware baseline / marginal stall / loaded-equal-KO ----------

@pytest.mark.req("REQ-GUST-0015")
def test_gust_for_the_ko_stands_down_when_the_menu_rider_already_collects_the_body():
    """ep86091435 f119: my attack's bench rider (50 snipe) already KOs the 40-HP benched body WITHOUT
    a gust — spending Boss's Orders to drag it up for the SAME single prize is a wasted Supporter.
    The whether-to-play baseline is snipe-aware: the gust must beat the best menu-attack TOTAL.
    Raise the body to 60 HP (out of the rider's reach) and the same gust fires again."""
    def _obs(bench_hp):
        return make_select(
            [attack_opt(555), opt(PLAY, area=HAND, index=0), opt(END)],
            context=MAIN,
            current=state(active=poke(SNIPER_WINCON, energy=1, hp=200),
                          opp_active=poke(WALL, hp=330),
                          opp_bench=[poke(BENCHIE, hp=bench_hp)],
                          hand=[BOSS]))
    p = Pilot(Strategy(roles={SNIPER_WINCON: ["win_condition"]}), deck=[1] * 60,
              general_strategy=GENERAL_STRATEGY, stats=_STATS, functions=_TAGS)
    assert "gust-for-the-ko" not in _fired(p.explain(_obs(40)).options[1])   # rider collects it free
    assert p.decide(_obs(40)) != [1]
    p2 = Pilot(Strategy(roles={SNIPER_WINCON: ["win_condition"]}), deck=[1] * 60,
               general_strategy=GENERAL_STRATEGY, stats=_STATS, functions=_TAGS)
    assert "gust-for-the-ko" in _fired(p2.explain(_obs(60)).options[1])      # out of reach: gust again


@pytest.mark.req("REQ-GUST-0015")
def test_gust_plus_spread_synergy_fires_past_the_rider_baseline():
    """ep85046350 f81: gust the 130-HP body up, the 200 main KOs it AND the 60 spread finishes the
    40-HP one — 2 prizes, vs the rider's lone 1-prize KO without the gust. The gust side counts its
    own drag-and-finish synergy (spread riders too), so the 2-prize line beats the snipe-aware
    baseline. Also proves the bench KO oracle sees the EXPENSIVE 200 attack the cheapest-attack
    summary would on other decks miss (the ADR-0052 patch finished for the bench side)."""
    obs = make_select(
        [attack_opt(555), opt(PLAY, area=HAND, index=0), opt(END)],
        context=MAIN,
        current=state(active=poke(SPREADER, energy=1, hp=200),
                      opp_active=poke(WALL, hp=330),
                      opp_bench=[poke(BENCHIE, hp=130), poke(BENCHIE, hp=40)],
                      hand=[BOSS]))
    p = Pilot(Strategy(roles={SPREADER: ["win_condition"]}), deck=[1] * 60,
              general_strategy=GENERAL_STRATEGY, stats=_STATS, functions=_TAGS)
    assert "gust-for-the-ko" in _fired(p.explain(obs).options[1])
    assert p.decide(obs) == [1]


@pytest.mark.req("REQ-GUST-0015")
def test_gust_pays_the_threat_forfeit_premium_when_the_menu_ko_removes_the_doom():
    """ep82753102 f109: the opponent's Active both DOOMS my Active (200 incoming ≥ 200 HP) and is
    KO-able on the menu — the direct KO removes the threat, while a gust benches it SAFELY to come
    back. A 2-prize gust must then beat the menu by MORE than one prize, so it stands down and the
    agent kills the threat. The same 2-prize gust over a harmless KO-able Active (no doom) fires —
    that control is `test_gust_for_the_ko_fires_to_reach_a_higher_prize_than_the_current_active`."""
    obs = make_select(
        [attack_opt(555), opt(PLAY, area=HAND, index=0), opt(END)],
        context=MAIN,
        current=state(active=poke(WINCON, energy=1, hp=200),
                      opp_active=poke(KOABLE_DOOM, hp=100, energy=1),
                      opp_bench=[poke(EX_BENCHIE, hp=60)],
                      hand=[BOSS]))
    p = _pilot()
    assert "gust-for-the-ko" not in _fired(p.explain(obs).options[1])
    assert p.decide(obs) != [1]


@pytest.mark.req("REQ-GUST-0015")
def test_starved_stall_stands_down_on_a_pointless_wall_swap():
    """ep86091435 f13: full energy famine, but the opponent's CURRENT Active is itself an energyless
    retreat-2 wall and the only stall candidate is the IDENTICAL wall — the swap changes nothing
    ('doesnt really make a difference'), so `stall-gust-over-dev-when-starved` stands down instead of
    wasting Boss's. Add a strictly TAMER wall (no forward line) to the bench and the famine stall
    fires again — the swap now denies the forward attacker its spot."""
    def _obs(bench):
        return make_select(
            [opt(PLAY, area=HAND, index=0), opt(END)], context=MAIN,
            current=state(active=poke(MY_FRAGILE, energy=0, hp=130),
                          opp_active=poke(DURA_W, energy=0, hp=130),
                          opp_bench=bench, hand=[BOSS], opp_hand_count=4))
    p = _pilot()
    same_wall = _obs([poke(DURA_W, hp=130, energy=0)])                  # wall-for-equal-wall
    assert p._board(same_wall).active_doomed is True                    # the famine premise holds
    assert "stall-gust-over-dev-when-starved" not in _fired(p.explain(same_wall).options[0])
    p2 = _pilot()
    tamer = _obs([poke(DURA_W, hp=130, energy=0), poke(STALL_TARGET, hp=200, energy=0)])
    assert "stall-gust-over-dev-when-starved" in _fired(p2.explain(tamer).options[0])


@pytest.mark.req("REQ-GUST-0015")
def test_gust_fires_on_the_equal_prize_ko_toward_the_loaded_body():
    """ep85163079 f30: the direct Active KO and the gust-KO are the SAME 1 prize, but the benched
    body carries 4 sunk Energy the KO would destroy with it (vs 1 on the Active) — the tie is not a
    tie, so `gust-for-the-loaded-equal-ko` spends Boss's on the loaded body. Strip the target's
    Energy (the ep82224509 f46 refutation shape) or shrink the swing below 2 and it stands down —
    an equal KO with nothing extra attached never burns the Supporter."""
    def _obs(bench_energy):
        return make_select(
            [attack_opt(555), opt(PLAY, area=HAND, index=0), opt(END)],
            context=MAIN,
            current=state(active=poke(WINCON, energy=1, hp=200),
                          opp_active=poke(KOABLE_ACTIVE, hp=100, energy=1),
                          opp_bench=[poke(BENCHIE, hp=60, energy=bench_energy)],
                          hand=[BOSS]))
    p = _pilot()
    loaded = _obs(4)
    assert "gust-for-the-loaded-equal-ko" in _fired(p.explain(loaded).options[1])
    assert p.decide(loaded) == [1]
    p2 = _pilot()
    assert "gust-for-the-loaded-equal-ko" not in _fired(p2.explain(_obs(0)).options[1])  # bare: f46
    p3 = _pilot()
    assert "gust-for-the-loaded-equal-ko" not in _fired(p3.explain(_obs(2)).options[1])  # swing 1


@pytest.mark.req("REQ-GUST-0015")
def test_gust_target_breaks_ties_toward_the_loaded_body():
    """SWITCH tie-break mirror of the loaded-equal play rule: two equal-prize KO-able bodies, one
    carrying 3 sunk Energy — drag up the loaded one (the KO destroys everything attached; ADR-0062's
    marginal strip pointed across the table). Sub-prize: it never overrides a real prize gap."""
    obs = make_select(
        [card_opt(BENCH, 0, player=1), card_opt(BENCH, 1, player=1)],
        context=SWITCH,
        current=state(active=poke(WINCON, energy=1, hp=200),
                      opp_bench=[poke(DEAD_END, hp=60), poke(DEAD_END, hp=60, energy=3)]))
    p = _pilot()
    opts = p.explain(obs).options
    assert opts[1].tactical > opts[0].tactical
    assert p.decide(obs) == [1]


# ── ADR-TEMP-398: denial is a LINE PRIZE, and the evolving-threat read is board-priced ────────────

@pytest.mark.req("REQ-GUST-0002")
def test_the_flat_wincon_denial_constant_is_gone_not_relocated():
    """ADR-TEMP-398 decision 2. `_gust_wincon_denial` added a flat `_WINCON_DENIAL_PRIZES` (1.5)
    scaled by γ and gated to two curated MatchupPlan roles, so it read 0 on an unrecognised opponent
    and on any wincon line no Brief had labelled. Its question — *what does this line BECOME* — is
    now answered from card facts for every board.

    Asserted structurally because the regression this guards is someone re-adding the constant
    beside the derivation, which no value test would notice."""
    from common.strategy.doctrines import doctrine_gust as dg
    assert not hasattr(Pilot, "_gust_wincon_denial")
    assert not hasattr(dg, "_WINCON_DENIAL_PRIZES")
    # Positive control on the same instrument: the siblings that were deliberately KEPT are present,
    # so this is not a module that failed to import or a getattr that always answers False.
    assert hasattr(Pilot, "_gust_matchup_priority") and hasattr(Pilot, "_gust_target_denial")
    assert hasattr(dg, "_MATCHUP_GUST_SCALE")


@pytest.mark.req("REQ-GUST-0002")
def test_the_gust_target_prices_the_LINES_prize_not_the_bodys_own():
    """The premium `_gust_wincon_denial` used to add, now derived. Riolu is a 1-prize Basic one hop
    from a 3-prize Mega ex; Ditto is a 1-prize Basic whose line goes nowhere. Both are KO-able and
    both yield exactly one prize TODAY, so nothing but the line reading can separate them.

    Hand-derived: `1 + (3 - 1) x halve(1)` = 2.0 against Ditto's flat 1.0."""
    from common.needs import line_prize_advance
    p = _pilot()
    assert p.combat.forward_line_prize(PREEVO_THREAT) == (3, 1), "Riolu -> MegaLucario, one hop"
    assert p.combat.forward_line_prize(DEAD_END) == (1, 0), "a line going nowhere"
    assert line_prize_advance(own_prize=1, max_line_prize=3, hops=1) == pytest.approx(2.0)
    assert line_prize_advance(own_prize=1, max_line_prize=1, hops=0) == pytest.approx(1.0)

    obs = make_select(
        [card_opt(BENCH, 0, player=1), card_opt(BENCH, 1, player=1)],
        context=SWITCH,
        current=state(active=poke(WINCON, energy=1, hp=200),
                      opp_bench=[poke(DEAD_END, hp=60), poke(PREEVO_THREAT, hp=60)]))
    opts = p.explain(obs).options
    assert opts[1].tactical - opts[0].tactical >= 1.0, (
        "a one-hop 3-prize line must outrank a dead end by the DERIVED premium, not a tie-break")


@pytest.mark.req("REQ-GUST-0002")
def test_the_evolving_threat_denial_sees_a_SCALING_forward_form():
    """ADR-TEMP-398 decision 5, made concrete on the shape that broke it.

    `_gust_forward_denial` used to threshold the provider's PRINTED forward index at 100. Alakazam's
    whole output is a Damage Formula scaler, so that index reads its line at **10** and the term
    scored a genuinely lethal evolving threat at exactly **0**. The board-priced
    `CombatMath.forward_threat_ceiling` sees it.

    The printed control is asserted first, so this cannot pass by the fixture simply being big."""
    p = _pilot()
    p.scaled_threat_rank = True          # armed by the runtime profile, not by `Pilot.__init__`
    printed = p.stats.forward_max_damage(SCALER_PREEVO)
    assert printed == 10, "the premise: the printed index reads this lethal line at 10"
    assert printed < 100, "...and so fell under the old threshold, scoring 0"

    p._opp_attack_context = {"atk_hand": 7}          # 10 + 20x7 = 150 on this board
    assert p.combat.forward_threat_ceiling(SCALER_PREEVO, context=p._opp_attack_context) == 150
    assert p._gust_forward_denial({"id": SCALER_PREEVO}) > 0.0, (
        "the regression this decision exists to fix: a scaling evolving threat now scores")
    # Still SUB-PRIZE, so it breaks ties among equal-prize targets and never overrides a real gap.
    assert p._gust_forward_denial({"id": SCALER_PREEVO}) < 1.0


@pytest.mark.req("REQ-GUST-0002")
def test_the_evolving_threat_denial_is_a_magnitude_not_a_threshold():
    """A line at 99 and a line at 400 both scored 0 and 0.5 under the threshold. Now the reading is
    monotone in the board-priced ceiling, so a scarier line prices higher — asserted by moving ONLY
    the scaler's variable, which leaves every card fact identical between the two readings."""
    p = _pilot()
    p.scaled_threat_rank = True          # armed by the runtime profile, not by `Pilot.__init__`
    p._opp_attack_context = {"atk_hand": 2}
    small = p._gust_forward_denial({"id": SCALER_PREEVO})
    p._opp_attack_context = {"atk_hand": 10}
    large = p._gust_forward_denial({"id": SCALER_PREEVO})
    assert 0.0 < small < large, "same card, bigger board threat, strictly bigger denial"


@pytest.mark.req("REQ-GUST-0002")
def test_the_printed_read_is_restored_exactly_when_the_lever_is_thrown():
    """`scaled_threat_rank` OFF must restore the printed threshold byte-for-byte at THIS call site
    too, which is the whole reason ADR-TEMP-398 rides Issue #213's existing lever rather than
    deleting the two constants. An incident switch that reverted two of three printed reads would be
    worse than no switch at all."""
    from common.strategy.doctrines import doctrine_gust as dg
    p = _pilot()
    p._opp_attack_context = {"atk_hand": 10}
    p.scaled_threat_rank = False
    # The scaler line reads 10 printed, under the 100 threshold -> exactly 0, as it always did.
    assert p._gust_forward_denial({"id": SCALER_PREEVO}) == 0
    # ...and the flat-damage line still trips the threshold to the flat constant.
    assert p._gust_forward_denial({"id": PREEVO_THREAT}) == dg._EVOLVING_GUST_DENIAL
    p.scaled_threat_rank = True
    assert p._gust_forward_denial({"id": SCALER_PREEVO}) > 0.0, "ON sees what OFF cannot"


@pytest.mark.req("REQ-GUST-0002")
def test_the_evolving_threat_denial_discounts_by_the_hops_to_the_ATTACKER():
    """The hop count must be the distance to the best-DAMAGE form, not the best-PRIZE one.

    `reach` is `forward_threat_ceiling` — a damage quantity about the line's biggest ATTACKER — so
    discounting it by `forward_line_prize`'s hop count asks how far away a different form is. The
    two genuinely diverge, and the direction of the error is what makes this worth a test rather
    than a comment: a line with NO prize gap reports 0 prize-hops, so a prize-hop discount would
    vanish entirely on exactly the case ADR-TEMP-398 decision 5 is justified by — *"a 1-prize Basic
    evolving into a 1-prize Stage 1 that hits hard"*.

    `SCALER_PREEVO` is that case: Abra (1 prize) -> Alakazam (1 prize), so `forward_line_prize`
    returns 0 hops while `forward_payoff_terms` returns 1. `halve(0)` is 1.0 and `halve(1)` is 0.5,
    so the bug was a clean factor of two, undiscounted."""
    p = _pilot()
    p.scaled_threat_rank = True
    p._opp_attack_context = {"atk_hand": 7}                       # 10 + 20x7 = 150

    assert p.combat.forward_line_prize(SCALER_PREEVO) == (1, 0), (
        "the premise: no prize gap, so the PRIZE hop count is 0 and would not discount at all")
    assert p.combat.forward_payoff_terms(SCALER_PREEVO)[1] == 1, (
        "...while the ATTACKER really is one hop away, which is the discount that belongs here")

    reach = p.combat.forward_threat_ceiling(SCALER_PREEVO, context=p._opp_attack_context)
    assert reach == 150
    assert p._gust_forward_denial({"id": SCALER_PREEVO}) == pytest.approx(
        (150 / 100.0) * 0.5), "one hop of discount, not zero"
