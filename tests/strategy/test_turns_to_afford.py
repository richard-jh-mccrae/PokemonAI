"""Threat-Clock unification S1c — the ``turns_to_afford`` affordability+evolve clock (design:
docs/plans/opponent-value-equation-unification.md).

``CombatMath.turns_to_afford`` is the deny-clock's energy/evolve model, extracted next to
``incoming`` so the Threat Clock's two legs — the damage CURVE and the affordability CLOCK — share
ONE home and the one forward index. "Armed" = the line's biggest-attack COST is payable (NOT
lethality — blocker 3), at the attach quota, in PARALLEL with the forward hops (the MAX of the two
legs, never the sum). Policy-parameterizable via ``attaches_per_turn`` (1 = the slow deny read,
ruling 2).

**POC-T1 (Issue #260)** moved the Pilot's delegate off the raw oracle onto the SNAPSHOT
(``theirs.turns_to_afford``), and landed **Issue #204**: the clock now credits a
``discard_energy_recur`` line's own discard reload at the ``self_arming`` scope — Effect-Clause
quantified, so it distinguishes Assemble Alloy (an Ability firing on the evolve hop, reloading the
evolved body) from Aura Jab (an attack reloading the BENCH, never the attacker).
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


# REQ-TTR-0004 — the Pilot deny-clock read DELEGATES to the SNAPSHOT's route (one home; drift
# guard). POC-T1 (Issue #260) moved the delegate off the raw oracle onto `theirs.turns_to_afford`,
# which is where the forward index, the discard and the energy policy already live — so the Pilot no
# longer assembles any of them by hand.
def test_opp_turns_to_ready_delegates_to_the_snapshot_route():
    from train.tune import _build_pilot
    p = _build_pilot("mega_lucario")[0]
    obs = {"current": {"yourIndex": 0, "players": [
        {"active": [{"id": 999999, "hp": 100, "energies": []}]},
        {"active": [{"id": MLUC, "hp": 340, "energies": []}], "bench": []},
    ]}}
    model = p._snapshot(obs)
    for body in ({"id": RIOLU, "energies": [0]}, {"id": MLUC, "energies": [0, 0]},
                 {"id": 424242, "energies": []}, None):
        assert p._opp_turns_to_ready(body) == model.theirs.turns_to_afford(body)
    # …and WITHOUT a snapshot the read makes no claim, which is the same fail-closed answer an
    # unknown stat gives: the caller emits no deny slot rather than one graded off a guess.
    p._state_model = None
    assert p._opp_turns_to_ready({"id": RIOLU, "energies": [0]}) is None


# REQ-TTR-0005 (Issue #204) — the clock credits a `discard_energy_recur` line's own DISCARD reload.
# Archaludon ex's Assemble Alloy attaches up to 2 Basic {M} from the discard on evolving (verified,
# data/EN_Card_Data.csv), so with {M} sitting in their discard its Metal Defender {M}{M}{M} 220 is
# ONE turn away, not two — the shipped clock's one-manual-attach assumption is not conservative
# here, it is wrong.
def _recur_model(pre_energy=0, discard=2):
    """A Duraludon → Archaludon ex line with {M} sitting in their discard.

    The clock is asked about the PRE-EVOLUTION, which is the position Issue #204 names: Assemble
    Alloy fires as Duraludon evolves, so the reload lands on the very hop the clock is counting."""
    from common.cards import CardFunctions
    from common.effects import CardEffects
    from common.state_model import StateModel
    DURA, ARCH, METAL, METAL_ENERGY = 189, 190, 8, 71
    stats = DictCardStatProvider({
        DURA: CardStat(DURA, name="Duraludon", hp=110, maxDamageCost=1, maxDamage=30,
                       attacks=(30,), energyType=METAL),
        ARCH: CardStat(ARCH, name="Archaludon ex", hp=280, evolvesFrom="Duraludon",
                       maxDamageCost=3, maxDamage=220, attacks=(31,), energyType=METAL),
        METAL_ENERGY: CardStat(METAL_ENERGY, name="Basic {M} Energy", energyType=METAL,
                               cardType=5),
    }, attacks={30: AttackStat(30, damage=30, cost=1, energyTypes=(METAL,)),
                31: AttackStat(31, damage=220, cost=3, energyTypes=(METAL, METAL, METAL))})
    combat = CombatMath(stats, functions=CardFunctions({ARCH: ["discard_energy_recur"]}),
                        transients=None, effects=CardEffects.load())
    body = {"id": DURA, "energies": [METAL_ENERGY] * pre_energy}
    obs = {"current": {"yourIndex": 0, "players": [
        {"active": []},
        {"active": [body], "bench": [],
         "discard": [{"id": METAL_ENERGY}] * discard},
    ]}}
    return StateModel.build(obs, combat=combat), body


def test_the_clock_credits_an_on_evolve_discard_reload():
    # Duraludon on 1 {M}: the line's biggest attack is Metal Defender {M}{M}{M}, so the bare clock
    # owes 2 more attaches → 2 turns (the hop is 1, and the legs run in PARALLEL).
    model, body = _recur_model(pre_energy=1)
    assert model.theirs.turns_to_afford(body, fuelled=False) == 2
    # Assemble Alloy attaches up to 2 Basic {M} from the discard AS the evolution is played, and the
    # evolved body is itself {M}, so both land here: 1 + 2 = 3 → armed on the hop turn.
    assert model.theirs.turns_to_afford(body) == 1
    # An empty discard has nothing to reload — the credit is a read of a real zone, not an allowance.
    dry, dry_body = _recur_model(pre_energy=1, discard=0)
    assert dry.theirs.turns_to_afford(dry_body) == 2


def test_the_clock_refuses_an_on_attack_bench_only_reload():
    """Mega Lucario ex's Aura Jab is an ATTACK that reloads the BENCH, never the attacker (verified,
    data/EN_Card_Data.csv). Crediting it toward arming that same body would be circular — it must
    already be armed to attack — so the `self_arming` scope reads 0 where the fail-open caution
    reading reads 3."""
    from common.cards import CardFunctions
    from common.effects import CardEffects
    FIGHTING, F_ENERGY = 6, 6
    stats = DictCardStatProvider({
        RIOLU: CardStat(RIOLU, name="Riolu", hp=70, maxDamageCost=1, maxDamage=30, attacks=(11,),
                        energyType=FIGHTING),
        MLUC: CardStat(MLUC, name="Mega Lucario ex", hp=340, megaEx=True, evolvesFrom="Riolu",
                       maxDamageCost=2, maxDamage=270, attacks=(21, 22), energyType=FIGHTING),
        F_ENERGY: CardStat(F_ENERGY, name="Basic {F} Energy", energyType=FIGHTING, cardType=5),
    }, attacks={11: AttackStat(11, damage=30, cost=1, energyTypes=(FIGHTING,)),
                21: AttackStat(21, damage=130, cost=1, energyTypes=(FIGHTING,)),
                22: AttackStat(22, damage=270, cost=2, energyTypes=(FIGHTING, FIGHTING))})
    combat = CombatMath(stats, functions=CardFunctions({MLUC: ["discard_energy_recur"]}),
                        transients=None, effects=CardEffects.load())
    body, discard = _b(RIOLU, 0), {FIGHTING: 3}
    assert combat.discard_recur_fuel(body, discard) == 3                    # the caution reading
    assert combat.discard_recur_fuel(body, discard, scope="self_arming") == 0   # the clock reading


def test_the_arming_scope_fails_closed_without_a_clause():
    """A tagged line the Effect-Clause compendium says nothing about yields NOTHING to the clock —
    ADR-0067's rule that the tag ROUTES and the clause quantifies, applied one zone over. Without
    it a newly tagged card would silently inherit the {F}/{M} lines' generous cap."""
    from common.cards import CardFunctions
    from common.effects import CardEffects
    UNKNOWN, FIGHTING = 990001, 6
    stats = DictCardStatProvider({
        UNKNOWN: CardStat(UNKNOWN, name="Untabulated", hp=100, maxDamageCost=3, maxDamage=200,
                          attacks=(41,), energyType=FIGHTING),
    }, attacks={41: AttackStat(41, damage=200, cost=3)})
    combat = CombatMath(stats, functions=CardFunctions({UNKNOWN: ["discard_energy_recur"]}),
                        transients=None, effects=CardEffects.load())
    body = {"id": UNKNOWN, "energies": []}
    assert combat.discard_recur_fuel(body, {FIGHTING: 3}) == 3
    assert combat.discard_recur_fuel(body, {FIGHTING: 3}, scope="self_arming") == 0
