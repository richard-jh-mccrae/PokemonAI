"""Attack-value refinements (ADR-0022): item 14 bench-snipe bonus and item 2 simultaneous-draw guard,
both in the Pilot's Tactical layer (`_tactical`). Lib-free: per-attackId maps are injected directly.
"""
import pytest

from common.pilot import KO_SCORE, Pilot
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy import Strategy
from pilot_helpers import ACTIVE, BENCH, HAND, attack_opt, card_opt, make_select, opt, poke, state

MY_ATK = 920        # my Active attacker (two equal-cost KO attacks, one with a bench rider)
MY_EX = 921         # my Active: a 2-prize ex (its self-KO hands opponent 2 prizes)
FIGHT_ATK = 922     # my Active: a Fighting attacker (exercises Resistance)
MY_RESISTER = 923   # my Active: HP 100, RESISTS Fighting — incoming Fighting damage reduced -30
OPP = 800           # opp Active, KO-able for 1 prize
RESISTER = 801      # opp Active: HP 100, RESISTS Fighting (survives a 120 hit: 120-30=90)
OPP_FIGHTER = 802   # opp Active: Fighting attacker hitting 120 (would KO a 100-HP non-resister)
OPP_BENCH = 700     # opp benched Pokémon — a snipe target
OPP_BENCH2 = 701    # a second opp benched Pokémon (multi-KO spread test)
EX_BENCHIE = 702    # a benched 2-prize ex (spread-placement prize-preference test)
A_PLAIN, A_SNIPE, A_RECOIL, A_FLAT, A_SPREAD = 101, 102, 110, 103, 104   # attack ids
SLOWKING = 163
COPY_BODY = 750
COPY_RULEBOX = 751
COPY_TRAINER = 752
COPY_WEAK = 753
SEEK, SUPER_PSY_BOLT, COPY_HIT, COPY_WEAK_HIT = 1201, 1202, 1203, 1204
WATER, FIGHTING = 3, 6

_CARDS = {
    MY_ATK: CardStat(MY_ATK, synthetic=True, energyType=WATER),
    MY_EX: CardStat(MY_EX, synthetic=True, energyType=WATER, ex=True, hp=200),
    FIGHT_ATK: CardStat(FIGHT_ATK, synthetic=True, energyType=FIGHTING),
    MY_RESISTER: CardStat(MY_RESISTER, synthetic=True, hp=100, resistance=FIGHTING),
    OPP: CardStat(OPP, synthetic=True, hp=100),          # 1 prize, no resistance
    RESISTER: CardStat(RESISTER, synthetic=True, hp=100, resistance=FIGHTING),
    OPP_FIGHTER: CardStat(OPP_FIGHTER, synthetic=True, energyType=FIGHTING, maxDamage=120),
    OPP_BENCH: CardStat(OPP_BENCH, synthetic=True, hp=60),
    OPP_BENCH2: CardStat(OPP_BENCH2, hp=60),
    EX_BENCHIE: CardStat(EX_BENCHIE, synthetic=True, hp=200, ex=True),   # 2-prize benched ex
    SLOWKING: CardStat(SLOWKING, name="Slowking", hp=120, attacks=(SEEK, SUPER_PSY_BOLT)),
    COPY_BODY: CardStat(COPY_BODY, hp=120, attacks=(COPY_HIT,)),
    COPY_RULEBOX: CardStat(COPY_RULEBOX, synthetic=True, hp=220, ex=True, attacks=(COPY_HIT,)),
    COPY_TRAINER: CardStat(COPY_TRAINER, synthetic=True, name="Trainer", cardType=3),
    COPY_WEAK: CardStat(COPY_WEAK, synthetic=True, hp=120, attacks=(COPY_WEAK_HIT,)),
}


def _pilot(attacks=None, **kw):
    """`attacks` = {attackId: AttackStat} — the per-test attack-record table, carried by the provider."""
    return Pilot(Strategy(), deck=[1] * 60,
                 stats=DictCardStatProvider(_CARDS, attacks=attacks or {}), **kw)


