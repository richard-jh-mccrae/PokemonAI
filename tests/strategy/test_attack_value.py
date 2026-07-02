"""Attack-value refinements (ADR-0022): the #14 bench-snipe bonus and the #2 simultaneous-draw guard,
both in the Pilot's Tactical layer (`_tactical`). Lib-free: per-attackId maps are injected directly.
"""
import pytest

from common.pilot import KO_SCORE, Pilot
from common.scouting.provider import CardStat, DictCardStatProvider
from common.strategy import Strategy
from pilot_helpers import attack_opt, make_select, opt, poke, state

MY_ATK = 920        # my Active attacker (two equal-cost KO attacks, one with a bench rider)
MY_EX = 921         # my Active: a 2-prize ex (its self-KO hands the opponent 2 prizes)
FIGHT_ATK = 922     # my Active: a Fighting attacker (to exercise Resistance)
MY_RESISTER = 923   # my Active: HP 100, RESISTS Fighting — incoming Fighting damage is reduced -30
OPP = 800           # opponent's Active, KO-able for 1 prize
RESISTER = 801      # opponent's Active: HP 100, RESISTS Fighting (survives a 120 hit: 120-30=90)
OPP_FIGHTER = 802   # opponent's Active: a Fighting attacker hitting 120 (would KO a 100-HP non-resister)
OPP_BENCH = 700     # an opponent benched Pokémon — a snipe target
A_PLAIN, A_SNIPE, A_RECOIL, A_FLAT = 101, 102, 110, 103   # attack ids
WATER, FIGHTING = 3, 6

_STATS = DictCardStatProvider({
    MY_ATK: CardStat(MY_ATK, energyType=WATER),
    MY_EX: CardStat(MY_EX, energyType=WATER, ex=True, hp=200),
    FIGHT_ATK: CardStat(FIGHT_ATK, energyType=FIGHTING),
    MY_RESISTER: CardStat(MY_RESISTER, hp=100, resistance=FIGHTING),
    OPP: CardStat(OPP, hp=100),          # 1 prize, no resistance
    RESISTER: CardStat(RESISTER, hp=100, resistance=FIGHTING),
    OPP_FIGHTER: CardStat(OPP_FIGHTER, energyType=FIGHTING, maxDamage=120),
    OPP_BENCH: CardStat(OPP_BENCH, hp=60),
})


def _pilot(**kw):
    return Pilot(Strategy(), deck=[1] * 60, stats=_STATS, **kw)


# --- #14 bench-snipe bonus: prefer the equal-cost KO that also snipes a benched target -------------

@pytest.mark.req("REQ-GUST-0007")
def test_equal_cost_ko_prefers_the_attack_with_a_bench_snipe():
    """Two equal-cost KO attacks; one ALSO snipes a benched Pokémon → it scores higher (best total
    board value), so the agent picks the sniping attack."""
    p = _pilot(attacks={A_PLAIN: 120, A_SNIPE: 120}, attack_costs={A_PLAIN: 1, A_SNIPE: 1},
               bench_snipe={A_SNIPE: 50})
    obs = make_select([attack_opt(A_PLAIN), attack_opt(A_SNIPE)],
                      current=state(active=poke(MY_ATK, energy=1),
                                    opp_active=poke(OPP, hp=100),
                                    opp_bench=[poke(OPP_BENCH, hp=60)]))
    opts = p.explain(obs).options
    assert opts[1].tactical > opts[0].tactical    # the sniper edges the plain KO
    assert opts[0].tactical >= KO_SCORE           # both still knockouts
    assert p.decide(obs) == [1]


@pytest.mark.req("REQ-GUST-0007")
def test_bench_snipe_bonus_is_silent_with_no_benched_target():
    """No benched target → the rider hits nothing, so it adds no value and the two KO attacks tie."""
    p = _pilot(attacks={A_PLAIN: 120, A_SNIPE: 120}, attack_costs={A_PLAIN: 1, A_SNIPE: 1},
               bench_snipe={A_SNIPE: 50})
    obs = make_select([attack_opt(A_PLAIN), attack_opt(A_SNIPE)],
                      current=state(active=poke(MY_ATK, energy=1),
                                    opp_active=poke(OPP, hp=100), opp_bench=[]))
    opts = p.explain(obs).options
    assert opts[1].tactical == opts[0].tactical   # nothing to snipe → no bonus


@pytest.mark.req("REQ-GUST-0007")
def test_bench_snipe_chip_bonus_never_overrides_a_prize():
    """A snipe that only CHIPS (rider < the benched HP) is a sub-prize tiebreak: even a big (120) chip
    on a 1-prize KO stays BELOW a 2-prize KO's floor, so it can never override real prize value."""
    p = _pilot(attacks={A_SNIPE: 120}, attack_costs={A_SNIPE: 1}, bench_snipe={A_SNIPE: 120})
    obs = make_select([attack_opt(A_SNIPE)],
                      current=state(active=poke(MY_ATK, energy=1),
                                    opp_active=poke(OPP, hp=100),        # 1-prize Active
                                    opp_bench=[poke(OPP_BENCH, hp=200)]))  # 200 > 120 rider → chip, not a KO
    val = p.explain(obs).options[0].tactical       # KO_SCORE + 1 prize + capped chip bonus
    assert KO_SCORE + 1 <= val < KO_SCORE + 2      # above the 1-prize floor, below a 2-prize KO


