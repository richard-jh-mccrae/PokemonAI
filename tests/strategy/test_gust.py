"""Gust (Boss's Orders) — the whether-to-play line (general doctrine, ADR-0022, docs/general-strategy.md).

Behaviour through the Pilot's PUBLIC interface (`decide` / `explain`): the agent plays a gust Supporter
exactly when it converts to a KO this turn that beats its best non-gust line, and holds it otherwise.
Lib-free: observations built by hand via `pilot_helpers`.
"""
import pytest

from common.cards import CardFunctions
from common.strategy.general_strategy import GENERAL_STRATEGY
from common.pilot import KO_SCORE, Pilot
from common.scouting.provider import CardStat, DictCardStatProvider
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
WEAK_ATTACKER = 905  # my Active: 10-damage attacker, can't KO a 20-HP body by attacking
ITEM_GUST = 1183   # synthetic Item gust (cardType ITEM) — doesn't cost the one Supporter slot
FIGHT_GUST = 906   # my Active: Fighting attacker (120) — exercises Resistance in gust oracle
RESIST_BENCHIE = 710  # opp benched: HP 100, RESISTS Fighting (survives 120-30=90) — a false KO
SNIPER_WINCON = 907  # my Active: win-condition whose attack ALSO snipes bench (Jetting Blow-like)
DWEB_HI = 720      # opp benched, KO-able, removal lets my snipe finish DWEB_LO (2-prize line)
DWEB_LO = 721      # opp benched, KO-able, low HP — finished by 50 snipe only if DWEB_HI gusted
A_SNIPE_G = 104    # my Active's snipe attack id (120 damage + 50 bench rider)
MY_FRAGILE = 908   # my Active: 130 HP — KO'd by opp's FORWARD hand-size evolution, not now
KADA = 911         # opp Active: weak pre-evo (30 dmg) that EVOLVES into a hand-size attacker
ALAK = 912         # hand_size_attacker KADA evolves into (Alakazam: 20 dmg/card via handSizeDamage)
STALL1 = 711       # opp benched body: energyless, retreat 1 — valid stall target (can't pay retreat)
PSYCHIC = 7        # energy type for the opp pre-evo
WATER, LIGHTNING, FIRE, FIGHTING = 3, 4, 2, 6
SUPPORTER, ITEM = 3, 1   # CardType values (cg/api.py)

_STATS = DictCardStatProvider({
    BOSS: CardStat(BOSS, hp=0, cardType=SUPPORTER),
    ITEM_GUST: CardStat(ITEM_GUST, hp=0, cardType=ITEM),
    WINCON: CardStat(WINCON, energyType=WATER, minAttackCost=1, minCostDamage=120),
    WALL: CardStat(WALL, hp=330),
    BENCHIE: CardStat(BENCHIE, hp=60),
    KOABLE_ACTIVE: CardStat(KOABLE_ACTIVE, hp=100),
    EX_BENCHIE: CardStat(EX_BENCHIE, hp=60, ex=True),
    OFF_WINCON: CardStat(OFF_WINCON, energyType=WATER, minAttackCost=1, minCostDamage=120),
    TUTOR: CardStat(TUTOR, hp=0),
    BIG_BENCHIE: CardStat(BIG_BENCHIE, hp=200),
    MEGA_WINCON: CardStat(MEGA_WINCON, energyType=WATER, weakness=LIGHTNING, megaEx=True,
                          minAttackCost=1, minCostDamage=120),
    LIVE_ATTACKER: CardStat(LIVE_ATTACKER, energyType=WATER, maxDamage=200),
    DOOM_ACTIVE: CardStat(DOOM_ACTIVE, energyType=FIRE, hp=330, maxDamage=200),
    STALL_TARGET: CardStat(STALL_TARGET, hp=200, retreatCost=2),
    PREEVO_THREAT: CardStat(PREEVO_THREAT, name="Riolu", hp=60),
    EVO_FORM: CardStat(EVO_FORM, name="MegaLucario", evolvesFrom="Riolu", maxDamage=270),
    DEAD_END: CardStat(DEAD_END, name="Ditto", hp=60),
    WEAK_ATTACKER: CardStat(WEAK_ATTACKER, energyType=WATER, minAttackCost=1, minCostDamage=10),
    FIGHT_GUST: CardStat(FIGHT_GUST, energyType=FIGHTING, minAttackCost=1, minCostDamage=120),
    RESIST_BENCHIE: CardStat(RESIST_BENCHIE, hp=100, resistance=FIGHTING),
    SNIPER_WINCON: CardStat(SNIPER_WINCON, energyType=WATER, minAttackCost=1, minCostDamage=120,
                            attacks=(A_SNIPE_G,)),
    DWEB_HI: CardStat(DWEB_HI, hp=70),
    DWEB_LO: CardStat(DWEB_LO, hp=20),
    MY_FRAGILE: CardStat(MY_FRAGILE, energyType=WATER, hp=130, minAttackCost=1, minCostDamage=50),
    KADA: CardStat(KADA, name="TKadabra", hp=80, energyType=PSYCHIC, maxDamage=30,
                   minAttackCost=1, minCostDamage=30),                  # opp Active: weak pre-evo…
    ALAK: CardStat(ALAK, name="TAlakazam", evolvesFrom="TKadabra", hp=140, minAttackCost=1,
                   handSizeDamage=20),                                  # …evolves into hand-size KO
    STALL1: CardStat(STALL1, hp=70, retreatCost=1),                     # energyless retreat-1 stall body
})
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
                      opp_active=poke(DOOM_ACTIVE, hp=330),
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
                      opp_active=poke(DOOM_ACTIVE, hp=330),
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


@pytest.mark.req("REQ-GUST-0002")
def test_gust_target_does_not_fire_on_my_own_retreat():
    """SWITCH is ALSO my own retreat (playerIndex == yourIndex) — the gust target scoring must stay
    silent on my own benched Pokémon (resolved by the owner guard), never treating a retreat as a gust."""
    obs = make_select(
        [card_opt(BENCH, 0, player=0)],
        context=SWITCH,
        current=state(active=poke(WINCON, energy=1, hp=200), bench=[poke(BENCHIE, hp=60)]))
    p = _pilot()
    assert p.explain(obs).options[0].tactical == 0   # my own bench -> no gust KO_SCORE boost


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
              general_strategy=GENERAL_STRATEGY, stats=_STATS, functions=_TAGS,
              attacks={A_SNIPE_G: 120}, attack_costs={A_SNIPE_G: 1}, bench_snipe={A_SNIPE_G: 50})
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
                      opp_active=poke(DOOM_ACTIVE, hp=330),
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
                      opp_active=poke(DOOM_ACTIVE, hp=330),
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
