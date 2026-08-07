"""S2 discard-recur fuel — the doom-relax REFINEMENT (ADR-0076).

`Pilot._doom_recur_fueled` already ships an all-or-nothing guard: whenever an opponent's Active is a
POSSIBLE discard-recur refueler, the matched-Read relax stands down entirely, regardless of whether
the fuel would actually change the affordability verdict. `recur_fuel_relax` (ships ON)
quantifies it instead — the CHARGED relax read is computed against the body's REAL fuel-augmented
Energy, so a line whose fuel still can't bridge the affordability gap is told apart from one where it
does, recovering a legitimate relax the coarse guard was blocking. OFF is byte-identical to today
(`tests/strategy/test_doomed_incoming.py`, `test_opponent_choice_reads.py` already pin the unarmed
shape); this file pins the armed refinement itself.
"""
from __future__ import annotations


from common.cards import CardFunctions
from common.pilot import Pilot
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy import Strategy
from common.strategy.general_strategy import GENERAL_STRATEGY

FIGHTING = 6
MY_ID, REFUEL, BASIC_F = 5001, 9001, 6001
ATTACK = 9101


def _setup(*, recur_fuel_relax: bool, fuel_energy_count: int):
    """The synthetic `AttackStat` sets no `energyTypes` on purpose, so only the plain COUNT check
    gates and the scenario stays about the FUEL AMOUNT rather than per-type composition."""
    stats = DictCardStatProvider({
        MY_ID: CardStat(MY_ID, name="My Active", hp=150),
        REFUEL: CardStat(REFUEL, name="Refueler", hp=100, energyType=FIGHTING,
                         maxDamageCost=5, maxDamage=200, attacks=(ATTACK,)),
        BASIC_F: CardStat(BASIC_F, name="Basic {F} Energy", cardType=5, energyType=FIGHTING),
    }, attacks={ATTACK: AttackStat(ATTACK, damage=200, cost=5)})
    funcs = CardFunctions({REFUEL: ["discard_energy_recur"]})
    pilot = Pilot(Strategy(roles={}), deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                  stats=stats, functions=funcs, doom_matched_relax=True,
                  recur_fuel_relax=recur_fuel_relax)
    pilot._incoming_budget = {"base_attach": 1, "burst_on_evo": 0}   # any truthy γ-matched value
    ma = {"id": MY_ID, "hp": 150, "energies": []}
    oa = {"id": REFUEL, "hp": 100, "energies": []}
    opp = {"active": [oa], "bench": [], "discard": [{"id": BASIC_F}] * fuel_energy_count}
    # The doom read goes through the per-decision snapshot now (POC-T1) — and re-stamp the budget,
    # since `_snapshot` reads it off the Pilot at build time.
    pilot._snapshot({"current": {"yourIndex": 0, "players": [
        {"active": [ma], "bench": []}, opp]}})
    return pilot, ma, oa, opp


def test_off_stands_down_entirely_whenever_fuel_is_merely_possible():
    """OFF (default): a merely POSSIBLE recur-fueled line blocks the relax outright, because the
    worst-case oracle's raw damage is unconditional on affordability."""
    pilot, ma, oa, opp = _setup(recur_fuel_relax=False, fuel_energy_count=1)
    assert pilot._active_doomed(ma, oa, opp) is True


def test_on_relaxes_when_the_fuel_still_cant_bridge_the_gap():
    """ON: the SAME board, quantified — 1 unit of fuel still cannot afford the cost-5 attack under
    the charged budget (1 + wild 2 = 3 < 5), so the relax fires."""
    pilot, ma, oa, opp = _setup(recur_fuel_relax=True, fuel_energy_count=1)
    assert pilot._active_doomed(ma, oa, opp) is False


def test_on_still_stays_doomed_when_the_fuel_actually_bridges_the_gap():
    """ON with enough discard fuel (3, the verified reload cap) that the charged budget AFFORDS the
    attack: the quantified read refuses to relax across a REAL threat (the ADR-0064 hidden burst)."""
    pilot, ma, oa, opp = _setup(recur_fuel_relax=True, fuel_energy_count=3)
    assert pilot._active_doomed(ma, oa, opp) is True
