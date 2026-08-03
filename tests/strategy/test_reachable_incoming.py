"""ADR-0064 — the reachable-Incoming primitive (`CombatMath.reachable_incoming`).

The worked example, verified card facts (docs/plans/2ply-opponent-survival-grill-spec.md):
my Mega Starmie ex at 270 HP remaining ({L}-weak, so Fighting damage is un-adjusted); the opponent's
benched Riolu is a single hop from Mega Lucario ex (Aura Jab {F} 130 / Mega Brave {F}{F} 270). The
old `_incoming_worst` sees only Riolu's own 30 and reports "survives" even when the bench Riolu holds
the Energy to evolve-and-swing for an exact 270 KO. This exercises the primitive in isolation, both
energy policies, on a lib-free provider.
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
        RIOLU: CardStat(RIOLU, synthetic=True, name='Riolu', hp=80, maxDamage=30, minAttackCost=2,
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


def test_evo_min_energy_skips_the_forward_hop_of_a_bare_pre_evo():
    # evo_min_energy=1 (the loss rung's stricter read): a 0-Energy Riolu can't fund its own 2-cost
    # attack and its forward hop is skipped, so it contributes NOTHING — not a credible evolving
    # threat. (Under the default evo_min_energy=0 the ceiling would instead credit the evolved 270.)
    assert _combat().reachable_incoming(MY_BODY, [_riolu(0)], evo_min_energy=1) == 0
    assert _combat().reachable_incoming(MY_BODY, [_riolu(0)]) == 270          # default still pessimistic
    # a 1-Energy Riolu still counts (it is being powered toward the evolved attack) → 270.
    assert _combat().reachable_incoming(MY_BODY, [_riolu(1)], evo_min_energy=1) == 270


def test_old_style_current_form_only_when_no_forward_exists():
    # A body with no evolution contributes only its own attack (Riolu's 30 — the historical read).
    stats = DictCardStatProvider({
        MY: CardStat(MY, name="Mega Starmie ex", hp=330, maxDamage=210, minAttackCost=1,
                     attacks=(NEBULA,), energyType=3),
        RIOLU: CardStat(RIOLU, synthetic=True, name='Riolu', hp=80, maxDamage=30, minAttackCost=2,
                        minCostDamage=30, attacks=(ACC_STAB,), energyType=6),
    }, attacks={ACC_STAB: AttackStat(ACC_STAB, damage=30, cost=2, energyTypes=(FIGHTING, FIGHTING)),
                NEBULA: AttackStat(NEBULA, damage=210, cost=3)})
    assert CombatMath(stats, None, None).reachable_incoming(MY_BODY, [_riolu(1)]) == 30


# ---- charged policy (matched-Read; typed-cost affordability) -----------------------------------

def test_charged_variant1_bench_riolu_one_energy_reaches_mega_brave():
    # attached 1 {F} + 1 wild attach = 2 → pays {F}{F} → 270. The exact-KO threat, defend.
    got = _combat().reachable_incoming(MY_BODY, [_riolu(1)], charged={"base_attach": 1, "burst_on_evo": 0})
    assert got == 270


def test_charged_variant2_bench_riolu_zero_energy_only_reaches_aura_jab():
    # attached 0 + 1 wild attach = 1 → pays {F} (Aura Jab 130) but NOT {F}{F} → 130 < 270 → survives, greedy.
    # Lucario runs no colourless-burst energy, so burst_on_evo stays 0 and the typed {F}{F} is out of reach.
    got = _combat().reachable_incoming(MY_BODY, [_riolu(0)], charged={"base_attach": 1, "burst_on_evo": 0})
    assert got == 130


def test_charged_colorless_burst_pays_a_colorless_nuke_but_never_a_typed_cost():
    # A colorless-burst allowance (Ignition {C}{C}{C} on an Evolution) pays Nebula's ●●● from 0
    # attached (0 + 1 base + 2 burst ≥ 3), but can NEVER pay Mega Brave's typed {F}{F} — the
    # planner_6858-safe typed/colorless split. Burst applies because Mega Starmie ex is an Evolution.
    stats = DictCardStatProvider({
        MY: CardStat(MY, synthetic=True, name='Mega Starmie ex', hp=330, maxDamage=270, minAttackCost=1,
                     attacks=(MEGA_BRAVE, NEBULA), evolvesFrom="Staryu", energyType=3),
    }, attacks={
        MEGA_BRAVE: AttackStat(MEGA_BRAVE, damage=270, cost=2, energyTypes=(FIGHTING, FIGHTING)),
        NEBULA: AttackStat(NEBULA, damage=210, cost=3, energyTypes=(COLORLESS, COLORLESS, COLORLESS)),
    })
    c = CombatMath(stats, None, None)
    body0 = {"id": MY, "hp": 999, "energies": []}      # 0 attached
    my = {"id": MY, "hp": 999}
    # burst_on_evo 2 → Nebula (210) payable, Mega Brave still not (typed, needs 2, only 1 wild attach)
    assert c.reachable_incoming(my, [body0], charged={"base_attach": 1, "burst_on_evo": 2}) == 210


def test_charged_burst_does_not_apply_to_a_basic_form():
    # Ignition provides only {C} on a Basic, so a Basic body gets NO burst — a colorless nuke it can't
    # otherwise reach stays out of reach (guards the evolution-gate on the burst).
    stats = DictCardStatProvider({
        RIOLU: CardStat(RIOLU, synthetic=True, name='Riolu', hp=80, maxDamage=210, minAttackCost=3,
                        attacks=(NEBULA,), energyType=6),   # a Basic wielding a 3-colorless nuke
    }, attacks={NEBULA: AttackStat(NEBULA, damage=210, cost=3,
                                   energyTypes=(COLORLESS, COLORLESS, COLORLESS))})
    c = CombatMath(stats, None, None)
    basic0 = {"id": RIOLU, "hp": 80, "energies": []}
    my = {"id": MY, "hp": 999}
    # 0 attached + 1 base + 0 burst (Basic) = 1 < 3 → unreachable
    assert c.reachable_incoming(my, [basic0], charged={"base_attach": 1, "burst_on_evo": 2}) == 0


def test_charged_returns_zero_when_body_cannot_afford_anything():
    stats = DictCardStatProvider({
        MEGA_LUC: CardStat(MEGA_LUC, name="Mega Lucario ex", hp=340, maxDamage=270, minAttackCost=1,
                           minCostDamage=130, attacks=(MEGA_BRAVE,), energyType=6),
    }, attacks={MEGA_BRAVE: AttackStat(MEGA_BRAVE, damage=270, cost=2, energyTypes=(FIGHTING, FIGHTING))})
    c = CombatMath(stats, None, None)
    lucario0 = {"id": MEGA_LUC, "hp": 340, "energies": []}    # 0 attached, only a 2-cost attack
    assert c.reachable_incoming(MY_BODY, [lucario0], charged={"base_attach": 1, "burst_on_evo": 0}) == 0


# ---- the BENCH branch: area-at-damage-time (ADR-0070 §9) ---------------------------------------
#
# An attack's printed damage hits the ACTIVE. A benched body is reachable only by the snipe/spread
# RIDERS, which ignore Weakness/Resistance (ADR-0022) — and not at all if it is Tera (rules.md §185).
# Without this branch every benched pre-evolution reads as doomed, which would make the evolve
# decider OVER-evolve. ``my_benched`` is the area the body occupies WHEN THE DAMAGE LANDS, declared
# by the caller: the lethal tiers ask about bodies benched now but Active when the opponent replies.

DRAKLOAK = 120          # 90 HP, no Tera
DRAGAPULT = 121         # Tera: no attack damage while Benched
SNIPER = 700
SNIPE_ATK, SPREAD_ATK = 901, 902


def _bench_combat(*, both_riders=False, second_attack=False):
    attacks = {SNIPE_ATK: AttackStat(SNIPE_ATK, damage=270, cost=1, energyTypes=(FIGHTING,),
                                     benchSnipe=30, benchSpread=60 if both_riders else 0)}
    aids = (SNIPE_ATK,)
    if second_attack:
        attacks[SPREAD_ATK] = AttackStat(SPREAD_ATK, damage=200, cost=3,
                                         energyTypes=(FIGHTING, FIGHTING, FIGHTING), benchSpread=60)
        aids = (SNIPE_ATK, SPREAD_ATK)
    stats = DictCardStatProvider({
        DRAKLOAK: CardStat(DRAKLOAK, synthetic=True, name='Drakloak', hp=90, maxDamage=70, minAttackCost=2,
                           attacks=(), evolvesFrom="Dreepy", energyType=8),
        DRAGAPULT: CardStat(DRAGAPULT, synthetic=True, name='Dragapult ex', hp=320, ex=True, tera=True,
                            maxDamage=200, minAttackCost=1, attacks=(), evolvesFrom="Drakloak",
                            energyType=8),
        SNIPER: CardStat(SNIPER, synthetic=True, name="Sniper", hp=200, maxDamage=270, minAttackCost=1,
                         attacks=aids, energyType=6),
    }, attacks=attacks)
    return CombatMath(stats, functions=None, transients=None)


def _sniper(n=1):
    return {"id": SNIPER, "hp": 200, "energies": [FIGHTING] * n}


def test_benched_body_takes_only_the_rider_never_the_active_damage():
    c, me = _bench_combat(), {"id": DRAKLOAK, "hp": 90}
    # Declared ACTIVE (the default): the printed 270 lands.
    assert c.reachable_incoming(me, [_sniper()]) == 270
    # Declared BENCHED: only the snipe rider reaches it.
    assert c.reachable_incoming(me, [_sniper()], my_benched=True) == 30


def test_benched_tera_body_takes_nothing():
    c, me = _bench_combat(), {"id": DRAGAPULT, "hp": 320}
    assert c.reachable_incoming(me, [_sniper()], my_benched=True) == 0
    # ...but a Tera body in the ACTIVE spot is an ordinary target.
    assert c.reachable_incoming(me, [_sniper()]) == 270


def test_bench_riders_are_additive_on_one_body():
    # One attack carrying BOTH riders can put both on a single benched body — the worst case, and the
    # additive convention `objectives.py` already uses for a bench pool.
    me = {"id": DRAKLOAK, "hp": 90}
    assert _bench_combat(both_riders=True).reachable_incoming(me, [_sniper()], my_benched=True) == 90
    assert _bench_combat().reachable_incoming(me, [_sniper()], my_benched=True) == 30


def test_bench_read_counts_only_riders_the_attacker_can_afford():
    # Under the CHARGED policy an unaffordable attack lands no rider, exactly as it lands no damage.
    c, me = _bench_combat(second_attack=True), {"id": DRAKLOAK, "hp": 90}
    charged = {"base_attach": 1, "burst_on_evo": 0}
    # 0 attached + 1 wild = 1 -> only the 1-cost SNIPE_ATK is payable, so its 30 is the read; the
    # bigger 60-point spread rider sits behind a 3-cost attack and does not count.
    assert c.reachable_incoming(me, [_sniper(0)], my_benched=True, charged=charged) == 30
    # 2 attached + 1 wild = 3 -> the spread attack comes into reach and dominates.
    assert c.reachable_incoming(me, [_sniper(2)], my_benched=True, charged=charged) == 60


def test_turns_to_ko_me_honours_the_bench_branch():
    # The KO-clock is the survival half of the two clocks (ADR-0070 §6), read at the body's AREA:
    # printed damage lands on the Active, so the benched read sees only the riders and the clock
    # runs far slower there.
    #
    # RE-DERIVED for ADR-0071 decision 4, which made the read ACCUMULATE on BOTH areas. The old
    # expectation here was 9 (`max_t + 1`, "survives the horizon") and it encoded the one-swing
    # semantics this issue overturned: damage counters PERSIST, so a 30-point snipe fells a 90 HP
    # benched Drakloak in exactly 3 turns (30 + 30 + 30), not never. CONTEXT.md's Threat Clock
    # already specified "accumulating over turns when one hit doesn't KO"; the code was the outlier.
    c, me = _bench_combat(), {"id": DRAKLOAK, "hp": 90}
    assert c.turns_to_ko_me(me, [_sniper()]) == 1
    assert c.turns_to_ko_me(me, [_sniper()], my_benched=True) == 3      # 90 HP / 30 per turn


def test_default_is_active_so_an_undeclared_caller_stays_pessimistic():
    # Fail direction: the survival family must OVER-count their threat, never under-count it. A
    # caller that does not declare the area gets the Active read — the conservative answer — so the
    # bench branch is strictly opt-in and cannot silently grant immunity.
    c = _bench_combat()
    assert c.reachable_incoming({"id": DRAGAPULT, "hp": 320}, [_sniper()]) == 270
