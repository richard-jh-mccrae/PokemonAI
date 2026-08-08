"""Threat-Clock unification S1 — the ``incoming(t, policy)`` curve (design:
docs/plans/ADR-0078).

``CombatMath.incoming`` generalises ``reachable_incoming`` (the ADR-0064 t=1 read) to an N-turn
ENERGY clock: at future turn t the opponent has had t attach-turns, so a form is affordable under
``attached + t`` (ceiling) / ``attached + t*base_attach + burst`` (charged). The evolution reach is
already MAXIMAL at t=1 — ``forward_card_ids`` returns all descendants (existence-gated), credited
under the one-attach budget — so t moves ONLY the energy budget. That is exactly why
``incoming(t=1)`` is byte-identical to ``reachable_incoming``: the latter delegates to it.

Lib-free provider, mirroring ``test_reachable_incoming.py``.
"""
from common.strategy.combat import CombatMath
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider

MY = 1031           # Mega Starmie ex (330 HP; {L}-weak — Fighting is un-adjusted)
RIOLU = 677
MEGA_LUC = 678
GOLEM = 500         # a no-evolution Basic wielding one 2-cost colourless attack (isolates the
                    # CURRENT-form energy clock: no forward hop, no weakness)
FIGHTING = 6
COLORLESS = 0

ACC_STAB = 900      # Riolu {F}{F} 30
AURA_JAB = 982      # {F} 130
MEGA_BRAVE = 983    # {F}{F} 270
NEBULA = 210        # ●●● 210
GOLEM_ATK = 501     # {C}{C} 100


def _combat():
    stats = DictCardStatProvider({
        MY: CardStat(MY, name="Mega Starmie ex", hp=330, megaEx=True, maxDamage=210,
                     minAttackCost=1, attacks=(NEBULA,), evolvesFrom="Staryu", energyType=3),
        RIOLU: CardStat(RIOLU, synthetic=True, name='Riolu', hp=80, maxDamage=30, minAttackCost=2,
                        minCostDamage=30, attacks=(ACC_STAB,), energyType=6),
        MEGA_LUC: CardStat(MEGA_LUC, name="Mega Lucario ex", hp=340, megaEx=True, maxDamage=270,
                           minAttackCost=1, minCostDamage=130, attacks=(AURA_JAB, MEGA_BRAVE),
                           evolvesFrom="Riolu", energyType=6),
        GOLEM: CardStat(GOLEM, synthetic=True, name="Golem", hp=140, maxDamage=100, minAttackCost=2,
                        minCostDamage=100, attacks=(GOLEM_ATK,), energyType=6),
    }, attacks={
        ACC_STAB: AttackStat(ACC_STAB, damage=30, cost=2, energyTypes=(FIGHTING, FIGHTING)),
        AURA_JAB: AttackStat(AURA_JAB, damage=130, cost=1, energyTypes=(FIGHTING,)),
        MEGA_BRAVE: AttackStat(MEGA_BRAVE, damage=270, cost=2, energyTypes=(FIGHTING, FIGHTING)),
        NEBULA: AttackStat(NEBULA, damage=210, cost=3, energyTypes=(COLORLESS, COLORLESS, COLORLESS)),
        GOLEM_ATK: AttackStat(GOLEM_ATK, damage=100, cost=2, energyTypes=(COLORLESS, COLORLESS)),
    })
    return CombatMath(stats, functions=None, transients=None)


MY_BODY = {"id": MY, "hp": 270}


def _riolu(n):
    return {"id": RIOLU, "hp": 80, "energies": [FIGHTING] * n}


def _golem(n):
    return {"id": GOLEM, "hp": 140, "energies": [COLORLESS] * n}


# REQ-CURVE-0001 — incoming(t=1) is byte-identical to reachable_incoming (the latter delegates).
def test_t1_matches_reachable_incoming_across_fixtures():
    c = _combat()
    policies = [
        dict(),                                              # ceiling default
        dict(evo_min_energy=1),                              # the loss rung's stricter read
        dict(charged={"base_attach": 1, "burst_on_evo": 0}),
        dict(charged={"base_attach": 1, "burst_on_evo": 2}),
    ]
    for bodies in ([_riolu(0)], [_riolu(1)], [_golem(0)], [_riolu(1), _golem(0)]):
        for kw in policies:
            assert c.incoming(MY_BODY, bodies, 1, **kw) == c.reachable_incoming(MY_BODY, bodies, **kw)


# REQ-CURVE-0002 — the curve is monotonic non-decreasing in t (more turns never deals LESS).
def test_curve_is_monotonic_in_t():
    c = _combat()
    for bodies in ([_riolu(0)], [_golem(0)], [_riolu(1), _golem(0)]):
        for kw in (dict(), dict(charged={"base_attach": 1, "burst_on_evo": 0})):
            vals = [c.incoming(MY_BODY, bodies, t, **kw) for t in range(1, 6)]
            assert vals == sorted(vals), (bodies, kw, vals)


# REQ-CURVE-0003 — the ENERGY clock unlocks a costly CURRENT-form attack at a later turn (no evolution).
def test_energy_clock_unlocks_current_form_attack():
    c = _combat()
    # Golem: one {C}{C} 100 attack, 0 attached. Unpayable at t=1 (0+1 < cost 2), payable at t=2 → 100.
    assert c.incoming(MY_BODY, [_golem(0)], 1) == 0
    assert c.incoming(MY_BODY, [_golem(0)], 2) == 100
    ch = {"base_attach": 1, "burst_on_evo": 0}                # the charged budget crosses at the same t
    assert c.incoming(MY_BODY, [_golem(0)], 1, charged=ch) == 0
    assert c.incoming(MY_BODY, [_golem(0)], 2, charged=ch) == 100


# REQ-CURVE-0004 — under charged, the energy clock reaches the evolved TYPED nuke at t=2.
def test_energy_clock_reaches_the_evolved_nuke_charged():
    c = _combat()
    ch = {"base_attach": 1, "burst_on_evo": 0}
    # 0-energy Riolu → Mega Lucario ex. Budget 0+t: t=1 pays {F} Aura Jab 130 only; t=2 pays {F}{F}
    # Mega Brave 270. (The ceiling already credits 270 at t=1 — this is the charged clock's finer read.)
    assert c.incoming(MY_BODY, [_riolu(0)], 1, charged=ch) == 130
    assert c.incoming(MY_BODY, [_riolu(0)], 2, charged=ch) == 270


# REQ-CURVE-0005 — t clamps to >= 1 (a degenerate t never reads richer than t=1).
def test_t_clamps_to_one():
    c = _combat()
    assert c.incoming(MY_BODY, [_riolu(0)], 0) == c.incoming(MY_BODY, [_riolu(0)], 1)
    assert c.incoming(MY_BODY, [_golem(0)], -5) == c.incoming(MY_BODY, [_golem(0)], 1)