def _gpilot(**kw):
    """Pilot WITH the general strategy loaded — so baseline Hypotheses (e.g. `place-counter-to-convert`)
    actually fire (the tactical-only `_pilot` above doesn't load them)."""
    from common.strategy.general_strategy import GENERAL_STRATEGY
    return Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                 stats=DictCardStatProvider(_CARDS), **kw)


# --- Issue #289: known top-of-deck copy attack --------------------------------------------------

def _seek_obs():
    return make_select([attack_opt(SEEK), opt(14)],
                       current=state(active=poke(SLOWKING, energy=1),
                                     opp_active=poke(OPP, hp=100)))


@pytest.mark.req("REQ-KNOWN-TOP-0001")
def test_seek_inspiration_is_not_live_without_a_known_top_card():
    p = _pilot({SEEK: AttackStat(SEEK, damage=0, cost=1),
                COPY_HIT: AttackStat(COPY_HIT, damage=200, cost=4)},
               copy_top_value=True)

    decision = p.explain(_seek_obs())

    assert decision.options[0].tactical < 0
    assert p.decide(_seek_obs()) == [1]


@pytest.mark.req("REQ-KNOWN-TOP-0001")
def test_slowkings_printed_second_attack_is_not_treated_as_seek_inspiration():
    p = _pilot({SEEK: AttackStat(SEEK, damage=0, cost=1),
                SUPER_PSY_BOLT: AttackStat(SUPER_PSY_BOLT, damage=120, cost=3)},
               copy_top_value=True)
    obs = make_select([attack_opt(SUPER_PSY_BOLT), opt(14)],
                      current=state(active=poke(SLOWKING, energy=3),
                                    opp_active=poke(OPP, hp=100)))

    assert p.explain(obs).options[0].tactical >= KO_SCORE
    assert p.decide(obs) == [0]


@pytest.mark.req("REQ-KNOWN-TOP-0001")
def test_seek_inspiration_prices_a_known_non_rulebox_pokemon_attack():
    p = _pilot({SEEK: AttackStat(SEEK, damage=0, cost=1),
                COPY_HIT: AttackStat(COPY_HIT, damage=200, cost=4)},
               copy_top_value=True)
    p._known_top = ((77, COPY_BODY),)

    decision = p.explain(_seek_obs())

    assert decision.options[0].tactical >= KO_SCORE + 1
    assert p.decide(_seek_obs()) == [0]


@pytest.mark.req("REQ-KNOWN-TOP-0001")
def test_seek_inspiration_known_rulebox_top_whiffs():
    p = _pilot({SEEK: AttackStat(SEEK, damage=0, cost=1),
                COPY_HIT: AttackStat(COPY_HIT, damage=200, cost=4)},
               copy_top_value=True)
    p._known_top = ((77, COPY_RULEBOX),)

    decision = p.explain(_seek_obs())

    assert decision.options[0].tactical < 0
    assert p.decide(_seek_obs()) == [1]


@pytest.mark.req("REQ-KNOWN-TOP-0001")
def test_seek_inspiration_does_not_charge_the_copied_attacks_energy_cost():
    p = _pilot({SEEK: AttackStat(SEEK, damage=0, cost=1),
                COPY_HIT: AttackStat(COPY_HIT, damage=200, cost=99)},
               copy_top_value=True)
    p._known_top = ((77, COPY_BODY),)

    decision = p.explain(_seek_obs())

    assert decision.options[0].tactical >= KO_SCORE + 1


@pytest.mark.req("REQ-KNOWN-TOP-0001")
def test_face_up_move_to_my_deck_creates_known_top_for_the_same_decision():
    p = _pilot({SEEK: AttackStat(SEEK, damage=0, cost=1),
                COPY_HIT: AttackStat(COPY_HIT, damage=200, cost=4)},
               copy_top_value=True)
    obs = _seek_obs()
    obs["logs"] = [{"type": 6, "playerIndex": 0, "cardId": COPY_BODY, "serial": 77,
                    "fromArea": 2, "toArea": 1}]

    assert p.decide(obs) == [0]