@pytest.mark.req("REQ-GUST-0007")
def test_snipe_ko_of_a_bench_pokemon_banks_a_full_prize():
    """A bench-snipe rider that KNOCKS OUT a benched Pokémon banks a PRIZE — it is a knockout, scored
    KO_SCORE-class — so it beats a bigger chip that KOs nothing (ep82749168 f62: Jetting Blow 120 + 50
    snipe finishes a 20-HP Dreepy, over a 210 Nebula Beam that only chips an un-KO-able 320-HP Active)."""
    p = _pilot(attacks={A_PLAIN: 210, A_SNIPE: 120}, attack_costs={A_PLAIN: 3, A_SNIPE: 1},
               bench_snipe={A_SNIPE: 50})
    obs = make_select([attack_opt(A_PLAIN), attack_opt(A_SNIPE)],
                      current=state(active=poke(MY_ATK, energy=3),
                                    opp_active=poke(OPP, hp=320),         # neither attack KOs the Active
                                    opp_bench=[poke(OPP_BENCH, hp=20)]))  # snipe 50 >= 20 → a KO = a prize
    opts = p.explain(obs).options
    assert opts[1].tactical >= KO_SCORE           # the snipe-KO is a knockout (a prize), not a chip
    assert opts[1].tactical > opts[0].tactical    # and it beats the 210 chip that KOs nothing
    assert p.decide(obs) == [1]


@pytest.mark.req("REQ-GUST-0007")
def test_snipe_that_only_chips_a_survivor_is_not_a_ko():
    """Control: the rider does NOT reach the benched HP (50 < 60) → a chip, not a knockout → with no
    KO of the Active either, the attack stays a plain chip (well below KO_SCORE)."""
    p = _pilot(attacks={A_SNIPE: 120}, attack_costs={A_SNIPE: 1}, bench_snipe={A_SNIPE: 50})
    obs = make_select([attack_opt(A_SNIPE)],
                      current=state(active=poke(MY_ATK, energy=1),
                                    opp_active=poke(OPP, hp=320),         # not a KO of the Active
                                    opp_bench=[poke(OPP_BENCH, hp=60)]))  # 60 > 50 rider → chip only
    assert p.explain(obs).options[0].tactical < KO_SCORE


# --- #2 simultaneous-draw guard: a game-winning KO whose recoil double-KOs is a DRAW, not a win ----

@pytest.mark.req("REQ-GUST-0008")
def test_lethal_with_recoil_double_ko_is_not_scored_as_a_win():
    """My 2-prize ex's attack KOs the opponent's Active for my LAST prize — but its forced recoil also
    KOs my ex, handing the opponent their LAST 2 prizes simultaneously. That is a DRAW, not a win, so the
    attack must NOT be scored KO_SCORE-class."""
    p = _pilot(attacks={A_RECOIL: 300}, attack_costs={A_RECOIL: 2}, recoil={A_RECOIL: 200})
    obs = make_select([attack_opt(A_RECOIL)],
                      current=state(active=poke(MY_EX, hp=200),
                                    opp_active=poke(OPP, hp=100),
                                    prizes=1, opp_prizes=2))
    assert p.explain(obs).options[0].tactical < KO_SCORE


@pytest.mark.req("REQ-GUST-0008")
def test_lethal_without_recoil_is_a_real_win():
    """Control: same winning KO but the attack has NO recoil → my ex survives → a real win (KO_SCORE)."""
    p = _pilot(attacks={A_RECOIL: 300}, attack_costs={A_RECOIL: 2})   # no recoil map
    obs = make_select([attack_opt(A_RECOIL)],
                      current=state(active=poke(MY_EX, hp=200),
                                    opp_active=poke(OPP, hp=100),
                                    prizes=1, opp_prizes=2))
    assert p.explain(obs).options[0].tactical >= KO_SCORE


@pytest.mark.req("REQ-GUST-0008")
def test_recoil_double_ko_is_a_win_when_it_does_not_empty_the_opponent():
    """Control: the recoil self-KO hands the opponent only 2 of their 3 remaining prizes — they don't
    reach 0, so I win on my last prize before they finish. Not simultaneous → a real win."""
    p = _pilot(attacks={A_RECOIL: 300}, attack_costs={A_RECOIL: 2}, recoil={A_RECOIL: 200})
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
    p = _pilot(attacks={A_FLAT: 120}, attack_costs={A_FLAT: 1})
    obs = make_select([attack_opt(A_FLAT)],
                      current=state(active=poke(FIGHT_ATK, energy=1), opp_active=poke(RESISTER, hp=100)))
    assert p.explain(obs).options[0].tactical < KO_SCORE       # 90 < 100 → chip, not a KO


@pytest.mark.req("REQ-GUST-0009")
def test_no_resistance_same_attack_is_a_real_ko():
    """Control: the same 120 attack on a 100-HP Active with NO resistance to my type is a real KO."""
    p = _pilot(attacks={A_FLAT: 120}, attack_costs={A_FLAT: 1})
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
    obs = make_select([opt(14)],   # an END option — we only need a valid board
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
