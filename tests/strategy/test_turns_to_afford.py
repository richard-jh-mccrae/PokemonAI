"""Threat-Clock unification S1c — the ``turns_to_afford`` affordability+evolve clock (design:
docs/plans/opponent-value-equation-unification.md).

``CombatMath.turns_to_afford`` is the deny-clock's energy/evolve model, extracted next to
``incoming`` so the Threat Clock's two legs — the damage CURVE and the affordability CLOCK — share
ONE home and the one forward index. ``pilot._opp_turns_to_ready`` now DELEGATES to it
(byte-identical, pinned by test_needs_deny_resolver). "Armed" = the line's biggest-attack COST is
payable (NOT lethality — blocker 3), at the attach quota, in PARALLEL with the forward hops (the MAX
of the two legs, never the sum). Policy-parameterizable via ``attaches_per_turn`` (1 = the slow deny
read, ruling 2).
"""
from common.strategy.combat import CombatMath
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider

RIOLU = 677
MLUC = 678          # Mega Lucario ex — one hop from Riolu (rulebook Appendix 1)


def _combat():
    stats = DictCardStatProvider({
        RIOLU: CardStat(RIOLU, name="Riolu", hp=70, maxDamageCost=1, maxDamage=30, attacks=(11,)),
        MLUC: CardStat(MLUC, name="Mega Lucario ex", hp=340, megaEx=True, evolvesFrom="Riolu",
                       maxDamageCost=2, maxDamage=270, attacks=(21, 22)),
    }, attacks={11: AttackStat(11, damage=30, cost=1),
                21: AttackStat(21, damage=130, cost=1), 22: AttackStat(22, damage=270, cost=2)})
    return CombatMath(stats, functions=None, transients=None)


def _b(cid, n):
    return {"id": cid, "energies": [0] * n}


# REQ-TTR-0001 — the parallel lookahead: MAX(energy leg, forward-hop leg), matching _opp_turns_to_ready.
def test_parallel_lookahead_energy_and_evolve_legs():
    c = _combat()
    # Riolu 1 Energy: line max cost = max(1, 2) = 2, deficit 2-1 = 1; one hop to Mega Lucario ex →
    # max(ceil(1/1), 1) = 1.
    assert c.turns_to_afford(_b(RIOLU, 1)) == 1
    # Riolu 0 Energy: deficit 2, one hop → max(2, 1) = 2.
    assert c.turns_to_afford(_b(RIOLU, 0)) == 2
    # Mega Lucario ex with 2 Energy: no forward, deficit 0, 0 hops → armed NOW.
    assert c.turns_to_afford(_b(MLUC, 2)) == 0


# REQ-TTR-0002 — fail-closed None on an unknown body or no known biggest-attack cost.
def test_none_when_unknown_or_no_cost():
    c = _combat()
    assert c.turns_to_afford({"id": 424242, "energies": [0]}) is None
    assert c.turns_to_afford(None) is None


# REQ-TTR-0003 — the policy parameter: a faster attach rate shortens the ENERGY leg (rounding up).
def test_attaches_per_turn_scales_the_energy_leg():
    c = _combat()
    # Riolu 0 Energy: energy deficit 2. At 2 attaches/turn the energy leg is ceil(2/2)=1, so the
    # EVOLVE leg (1 hop) now co-dominates → 1; the slow default (1/turn) is 2.
    assert c.turns_to_afford(_b(RIOLU, 0), attaches_per_turn=2) == 1
    assert c.turns_to_afford(_b(RIOLU, 0), attaches_per_turn=1) == 2


# REQ-TTR-0004 — the Pilot deny-clock read DELEGATES to the primitive (one home; drift guard).
def test_opp_turns_to_ready_delegates_to_the_primitive():
    from train.tune import _build_pilot
    p = _build_pilot("mega_lucario")[0]
    for body in ({"id": RIOLU, "energies": [0]}, {"id": MLUC, "energies": [0, 0]},
                 {"id": 424242, "energies": []}, None):
        assert p._opp_turns_to_ready(body) == p.combat.turns_to_afford(
            body, forward_ids=p._forward_card_ids)