@pytest.mark.req("REQ-KNOWN-TOP-0001")
def test_known_top_draw_mismatch_clears_the_whole_belief():
    p = _pilot({SEEK: AttackStat(SEEK, damage=0, cost=1),
                COPY_HIT: AttackStat(COPY_HIT, damage=200, cost=4)},
               copy_top_value=True)
    p._known_top = ((77, COPY_BODY),)
    obs = _seek_obs()
    obs["logs"] = [{"type": 4, "playerIndex": 0, "cardId": COPY_BODY, "serial": 78}]

    assert p.decide(obs) == [1]


@pytest.mark.req("REQ-KNOWN-TOP-0001")
def test_known_top_matching_draw_advances_to_the_tail():
    p = _pilot({SEEK: AttackStat(SEEK, damage=0, cost=1),
                COPY_HIT: AttackStat(COPY_HIT, damage=200, cost=4),
                COPY_WEAK_HIT: AttackStat(COPY_WEAK_HIT, damage=20, cost=1)},
               copy_top_value=True)
    p._known_top = ((76, COPY_WEAK), (77, COPY_BODY))
    obs = _seek_obs()
    obs["logs"] = [{"type": 4, "playerIndex": 0, "cardId": COPY_WEAK, "serial": 76}]

    assert p.decide(obs) == [0]


@pytest.mark.req("REQ-KNOWN-TOP-0001")
def test_shuffle_clears_known_top():
    p = _pilot({SEEK: AttackStat(SEEK, damage=0, cost=1),
                COPY_HIT: AttackStat(COPY_HIT, damage=200, cost=4)},
               copy_top_value=True)
    p._known_top = ((77, COPY_BODY),)
    obs = _seek_obs()
    obs["logs"] = [{"type": 0, "playerIndex": 0}]

    assert p.decide(obs) == [1]


@pytest.mark.req("REQ-KNOWN-TOP-0001")
def test_face_down_deck_movement_clears_known_top():
    p = _pilot({SEEK: AttackStat(SEEK, damage=0, cost=1),
                COPY_HIT: AttackStat(COPY_HIT, damage=200, cost=4)},
               copy_top_value=True)
    p._known_top = ((77, COPY_BODY),)
    obs = _seek_obs()
    obs["logs"] = [{"type": 7, "playerIndex": 0, "fromArea": 2, "toArea": 1}]

    assert p.decide(obs) == [1]


@pytest.mark.req("REQ-KNOWN-TOP-0001")
def test_unknown_deck_movement_clears_known_top():
    p = _pilot({SEEK: AttackStat(SEEK, damage=0, cost=1),
                COPY_HIT: AttackStat(COPY_HIT, damage=200, cost=4)},
               copy_top_value=True)
    p._known_top = ((77, COPY_BODY),)
    obs = _seek_obs()
    obs["logs"] = [{"type": 99, "playerIndex": 0, "fromArea": 1, "toArea": 2}]

    assert p.decide(obs) == [1]


@pytest.mark.req("REQ-KNOWN-TOP-0001")
def test_top_deck_select_prefers_the_best_copy_attack_body():
    p = _pilot({SEEK: AttackStat(SEEK, damage=0, cost=1),
                COPY_HIT: AttackStat(COPY_HIT, damage=200, cost=4),
                COPY_WEAK_HIT: AttackStat(COPY_WEAK_HIT, damage=20, cost=1)},
               copy_top_value=True)
    obs = make_select([card_opt(HAND, 0), card_opt(HAND, 1)], context=9,
                      current=state(active=poke(SLOWKING, energy=1),
                                    hand=[COPY_WEAK, COPY_BODY],
                                    opp_active=poke(OPP, hp=100)))

    assert p.decide(obs) == [1]


@pytest.mark.req("REQ-KNOWN-TOP-0001")
def test_top_deck_select_demotes_a_known_whiff_card():
    p = _pilot({SEEK: AttackStat(SEEK, damage=0, cost=1),
                COPY_HIT: AttackStat(COPY_HIT, damage=200, cost=4)},
               copy_top_value=True)
    obs = make_select([card_opt(HAND, 0), card_opt(HAND, 1)], context=9,
                      current=state(active=poke(SLOWKING, energy=1),
                                    hand=[COPY_TRAINER, COPY_BODY],
                                    opp_active=poke(OPP, hp=100)))

    assert p.decide(obs) == [1]


