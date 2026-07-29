"""CombatMath — the KO oracle (ADR-0052): the one closed-form home for damage/KO judgment,
constructed from the knowledge seams (Stat Provider, CardFunctions, the transient tracker)
and testable WITHOUT a Pilot. Expected values are worked examples (weakness x2, resistance
-30, the Crustle pierce), not recomputations.
"""
import pytest

from common.cards import CardFunctions
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy.combat import CombatMath
from common.strategy.damage import wr_adjust

WATER, FIRE, LIGHTNING = 3, 2, 4
STARMIE, CINDERACE, CRUSTLE, PIKA = 1031, 666, 500, 25
JETTING, NEBULA, COIN = 11, 12, 13


def _oracle(functions=None, transients=None):
    stats = DictCardStatProvider(
        {STARMIE: CardStat(STARMIE, name="Mega Starmie ex", hp=330, megaEx=True, energyType=WATER,
                           attacks=(JETTING, NEBULA), minAttackCost=1, maxDamage=210),
         CINDERACE: CardStat(CINDERACE, name="Cinderace", hp=160, energyType=FIRE, weakness=WATER),
         CRUSTLE: CardStat(CRUSTLE, name="Crustle", hp=150, energyType=6),
         PIKA: CardStat(PIKA, name="Pikachu", hp=60, energyType=LIGHTNING, resistance=WATER)},
        attacks={JETTING: AttackStat(JETTING, damage=120, cost=1),
                 NEBULA: AttackStat(NEBULA, damage=210, cost=3,
                                    ignoresWeakness=True, ignoresResistance=True, ignoresEffects=True),
                 COIN: AttackStat(COIN, damage=120, cost=1, damageMin=0, damageMax=240)})
    return CombatMath(stats, functions, transients=transients)


@pytest.mark.req("REQ-COMBAT-0001")
def test_predicted_damage_applies_weakness_and_resistance():
    o = _oracle()
    # Jetting Blow 120: x2 into the Water-weak Cinderace; -30 into the Water-resist Pikachu.
    assert o.predicted_damage(STARMIE, JETTING, {"id": CINDERACE, "hp": 160}) == 240
    assert o.predicted_damage(STARMIE, JETTING, {"id": PIKA, "hp": 60}) == 90


@pytest.mark.req("REQ-COMBAT-0001")
def test_predicted_damage_prevention_is_attack_scoped():
    # Crustle's prevent_ex_damage zeroes the plain attack from a Mega ex; Nebula's
    # ignores-effects pierces it (the repo's worked example).
    fns = CardFunctions({CRUSTLE: ["prevent_ex_damage"]})
    o = _oracle(functions=fns)
    assert o.predicted_damage(STARMIE, JETTING, {"id": CRUSTLE, "hp": 150}) == 0
    assert o.predicted_damage(STARMIE, NEBULA, {"id": CRUSTLE, "hp": 150}) == 210


@pytest.mark.req("REQ-COMBAT-0001")
def test_predicted_damage_reads_the_defenders_live_transient_shield():
    class _Grants:  # the TransientTracker seam: serial -> live grant
        def grant_for_serial(self, serial):
            return {"reduction": 30} if serial == 77 else None
    o = _oracle(transients=_Grants())
    # 120 x2 = 240, then the live -30 shield -> 210; a fresh serial takes the full 240.
    assert o.predicted_damage(STARMIE, JETTING, {"id": CINDERACE, "hp": 160, "serial": 77}) == 210
    assert o.predicted_damage(STARMIE, JETTING, {"id": CINDERACE, "hp": 160, "serial": 78}) == 240


@pytest.mark.req("REQ-COMBAT-0002")
def test_predicted_max_damage_reads_the_ceiling_and_honors_exclusions():
    o = _oracle()
    my = o.stats.get(STARMIE)
    # vs a neutral defender: Nebula 210 is the worst case; excluding it leaves Jetting 120.
    assert o.predicted_max_damage(my, {"id": CRUSTLE, "hp": 150}) == 210
    assert o.predicted_max_damage(my, {"id": CRUSTLE, "hp": 150}, exclude_attack=NEBULA) == 120


@pytest.mark.req("REQ-COMBAT-0002")
def test_predicted_max_damage_coin_attack_threatens_its_ceiling():
    stats = DictCardStatProvider(
        {STARMIE: CardStat(STARMIE, energyType=WATER, attacks=(COIN,), maxDamage=120),
         CRUSTLE: CardStat(CRUSTLE, hp=150, energyType=6)},
        attacks={COIN: AttackStat(COIN, damage=120, cost=1, damageMin=0, damageMax=240)})
    o = CombatMath(stats, None)
    # Incoming reads the worst case: "if heads +120" threatens 240, not the printed 120.
    assert o.predicted_max_damage(stats.get(STARMIE), {"id": CRUSTLE, "hp": 150}) == 240


