"""Opponent-Value-Equation S3a — the two-term opponent-target marginal (design:
docs/plans/opponent-value-equation-unification.md; O1 = Option B).

The Layer-2 currency, ruled: value(remove opponent body b) = prize_advance + survival_shift × phase
(ruling 1 two-term sum; ruling 5 phase-scaled by the KO-race margin). The survival term is grounded
in the S1a curve — `survival_shift` = Δ `turns_to_ko_me` from removing the body — and stays sub-prize
(the gust-marginal discipline: a bought turn breaks ties, never overrides a real prize). These are
pure primitives + a shadow, DECIDING NOTHING; the live snipe/gust/deny picks are unchanged.
"""
import types

from common import needs
from common.strategy.combat import CombatMath
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider

MY = 500
A = 501             # reaches my HP at t=1 (cheap attack, 0 energy)
B = 502             # reaches my HP at t=3 (3-cost attack)
FAST_ATK, SLOW_ATK = 511, 512


def _combat():
    stats = DictCardStatProvider({
        MY: CardStat(MY, name="Me", hp=100, minAttackCost=1, attacks=()),
        A: CardStat(A, name="Fast", hp=120, minAttackCost=1, minCostDamage=100, maxDamage=100,
                    attacks=(FAST_ATK,)),
        B: CardStat(B, name="Slow", hp=120, minAttackCost=3, minCostDamage=100, maxDamage=100,
                    attacks=(SLOW_ATK,)),
    }, attacks={FAST_ATK: AttackStat(FAST_ATK, damage=100, cost=1, energyTypes=(0,)),
                SLOW_ATK: AttackStat(SLOW_ATK, damage=100, cost=3, energyTypes=(0, 0, 0))})
    return CombatMath(stats, functions=None, transients=None)


MY_BODY = {"id": MY, "hp": 100}


def _b(cid):
    return {"id": cid, "energies": []}


# ---- phase_scale (ruling 5) ------------------------------------------------------------------
def test_phase_scale_is_bounded_and_monotonic():
    # Bounded [0,1] everywhere.
    for ra in (-10, -2, 0, 3, 10):
        for op in (0, 1, 3, 6):
            s = needs.phase_scale(race_ahead=ra, opp_prizes_remaining=op)
            assert 0.0 <= s <= 1.0
    # Being further BEHIND (more negative race_ahead) sharpens every survival turn → higher.
    assert needs.phase_scale(race_ahead=-3, opp_prizes_remaining=3) > \
           needs.phase_scale(race_ahead=0, opp_prizes_remaining=3)
    # The opponent nearer their last prize → higher stakes → higher.
    assert needs.phase_scale(race_ahead=0, opp_prizes_remaining=1) > \
           needs.phase_scale(race_ahead=0, opp_prizes_remaining=5)
    # Clamps at the extremes.
    assert needs.phase_scale(race_ahead=99, opp_prizes_remaining=6) == 0.0
    assert needs.phase_scale(race_ahead=-99, opp_prizes_remaining=1) == 1.0


# ---- opponent_target_value (ruling 1) --------------------------------------------------------
def test_two_term_value_prize_plus_capped_survival():
    # No survival shift → pure prize.
    assert needs.opponent_target_value(prize_advance=2, survival_shift=0, phase=0.7) == 2.0
    # The survival term is SUB-PRIZE (capped < 1) so it never overrides a real prize difference.
    assert needs.opponent_target_value(prize_advance=0, survival_shift=100, phase=1.0) < 1.0
    v = needs.opponent_target_value(prize_advance=1, survival_shift=4, phase=1.0)
    assert 1.0 < v < 2.0                                        # a prize + a capped survival tie-break
    # Monotonic: more turns bought (at equal phase) is worth at least as much.
    assert (needs.opponent_target_value(prize_advance=0, survival_shift=2, phase=0.5)
            >= needs.opponent_target_value(prize_advance=0, survival_shift=1, phase=0.5))


# ---- turns_to_ko_me (the S1a curve inversion) ------------------------------------------------
def test_turns_to_ko_me_and_the_survival_shift():
    c = _combat()
    # A one-shots me next turn (t=1); B needs 3 turns of energy.
    #
    # RE-DERIVED by hand for ADR-0071 decision 10, when `turns_to_ko_me` became an ACCUMULATING
    # read (`min{t : Σᵢ₌₁..ᵗ incoming(i) >= hp}`). Both numbers are unchanged, and NOT by luck:
    # my HP is 100, A pays its 1-cost attack on the first attach and deals the whole 100 at t=1,
    # while B is cost-3 off 0 Energy so it deals literally 0 at t=1 and t=2 — the running sum is
    # 0 + 0 + 100, which still first reaches 100 at t=3. Accumulation only moves a pin when some
    # earlier turn contributes non-zero damage.
    assert c.turns_to_ko_me(MY_BODY, [_b(A)]) == 1
    assert c.turns_to_ko_me(MY_BODY, [_b(B)]) == 3
    both = [_b(A), _b(B)]
    base = c.turns_to_ko_me(MY_BODY, both)                      # = 1 (A dominates)
    assert base == 1
    # Removing A buys 2 turns of survival; removing B buys none — A is the valuable removal.
    assert c.turns_to_ko_me(MY_BODY, [_b(B)]) - base == 2
    assert c.turns_to_ko_me(MY_BODY, [_b(A)]) - base == 0


# ---- the shadow (Pilot emit) -----------------------------------------------------------------
def test_opponent_target_shadow_ranks_bodies_and_decides_nothing():
    from train.tune import _build_pilot
    p = _build_pilot("mega_lucario")[0]
    p._planning = False
    obs = {"current": {"yourIndex": 0, "players": [
        {"active": [{"id": 999999, "hp": 100, "energies": []}]},
        {"active": [{"id": 678, "hp": 340, "energies": []}],
         "bench": [{"id": 677, "hp": 70, "energies": []}]},
    ]}}
    board = types.SimpleNamespace(race_ahead=-1.0, opp_prizes_remaining=3)
    sh = p._opponent_target_shadow(obs, board)
    assert sh is not None and sh["bodies"]
    assert 0.0 <= sh["phase"] <= 1.0
    for row in sh["bodies"]:
        assert {"id", "prize", "survival_shift", "value"} <= set(row)
    # mid-sim → sparse (no shadow work in rollouts)
    p._planning = True
    assert p._opponent_target_shadow(obs, board) is None