@pytest.mark.req("REQ-KNOWN-TOP-0001")
def test_top_deck_select_is_silent_without_active_seek_inspiration():
    p = _pilot({A_PLAIN: AttackStat(A_PLAIN, damage=20, cost=1),
                COPY_HIT: AttackStat(COPY_HIT, damage=200, cost=4)},
               copy_top_value=True)
    obs = make_select([card_opt(HAND, 0), card_opt(HAND, 1)], context=9,
                      current=state(active=poke(MY_ATK, energy=1),
                                    hand=[COPY_WEAK, COPY_BODY],
                                    opp_active=poke(OPP, hp=100)))

    opts = p.explain(obs).options
    assert opts[0].tactical == opts[1].tactical == 0


# --- ADR-0022 item 14: prefer the equal-cost KO that also snipes a benched target -----------------

@pytest.mark.req("REQ-GUST-0007")
def test_equal_cost_ko_prefers_the_attack_with_a_bench_snipe():
    """Two equal-cost KO attacks; one ALSO snipes a benched Pokémon → it scores higher (best total
    board value), so the agent picks the sniping attack."""
    p = _pilot({A_PLAIN: AttackStat(A_PLAIN, damage=120, cost=1),
                A_SNIPE: AttackStat(A_SNIPE, damage=120, cost=1, benchSnipe=50)})
    obs = make_select([attack_opt(A_PLAIN), attack_opt(A_SNIPE)],
                      current=state(active=poke(MY_ATK, energy=1),
                                    opp_active=poke(OPP, hp=100),
                                    opp_bench=[poke(OPP_BENCH, hp=60)]))
    opts = p.explain(obs).options
    assert opts[1].tactical > opts[0].tactical    # sniper edges plain KO
    assert opts[0].tactical >= KO_SCORE           # both still knockouts
    assert p.decide(obs) == [1]


@pytest.mark.req("REQ-GUST-0007")
def test_bench_snipe_bonus_is_silent_with_no_benched_target():
    """No benched target → the rider hits nothing, so it adds no value and the two KO attacks tie."""
    p = _pilot({A_PLAIN: AttackStat(A_PLAIN, damage=120, cost=1),
                A_SNIPE: AttackStat(A_SNIPE, damage=120, cost=1, benchSnipe=50)})
    obs = make_select([attack_opt(A_PLAIN), attack_opt(A_SNIPE)],
                      current=state(active=poke(MY_ATK, energy=1),
                                    opp_active=poke(OPP, hp=100), opp_bench=[]))
    opts = p.explain(obs).options
    assert opts[1].tactical == opts[0].tactical   # nothing to snipe -> no bonus


@pytest.mark.req("REQ-GUST-0007")
def test_bench_snipe_chip_bonus_never_overrides_a_prize():
    """A snipe that only CHIPS (rider < the benched HP) is a sub-prize tiebreak: even a big (120) chip
    on a 1-prize KO stays BELOW a 2-prize KO's floor, so it can never override real prize value."""
    p = _pilot({A_SNIPE: AttackStat(A_SNIPE, damage=120, cost=1, benchSnipe=120)})
    obs = make_select([attack_opt(A_SNIPE)],
                      current=state(active=poke(MY_ATK, energy=1),
                                    opp_active=poke(OPP, hp=100),        # 1-prize Active
                                    opp_bench=[poke(OPP_BENCH, hp=200)]))  # 200 > 120 rider -> chip, not KO
    val = p.explain(obs).options[0].tactical       # KO_SCORE + 1 prize + capped chip bonus
    assert KO_SCORE + 1 <= val < KO_SCORE + 2      # above the 1-prize floor, below a 2-prize KO