@pytest.mark.req("REQ-COMBAT-0002")
def test_predicted_max_damage_falls_back_to_card_level_wr_when_a_record_is_missing():
    # An attacker whose attack table doesn't resolve keeps the sound card-level worst case:
    # maxDamage x W/R (a partially-known table must never SHRINK a worst-case).
    stats = DictCardStatProvider(
        {STARMIE: CardStat(STARMIE, energyType=WATER, attacks=(99,), maxDamage=210),
         CINDERACE: CardStat(CINDERACE, hp=160, energyType=FIRE, weakness=WATER)})
    o = CombatMath(stats, None)
    assert o.predicted_max_damage(stats.get(STARMIE), {"id": CINDERACE, "hp": 160}) == 420


@pytest.mark.req("REQ-COMBAT-0004")
def test_can_ko_cheapest_is_prevention_aware_and_claims_nothing_without_records():
    fns = CardFunctions({CRUSTLE: ["prevent_ex_damage"]})
    o = _oracle(functions=fns)
    my = o.stats.get(STARMIE)
    assert o.can_ko_cheapest(my, {"id": CINDERACE, "hp": 160})        # Jetting 120 x2 = 240
    assert not o.can_ko_cheapest(my, {"id": CRUSTLE, "hp": 150})      # cheapest is zeroed by the wall
    # The card-level fallback is RETIRED: no attack records -> no KO claim, ever.
    bare = CombatMath(DictCardStatProvider(
        {STARMIE: CardStat(STARMIE, energyType=WATER, attacks=(JETTING,),
                           minAttackCost=1, minCostDamage=120),
         CINDERACE: CardStat(CINDERACE, hp=160, energyType=FIRE, weakness=WATER)}), None)
    assert not bare.can_ko_cheapest(bare.stats.get(STARMIE), {"id": CINDERACE, "hp": 160})


@pytest.mark.req("REQ-COMBAT-0004")
def test_can_ko_affordable_scans_every_affordable_attack():
    fns = CardFunctions({CRUSTLE: ["prevent_ex_damage"]})
    o = _oracle(functions=fns)
    # At CCC the ignores-effects Nebula (210) lands through the wall; at 1 Energy only the
    # zeroed Jetting is affordable.
    assert o.can_ko_affordable({"id": STARMIE, "energies": [1, 1, 1]}, {"id": CRUSTLE, "hp": 150})
    assert not o.can_ko_affordable({"id": STARMIE, "energies": [1]}, {"id": CRUSTLE, "hp": 150})


@pytest.mark.req("REQ-COMBAT-0004")
def test_maxed_kos_ignores_current_energy():
    o = _oracle()
    # 'Could I KO if I loaded up?' — Nebula 210 >= 160 even with ZERO Energy attached.
    assert o.maxed_kos({"id": STARMIE, "energies": []}, {"id": CINDERACE, "hp": 160})
    assert not o.maxed_kos({"id": STARMIE, "energies": []}, {"id": CINDERACE, "hp": 211})


@pytest.mark.req("REQ-COMBAT-0004")
def test_can_damage_a_zeroed_conditional_is_no_threat():
    scaler = 14
    stats = DictCardStatProvider(
        {STARMIE: CardStat(STARMIE, energyType=WATER, attacks=(scaler,)),
         CRUSTLE: CardStat(CRUSTLE, hp=150, energyType=6)},
        attacks={scaler: AttackStat(scaler, damage=0, cost=1,
                                    scaleVar="atk_discard_energy", scalePerUnit=20)})
    o = CombatMath(stats, None)
    # Riptide-class off an empty discard computes 0 -> no threat with what they hold NOW.
    assert not o.can_damage({"id": STARMIE, "energies": [1]}, {"id": CRUSTLE, "hp": 150})


@pytest.mark.req("REQ-COMBAT-0005")
def test_bench_rider_prize_math():
    o = _oracle()
    bench = ((CINDERACE, 50), (STARMIE, 40))            # a 1-prize body and a 3-prize Mega
    assert o.snipe_ko_prizes(bench, 50) == 3            # the 50 rider finishes BOTH; max prize wins
    assert o.snipe_ko_prizes(bench, 30) == 0            # finishes nothing
    assert o.spread_ko_prizes(((CINDERACE, 30), (CINDERACE, 30)), 60) == 2   # knapsack: both


