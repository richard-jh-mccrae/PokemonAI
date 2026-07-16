"""ADR-0064 — the reachable-Incoming primitive (`CombatMath.reachable_incoming`).

The worked example, verified card facts (docs/plans/2ply-opponent-survival-grill-spec.md):
my Mega Starmie ex at 270 HP remaining ({L}-weak, so Fighting damage is un-adjusted); the opponent's
benched Riolu is a single hop from Mega Lucario ex (Aura Jab {F} 130 / Mega Brave {F}{F} 270). The
old `_incoming_worst` sees only Riolu's own 30 and reports "survives" even when the bench Riolu holds
the Energy to evolve-and-swing for an exact 270 KO. This exercises the primitive in isolation, both
energy policies, on a lib-free synthetic provider.
"""
from common.strategy.combat import CombatMath
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider

MY = 1031           # Mega Starmie ex (330 HP; {L}-weak — Fighting is un-adjusted)
RIOLU = 677
MEGA_LUC = 678
FIGHTING = 6
COLORLESS = 0

ACC_STAB = 900      # Riolu's own attack: {F}{F} 30 (verified cost 2, dmg 30)
AURA_JAB = 982      # {F} 130
MEGA_BRAVE = 983    # {F}{F} 270
NEBULA = 210        # ●●● 210 (colorless-costed nuke — the burst-payable shape)


def _combat(*, ignition_burst=0):
    stats = DictCardStatProvider({
        MY: CardStat(MY, name="Mega Starmie ex", hp=330, megaEx=True, maxDamage=210,
                     minAttackCost=1, attacks=(NEBULA,), evolvesFrom="Staryu", energyType=3),
        RIOLU: CardStat(RIOLU, name="Riolu", hp=80, maxDamage=30, minAttackCost=2,
                        minCostDamage=30, attacks=(ACC_STAB,), energyType=6),
        MEGA_LUC: CardStat(MEGA_LUC, name="Mega Lucario ex", hp=340, megaEx=True, maxDamage=270,
                           minAttackCost=1, minCostDamage=130, attacks=(AURA_JAB, MEGA_BRAVE),
                           evolvesFrom="Riolu", energyType=6),
    }, attacks={
        ACC_STAB: AttackStat(ACC_STAB, damage=30, cost=2, energyTypes=(FIGHTING, FIGHTING)),
        AURA_JAB: AttackStat(AURA_JAB, damage=130, cost=1, energyTypes=(FIGHTING,)),
        MEGA_BRAVE: AttackStat(MEGA_BRAVE, damage=270, cost=2, energyTypes=(FIGHTING, FIGHTING)),
        NEBULA: AttackStat(NEBULA, damage=210, cost=3, energyTypes=(COLORLESS, COLORLESS, COLORLESS)),
    })
    return CombatMath(stats, functions=None, transients=None)


def _riolu(n_fighting):
    return {"id": RIOLU, "hp": 80, "energies": [FIGHTING] * n_fighting}


MY_BODY = {"id": MY, "hp": 270}


# ---- ceiling policy (worst-case; the unconditional threat read) --------------------------------

def test_ceiling_sees_the_evolved_nuke_off_a_one_energy_bench_riolu():
    # Variant 1: bench Riolu with 1 {F}. Evolve → Mega Lucario ex, one attach → {F}{F} → Mega Brave 270.
    assert _combat().reachable_incoming(MY_BODY, [_riolu(1)]) == 270


def test_ceiling_is_pessimistic_even_off_a_zero_energy_riolu():
    # Ceiling does NOT charge the big attack: cheapest (Aura Jab, cost 1) is payable at 0+1 energy,
    # so the form is credited its max (270) — the worst-case read that must never under-prepare.
    assert _combat().reachable_incoming(MY_BODY, [_riolu(0)]) == 270


def test_old_style_current_form_only_when_no_forward_exists():
    # A body with no evolution contributes only its own attack (Riolu's 30 — the historical read).
    stats = DictCardStatProvider({
        MY: CardStat(MY, name="Mega Starmie ex", hp=330, maxDamage=210, minAttackCost=1,
                     attacks=(NEBULA,), energyType=3),
        RIOLU: CardStat(RIOLU, name="Riolu", hp=80, maxDamage=30, minAttackCost=2,
                        minCostDamage=30, attacks=(ACC_STAB,), energyType=6),
    }, attacks={ACC_STAB: AttackStat(ACC_STAB, damage=30, cost=2, energyTypes=(FIGHTING, FIGHTING)),
                NEBULA: AttackStat(NEBULA, damage=210, cost=3)})
    assert CombatMath(stats, None, None).reachable_incoming(MY_BODY, [_riolu(1)]) == 30


# ---- charged policy (matched-Read; typed-cost affordability) -----------------------------------

def test_charged_variant1_bench_riolu_one_energy_reaches_mega_brave():
    # attached 1 {F} + 1 wild attach = 2 → pays {F}{F} → 270. The exact-KO threat, defend.
    got = _combat().reachable_incoming(MY_BODY, [_riolu(1)], charged={"base_attach": 1, "burst": 0})
    assert got == 270


def test_charged_variant2_bench_riolu_zero_energy_only_reaches_aura_jab():
    # attached 0 + 1 wild attach = 1 → pays {F} (Aura Jab 130) but NOT {F}{F} → 130 < 270 → survives, greedy.
    got = _combat().reachable_incoming(MY_BODY, [_riolu(0)], charged={"base_attach": 1, "burst": 0})
    assert got == 130


def test_charged_colorless_burst_pays_a_colorless_nuke_but_never_a_typed_cost():
    # A colorless-burst allowance (Ignition {C}{C}{C}) pays Nebula's ●●● from 0 attached (0+1+3 ≥ 3),
    # but can NEVER pay Mega Brave's typed {F}{F} — the planner_6858-safe typed/colorless split.
    stats = DictCardStatProvider({
        MY: CardStat(MY, name="Mega Starmie ex", hp=330, maxDamage=270, minAttackCost=1,
                     attacks=(MEGA_BRAVE, NEBULA), energyType=3),
    }, attacks={
        MEGA_BRAVE: AttackStat(MEGA_BRAVE, damage=270, cost=2, energyTypes=(FIGHTING, FIGHTING)),
        NEBULA: AttackStat(NEBULA, damage=210, cost=3, energyTypes=(COLORLESS, COLORLESS, COLORLESS)),
    })
    c = CombatMath(stats, None, None)
    body0 = {"id": MY, "hp": 999, "energies": []}      # 0 attached
    my = {"id": MY, "hp": 999}
    # burst 3 → Nebula (210) payable, Mega Brave still not (typed, needs 2, only 1 wild attach)
    assert c.reachable_incoming(my, [body0], charged={"base_attach": 1, "burst": 3}) == 210


def test_charged_returns_zero_when_body_cannot_afford_anything():
    stats = DictCardStatProvider({
        MEGA_LUC: CardStat(MEGA_LUC, name="Mega Lucario ex", hp=340, maxDamage=270, minAttackCost=1,
                           minCostDamage=130, attacks=(MEGA_BRAVE,), energyType=6),
    }, attacks={MEGA_BRAVE: AttackStat(MEGA_BRAVE, damage=270, cost=2, energyTypes=(FIGHTING, FIGHTING))})
    c = CombatMath(stats, None, None)
    lucario0 = {"id": MEGA_LUC, "hp": 340, "energies": []}    # 0 attached, only a 2-cost attack
    assert c.reachable_incoming(MY_BODY, [lucario0], charged={"base_attach": 1, "burst": 0}) == 0