@pytest.mark.req("REQ-GUST-0007")
def test_snipe_ko_of_a_bench_pokemon_banks_a_full_prize():
    """A bench-snipe rider that KNOCKS OUT a benched Pokémon banks a PRIZE — it is a knockout, scored
    KO_SCORE-class — so it beats a bigger chip that KOs nothing (ep82749168 f62: Jetting Blow 120 + 50
    snipe finishes a 20-HP Dreepy, over a 210 Nebula Beam that only chips an un-KO-able 320-HP Active)."""
    p = _pilot({A_PLAIN: AttackStat(A_PLAIN, damage=210, cost=3),
                A_SNIPE: AttackStat(A_SNIPE, damage=120, cost=1, benchSnipe=50)})
    obs = make_select([attack_opt(A_PLAIN), attack_opt(A_SNIPE)],
                      current=state(active=poke(MY_ATK, energy=3),
                                    opp_active=poke(OPP, hp=320),         # neither attack KOs the Active
                                    opp_bench=[poke(OPP_BENCH, hp=20)]))  # snipe 50 >= 20 -> a KO = a prize
    opts = p.explain(obs).options
    assert opts[1].tactical >= KO_SCORE           # snipe-KO is a knockout (prize), not a chip
    assert opts[1].tactical > opts[0].tactical    # beats the 210 chip that KOs nothing
    assert p.decide(obs) == [1]


@pytest.mark.req("REQ-GUST-0007")
def test_snipe_that_only_chips_a_survivor_is_not_a_ko():
    """Control: the rider does NOT reach the benched HP (50 < 60) → a chip, not a knockout → with no
    KO of the Active either, the attack stays a plain chip (well below KO_SCORE)."""
    p = _pilot({A_SNIPE: AttackStat(A_SNIPE, damage=120, cost=1, benchSnipe=50)})
    obs = make_select([attack_opt(A_SNIPE)],
                      current=state(active=poke(MY_ATK, energy=1),
                                    opp_active=poke(OPP, hp=320),         # not a KO of the Active
                                    opp_bench=[poke(OPP_BENCH, hp=60)]))  # 60 > 50 rider -> chip only
    assert p.explain(obs).options[0].tactical < KO_SCORE


# --- Phantom Dive distributable bench SPREAD: the 6 counters can DIRECTLY KO softened bench mons ---

@pytest.mark.req("REQ-GEN-0050")
def test_spread_kos_a_softened_bench_pokemon_banks_a_prize():
    """A distributable bench spread (Phantom Dive benchSpread=60) that KOs a softened benched Pokémon
    (remaining HP <= spread) banks a PRIZE this turn — scored KO_SCORE-class — even when the Active
    survives (200-to-Active here is only a chip vs a 320-HP wall)."""
    p = _pilot({A_SPREAD: AttackStat(A_SPREAD, damage=200, cost=2, benchSpread=60)})
    obs = make_select([attack_opt(A_SPREAD)],
                      current=state(active=poke(MY_ATK, energy=2),
                                    opp_active=poke(OPP, hp=320),         # 200 doesn't KO the Active
                                    opp_bench=[poke(OPP_BENCH, hp=60)]))  # spread 60 >= 60 -> a KO = a prize
    assert p.explain(obs).options[0].tactical >= KO_SCORE


@pytest.mark.req("REQ-GEN-0050")
def test_spread_can_ko_multiple_bench_mons_within_its_total():
    """The spread is DISTRIBUTABLE: 60 splits to KO two 30-remaining bench mons (30+30 <= 60) → two
    prizes, worth more than KOing a single one."""
    p = _pilot({A_SPREAD: AttackStat(A_SPREAD, damage=200, cost=2, benchSpread=60)})
    two = make_select([attack_opt(A_SPREAD)],
                      current=state(active=poke(MY_ATK, energy=2), opp_active=poke(OPP, hp=320),
                                    opp_bench=[poke(OPP_BENCH, hp=30), poke(OPP_BENCH2, hp=30)]))
    one = make_select([attack_opt(A_SPREAD)],
                      current=state(active=poke(MY_ATK, energy=2), opp_active=poke(OPP, hp=320),
                                    opp_bench=[poke(OPP_BENCH, hp=30)]))
    assert p.explain(two).options[0].tactical > p.explain(one).options[0].tactical >= KO_SCORE