@pytest.mark.req("REQ-COMBAT-0005")
def test_bench_ko_indices_names_the_bodies_and_the_prize_read_derives_from_it():
    """Issue #199 (ADR-0079): the Deny Relevance redundancy gate needs to know WHICH benched body dies —
    *"no hammer on that specific pokemon"* — which the aggregate prize read cannot say. The bench
    Knock Out rule is therefore stated ONCE here, and `snipe_ko_prizes` is derived from it, so the
    two cannot drift (the `_build_standing` / `_affords` one-function-owns-the-fact lesson)."""
    o = _oracle()
    bench = ((CINDERACE, 50), (STARMIE, 40))
    assert o.bench_ko_indices(bench, 50) == frozenset({0, 1})
    assert o.bench_ko_indices(bench, 40) == frozenset({1})     # only the 40-HP body is in reach
    assert o.bench_ko_indices(bench, 30) == frozenset()
    assert o.bench_ko_indices(bench, 0) == frozenset()         # no reach, no claim
    # the aggregate agrees with the per-body read at every reach — that is what "derived" means
    for reach in (0, 30, 40, 50, 999):
        idx = o.bench_ko_indices(bench, reach)
        expected = max((o.prize_value({"id": bench[i][0]}) for i in idx), default=0)
        assert o.snipe_ko_prizes(bench, reach) == expected


@pytest.mark.req("REQ-COMBAT-0005")
def test_attack_type_payable_suppresses_only_provable_shortfalls():
    typed = 15
    stats = DictCardStatProvider(
        {3: CardStat(3, cardType=5, energyType=WATER)},   # the attached Water Energy resolves
        attacks={typed: AttackStat(typed, damage=100, cost=2, energyTypes=(WATER, WATER))})
    o = CombatMath(stats, None)
    target = {"id": 9, "energies": [3]}                  # one typed Water attached, needs two
    assert not o.attack_type_payable(typed, target, extra_type=0, extra_units=1)  # {C} can't fund {W}
    assert o.attack_type_payable(typed, target, wild_units=1)   # a wild attach might be the Water


@pytest.mark.req("REQ-COMBAT-0006")
def test_best_affordable_ko_value_scores_the_ko_band_and_prefers_cheap():
    from common.strategy.context import KO_SCORE
    o = _oracle()
    opp = {"id": CINDERACE, "hp": 160}
    # 1 Energy: Jetting (120 x2) KOs -> KO_SCORE + 1 prize - efficiency*1.
    v1 = o.best_affordable_ko_value(opp, STARMIE, 1)
    assert v1 == pytest.approx(KO_SCORE + 1 - 0.1)
    # 3 Energy: Nebula also KOs but costs 3 — the CHEAPER equal-prize KO keeps the best value.
    assert o.best_affordable_ko_value(opp, STARMIE, 3) == pytest.approx(KO_SCORE + 1 - 0.1)
    assert o.best_affordable_ko_value(opp, STARMIE, 0) == 0.0    # nothing affordable


@pytest.mark.req("REQ-COMBAT-0006")
def test_best_affordable_ko_value_credits_the_bench_snipe_rider():
    snipe = 16
    stats = DictCardStatProvider(
        {STARMIE: CardStat(STARMIE, energyType=WATER, attacks=(snipe,)),
         CINDERACE: CardStat(CINDERACE, hp=160, energyType=FIRE, weakness=WATER)},
        attacks={snipe: AttackStat(snipe, damage=120, cost=1, benchSnipe=50)})
    o = CombatMath(stats, None)
    opp = {"id": CINDERACE, "hp": 160}
    with_bench = o.best_affordable_ko_value(opp, STARMIE, 1, opp_bench=((CINDERACE, 60),))
    bare = o.best_affordable_ko_value(opp, STARMIE, 1)
    assert with_bench > bare                     # the rider's board value counts with a bench
    assert with_bench - bare < 1                 # …but never a full prize


@pytest.mark.req("REQ-COMBAT-0006")
def test_best_affordable_ko_value_min_bound_never_locks_a_coin():
    o = _oracle()
    stats = DictCardStatProvider(
        {STARMIE: CardStat(STARMIE, energyType=WATER, attacks=(COIN,)),
         CRUSTLE: CardStat(CRUSTLE, hp=100, energyType=6)},
        attacks={COIN: AttackStat(COIN, damage=120, cost=1, damageMin=0, damageMax=240)})
    o = CombatMath(stats, None)
    opp = {"id": CRUSTLE, "hp": 100}
    assert o.best_affordable_ko_value(opp, STARMIE, 1, bound="min") == 0.0   # floor 0: no lock
    assert o.best_affordable_ko_value(opp, STARMIE, 1, bound="exact") > 0    # printed 120 KOs