@pytest.mark.req("REQ-GEN-0050")
def test_spread_that_only_chips_is_a_subprize_bonus_not_a_ko():
    """A spread too small to KO any bench mon (all HP > 60) is a sub-prize chip tiebreak — with no KO of
    the Active either, the attack stays below KO_SCORE (never invents a prize)."""
    p = _pilot({A_SPREAD: AttackStat(A_SPREAD, damage=200, cost=2, benchSpread=60)})
    obs = make_select([attack_opt(A_SPREAD)],
                      current=state(active=poke(MY_ATK, energy=2), opp_active=poke(OPP, hp=320),
                                    opp_bench=[poke(OPP_BENCH, hp=200)]))  # 200 > 60 -> chip, no bench KO
    assert p.explain(obs).options[0].tactical < KO_SCORE


@pytest.mark.req("REQ-GEN-0050")
def test_spread_silent_with_no_bench():
    """No benched target → the spread hits nothing, adds no value."""
    p = _pilot({A_PLAIN: AttackStat(A_PLAIN, damage=200, cost=2),
                A_SPREAD: AttackStat(A_SPREAD, damage=200, cost=2, benchSpread=60)})
    obs = make_select([attack_opt(A_PLAIN), attack_opt(A_SPREAD)],
                      current=state(active=poke(MY_ATK, energy=2), opp_active=poke(OPP, hp=320),
                                    opp_bench=[]))
    opts = p.explain(obs).options
    assert opts[1].tactical == opts[0].tactical   # nothing to spread onto -> no bonus


# --- Phantom Dive PLACEMENT: distribute counters at DAMAGE_COUNTER_ANY (ctx 14), knapsack-optimal ---
DAMAGE_COUNTER_ANY = 14

@pytest.mark.req("REQ-GEN-0051")
def test_counter_placement_finishes_a_ko_able_target():
    """At a spread-placement select (one counter per select, 6-counter budget), put the counter on an
    opponent mon a counter can KO within the budget — not on an un-KO-able wall."""
    p = _gpilot()
    obs = make_select([card_opt(BENCH, 0, player=1), card_opt(BENCH, 1, player=1)],
                      context=DAMAGE_COUNTER_ANY, remain_counters=6,
                      current=state(opp_active=poke(OPP, hp=320),
                                    opp_bench=[poke(OPP_BENCH, hp=10), poke(OPP_BENCH2, hp=200)]))
    assert p.decide(obs) == [0]   # 10-HP mon is KO-able within the 60 budget; the 200 wall isn't


@pytest.mark.req("REQ-GEN-0051")
def test_counter_placement_prefers_the_higher_prize_ko_set():
    """Budget 50 (5 counters) can KO EITHER the 2-prize ex@50 OR the 1-prize@10 (not both: 60>50). The
    knapsack picks the higher-prize KO set → place on the ex to finish it, not the cheap mon."""
    p = _gpilot()
    obs = make_select([card_opt(BENCH, 0, player=1), card_opt(BENCH, 1, player=1)],
                      context=DAMAGE_COUNTER_ANY, remain_counters=5,
                      current=state(opp_active=poke(OPP, hp=320),
                                    opp_bench=[poke(EX_BENCHIE, hp=50), poke(OPP_BENCH, hp=10)]))
    assert p.decide(obs) == [0]   # the 2-prize ex (KO set worth 2) over the 1-prize@10 (worth 1)


@pytest.mark.req("REQ-GEN-0051")
def test_counter_placement_preloads_lowest_hp_when_no_ko_possible():
    """No target is KO-able within the budget (both HP > the 20 budget) → pre-load the LOWEST-HP mon
    (concentrate toward a future KO)."""
    p = _gpilot()
    obs = make_select([card_opt(BENCH, 0, player=1), card_opt(BENCH, 1, player=1)],
                      context=DAMAGE_COUNTER_ANY, remain_counters=2,
                      current=state(opp_active=poke(OPP, hp=320),
                                    opp_bench=[poke(OPP_BENCH, hp=90), poke(OPP_BENCH2, hp=40)]))
    assert p.decide(obs) == [1]   # 40-HP < 90-HP -> concentrate on the weaker


@pytest.mark.req("REQ-GEN-0051")
def test_counter_placement_silent_off_context():
    """Off a DAMAGE_COUNTER_ANY select, the placement rule is silent (a plain END option is unaffected)."""
    p = _pilot()
    obs = make_select([opt(14)], context=0,
                      current=state(active=poke(MY_ATK, energy=1), opp_active=poke(OPP, hp=100)))
    board = p._board(obs, obs["select"])
    assert board.best_counter_slot is None


# --- Munkidori Adrena-Brain counter-move: TARGET (ctx13 add-to-opp) / SOURCE (ctx16 remove-ours) / AMOUNT --
DAMAGE_COUNTER = 13          # ADD (target = opponent)
REMOVE_DAMAGE_COUNTER = 16   # REMOVE (source = ours; removing = a heal)
REMOVE_COUNT = 40            # how many
NUMBER = 0                   # OptionType.NUMBER

@pytest.mark.req("REQ-GEN-0052")
def test_move_counter_target_finishes_the_best_opp():
    """At the counter-move TARGET select (ctx 13, add to opponent), place on the opp mon a move-of-<=3
    (30) can KO — reuses the spread placement (budget falls back to 30 for a counter-mover)."""
    p = _gpilot()
    obs = make_select([card_opt(BENCH, 0, player=1), card_opt(BENCH, 1, player=1)],
                      context=DAMAGE_COUNTER,
                      current=state(opp_active=poke(OPP, hp=320),
                                    opp_bench=[poke(OPP_BENCH2, hp=200), poke(OPP_BENCH, hp=30)]))
    assert p.decide(obs) == [1]   # index 1 (30-HP) is finishable within a 3-counter move; the 200 isn't


@pytest.mark.req("REQ-GEN-0052")
def test_move_counter_source_heals_the_most_damaged_body():
    """At the SOURCE select (ctx 16, remove from ours), pull counters off OUR most-damaged body (the
    biggest heal / the win-con line body carrying residual chip)."""
    p = _gpilot()
    obs = make_select([card_opt(ACTIVE, 0, player=0), card_opt(BENCH, 0, player=0)],
                      context=REMOVE_DAMAGE_COUNTER,
                      current=state(active=poke(OPP_BENCH, hp=300, max_hp=320),      # 20 damage
                                    bench=[poke(OPP_BENCH2, hp=40, max_hp=90)]))     # 50 damage (more)
    assert p.decide(obs) == [1]   # heal the benched body (50 dmg) over the active (20 dmg)


@pytest.mark.req("REQ-GEN-0052")
def test_move_counter_amount_is_max():
    """At the AMOUNT select (ctx 40), move the MOST counters offered (max offense + max heal)."""
    p = _gpilot()
    obs = make_select([opt(NUMBER, number=1), opt(NUMBER, number=2), opt(NUMBER, number=3)],
                      context=REMOVE_COUNT, current=state(active=poke(MY_ATK, energy=1)))
    assert p.decide(obs) == [2]   # the "3" option


# --- ADR-0022 item 2: a game-winning KO whose recoil double-KOs is a DRAW, not a win --------------

@pytest.mark.req("REQ-GUST-0008")
def test_lethal_with_recoil_double_ko_is_not_scored_as_a_win():
    """My 2-prize ex's attack KOs the opponent's Active for my LAST prize — but its forced recoil also
    KOs my ex, handing the opponent their LAST 2 prizes simultaneously. That is a DRAW, not a win, so the
    attack must NOT be scored KO_SCORE-class."""
    p = _pilot({A_RECOIL: AttackStat(A_RECOIL, damage=300, cost=2, recoil=200)})
    obs = make_select([attack_opt(A_RECOIL)],
                      current=state(active=poke(MY_EX, hp=200),
                                    opp_active=poke(OPP, hp=100),
                                    prizes=1, opp_prizes=2))
    assert p.explain(obs).options[0].tactical < KO_SCORE