@pytest.mark.req("REQ-COMBAT-0006")
def test_best_affordable_ko_value_type_guard_and_boost_rider():
    typed = 17
    stats = DictCardStatProvider(
        {STARMIE: CardStat(STARMIE, energyType=WATER, attacks=(typed,)),
         CRUSTLE: CardStat(CRUSTLE, hp=150, energyType=6),
         3: CardStat(3, cardType=5, energyType=WATER)},
        attacks={typed: AttackStat(typed, damage=100, cost=2, energyTypes=(WATER, WATER))})
    o = CombatMath(stats, None)
    opp = {"id": CRUSTLE, "hp": 150}
    body = {"id": STARMIE, "energies": [3, 3]}   # two typed Water attached — cost payable
    # 100 < 150: no KO — but a +50 boost rider crosses it (the boost-lethal arithmetic).
    assert o.best_affordable_ko_value(opp, STARMIE, 2, body=body) == 0.0
    assert o.best_affordable_ko_value(opp, STARMIE, 2, body=body, boost_amount=50) > 0
    # Ignition-class extra ({C}x2) can't fund the {W}{W} slots: provably unpayable, suppressed.
    bare = {"id": STARMIE, "energies": []}
    assert o.best_affordable_ko_value(opp, STARMIE, 2, body=bare,
                                      extra_type=0, extra_units=2, boost_amount=50) == 0.0


@pytest.mark.req("REQ-COMBAT-0007")
def test_incoming_active_damage_reads_transient_locks_and_bonuses():
    class _Grants:
        def __init__(self, grant): self._g = grant
        def grant_for_serial(self, serial): return self._g if serial == 9 else None
    base = _oracle()
    oa = {"id": STARMIE, "energies": [1], "serial": 9}
    ma = {"id": CINDERACE, "hp": 160}
    # Unlocked worst case vs my Water-weak Cinderace: Jetting 120 x2 = 240 (beats Nebula's
    # weakness-blind 210 — Incoming reads the ceiling over ALL their attacks).
    assert base.incoming_active_damage(ma, {"id": STARMIE, "energies": [1]}) == 240
    # A self-lock grant on THEIR Active: no attack next turn -> 0 threat.
    locked = _oracle(transients=_Grants({"self_lock": True}))
    assert locked.incoming_active_damage(ma, oa) == 0
    # A same-attack lock excludes only that attack: Jetting locked -> Nebula's 210 remains.
    same = _oracle(transients=_Grants({"same_lock": JETTING}))
    assert same.incoming_active_damage(ma, oa) == 210
    # A self-bonus raises the worst hit: 240 + 30.
    bonus = _oracle(transients=_Grants({"self_bonus": 30}))
    assert bonus.incoming_active_damage(ma, oa) == 270


@pytest.mark.req("REQ-COMBAT-0007")
def test_active_doomed_sees_the_forward_evolution_threat():
    fns = CardFunctions({})
    riolu, mega_l, a_big = 333, 678, 18
    stats = DictCardStatProvider(
        {riolu: CardStat(riolu, name="Riolu", hp=60, energyType=6, maxDamage=10,
                         minAttackCost=1, attacks=()),
         mega_l: CardStat(mega_l, name="Mega Lucario ex", evolvesFrom="Riolu", energyType=6,
                          maxDamage=270, minAttackCost=2, attacks=(a_big,)),
         CINDERACE: CardStat(CINDERACE, hp=130, energyType=2)},
        attacks={a_big: AttackStat(a_big, damage=270, cost=2)})
    o = CombatMath(stats, fns)
    ma = {"id": CINDERACE, "hp": 130}
    oa = {"id": riolu, "energies": [1]}                     # 1 Energy + next attach pays the 2
    # Riolu's own attack can't KO — but the line it evolves INTO (270) dooms my 130-HP Active.
    assert o.active_doomed(ma, oa, {"handCount": 4})
    assert not o.active_doomed(ma, oa)                      # no opp dict -> no forward read


@pytest.mark.req("REQ-COMBAT-0008")
def test_turns_to_ko_is_ceil_over_best_affordable_damage():
    o = _oracle()
    # Jetting (1 Energy) 120 into neutral 300 HP -> ceil(300/120) = 3 turns; no damage -> None.
    assert o.turns_to_ko(STARMIE, 1, {"id": CRUSTLE, "hp": 300}) == 3
    assert o.turns_to_ko(STARMIE, 0, {"id": CRUSTLE, "hp": 300}) is None


@pytest.mark.req("REQ-COMBAT-0003")
def test_wr_adjust_is_the_one_card_level_wr_rule():
    atk = CardStat(1, energyType=WATER)
    weak = CardStat(2, weakness=WATER)
    resist = CardStat(3, resistance=WATER)
    assert wr_adjust(atk, weak, 120) == 240          # Weakness x2 (S&V)
    assert wr_adjust(atk, resist, 120) == 90         # Resistance flat -30, floored at 0
    assert wr_adjust(atk, resist, 20) == 0
    assert wr_adjust(None, weak, 120) == 120         # unknown attacker -> unadjusted