@pytest.mark.req("REQ-GUST-0008")
def test_lethal_without_recoil_is_a_real_win():
    """Control: same winning KO but the attack has NO recoil → my ex survives → a real win (KO_SCORE)."""
    p = _pilot({A_RECOIL: AttackStat(A_RECOIL, damage=300, cost=2)})   # no recoil
    obs = make_select([attack_opt(A_RECOIL)],
                      current=state(active=poke(MY_EX, hp=200),
                                    opp_active=poke(OPP, hp=100),
                                    prizes=1, opp_prizes=2))
    assert p.explain(obs).options[0].tactical >= KO_SCORE


@pytest.mark.req("REQ-GUST-0008")
def test_recoil_double_ko_is_a_win_when_it_does_not_empty_the_opponent():
    """Control: the recoil self-KO hands the opponent only 2 of their 3 remaining prizes — they don't
    reach 0, so I win on my last prize before they finish. Not simultaneous → a real win."""
    p = _pilot({A_RECOIL: AttackStat(A_RECOIL, damage=300, cost=2, recoil=200)})
    obs = make_select([attack_opt(A_RECOIL)],
                      current=state(active=poke(MY_EX, hp=200),
                                    opp_active=poke(OPP, hp=100),
                                    prizes=1, opp_prizes=3))
    assert p.explain(obs).options[0].tactical >= KO_SCORE


# --- Resistance: a resisted "lethal" survives (flat -30 after Weakness, simulator-verified) --------

@pytest.mark.req("REQ-GUST-0009")
def test_resistance_turns_a_false_ko_into_a_chip():
    """A 120 Fighting attack would KO a 100-HP Active at face value, but the defender RESISTS Fighting
    (120 - 30 = 90 < 100) → it is NOT a knockout. Without the resistance subtraction this is a false KO
    (and gusting it would be a gift)."""
    p = _pilot({A_FLAT: AttackStat(A_FLAT, damage=120, cost=1)})
    obs = make_select([attack_opt(A_FLAT)],
                      current=state(active=poke(FIGHT_ATK, energy=1), opp_active=poke(RESISTER, hp=100)))
    assert p.explain(obs).options[0].tactical < KO_SCORE       # 90 < 100 → chip, not a KO


@pytest.mark.req("REQ-GUST-0009")
def test_no_resistance_same_attack_is_a_real_ko():
    """Control: the same 120 attack on a 100-HP Active with NO resistance to my type is a real KO."""
    p = _pilot({A_FLAT: AttackStat(A_FLAT, damage=120, cost=1)})
    obs = make_select([attack_opt(A_FLAT)],
                      current=state(active=poke(FIGHT_ATK, energy=1), opp_active=poke(OPP, hp=100)))
    assert p.explain(obs).options[0].tactical >= KO_SCORE


# --- Resistance is applied in BOTH directions: incoming (opponent attacking me) too ---------------

@pytest.mark.req("REQ-GUST-0009")
def test_incoming_damage_applies_my_active_resistance():
    """Defensive direction: the opponent's Active hits for 120 — enough to KO my 100-HP Active at face
    value — but my Active RESISTS Fighting, so incoming is 120 - 30 = 90 < 100. I am NOT doomed. The
    same Weakness/Resistance check must apply to incoming damage, not just my own attacks."""
    p = _pilot()
    obs = make_select([opt(14)],   # an END option — just need a valid board
                      current=state(active=poke(MY_RESISTER, hp=100), opp_active=poke(OPP_FIGHTER, hp=200)))
    board = p._board(obs)
    assert board.incoming_active_damage == 90    # 120 reduced by my -30 resistance
    assert board.active_doomed is False          # 90 < 100 — resistance saves my Active


@pytest.mark.req("REQ-GUST-0009")
def test_incoming_damage_doomed_without_resistance():
    """Control: a non-resisting 100-HP Active takes the full 120 → doomed (resistance is what changed it)."""
    p = _pilot()
    obs = make_select([opt(14)],
                      current=state(active=poke(MY_ATK, hp=100), opp_active=poke(OPP_FIGHTER, hp=200)))
    board = p._board(obs)
    assert board.incoming_active_damage == 120
    assert board.active_doomed is True
