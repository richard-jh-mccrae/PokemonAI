"""S2 discard-recur fuel — the doom-relax REFINEMENT (ADR-0076).

`Pilot._doom_recur_fueled` already ships an all-or-nothing guard: whenever an opponent's Active is a
POSSIBLE discard-recur refueler, the matched-Read relax stands down entirely, regardless of whether
the fuel would actually change the affordability verdict. `recur_fuel_relax` (OFF by default)
quantifies it instead — the CHARGED relax read is computed against the body's REAL fuel-augmented
Energy, so a line whose fuel still can't bridge the affordability gap is told apart from one where it
does, recovering a legitimate relax the coarse guard was blocking. OFF is byte-identical to today
(`tests/strategy/test_threat_shadow.py`, `test_opponent_choice_reads.py` already pin the unarmed
shape); this file pins the armed refinement itself.
"""
from __future__ import annotations

import types

from common.cards import CardFunctions
from common.pilot import Pilot
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy import Strategy
from common.strategy.general_strategy import GENERAL_STRATEGY

FIGHTING = 6
MY_ID, REFUEL, BASIC_F = 5001, 9001, 6001
ATTACK = 9101


def _setup(*, recur_fuel_relax: bool, fuel_energy_count: int):
    """MY 150-HP Active vs a BARE (0 Energy) opponent refueler whose single attack costs 5 —
    unaffordable under `_DOOM_CHARGED`'s base budget (wild=2, no burst — `evolvesFrom` unset) alone,
    and by design the synthetic `AttackStat` sets no `energyTypes`, so `attack_type_payable` is a
    trivial pass-through (`combat.py`: "True whenever the attack record doesn't resolve") — only the
    plain COUNT check (`attached + wild + burst >= cost`) gates, keeping the scenario about the FUEL
    AMOUNT, not per-type composition. `fuel_energy_count` populates `opp["discard"]` — the ONE
    source both `_doom_recur_fueled` (the possibility gate) and `_recur_fueled_oa` (the
    augmentation amount) read, so the two cannot disagree about how much fuel there is."""
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
    """OFF (default): the possible recur-fueled line blocks the relax outright — the worst-case
    oracle's raw damage (200, unconditional on affordability) exceeds my HP (150), so it stays
    doomed, even though the CHARGED read — never even reached — could not afford the attack either
    way. This is today's shipped behavior, unaffected by the kill-switch's existence."""
    pilot, ma, oa, opp = _setup(recur_fuel_relax=False, fuel_energy_count=1)
    assert pilot._active_doomed(ma, oa, opp) is True


def test_on_relaxes_when_the_fuel_still_cant_bridge_the_gap():
    """ON: the SAME board, but the relax is now quantified — 1 unit of real fuel (0→1 attached)
    still can't afford the cost-5 attack under the charged budget (1 + wild 2 = 3 < 5), so the
    relax correctly fires and the AI is freed from an unnecessary worst-case posture the coarse
    guard was blocking for no reason."""
    pilot, ma, oa, opp = _setup(recur_fuel_relax=True, fuel_energy_count=1)
    assert pilot._active_doomed(ma, oa, opp) is False


def test_on_still_stays_doomed_when_the_fuel_actually_bridges_the_gap():
    """ON, but with enough discard fuel (3, the verified reload cap) that the charged budget
    (3 + wild 2 = 5) now AFFORDS the attack — the quantified read correctly refuses to relax across
    a REAL threat, exactly the ADR-0064 hidden-burst lesson this whole mechanism exists to protect."""
    pilot, ma, oa, opp = _setup(recur_fuel_relax=True, fuel_energy_count=3)
    assert pilot._active_doomed(ma, oa, opp) is True


def test_threat_shadow_decided_bit_tracks_the_same_refinement():
    """`_threat_shadow`'s diagnostic `decided`/`doom_charged` fields must not drift from the live
    decider: OFF, `decided` is False whenever fuel is possible (today's shape); ON, `decided` tracks
    whether the quantified charged read actually ran."""
    state = {"players": [
        {"active": [{"id": MY_ID, "hp": 150, "energies": []}]},
        {"active": [{"id": REFUEL, "hp": 100, "energies": []}],
         "discard": [{"id": BASIC_F}]},
    ], "yourIndex": 0}
    obs = {"current": state}
    pilot, _ma, _oa, _opp = _setup(recur_fuel_relax=False, fuel_energy_count=1)
    board_off = types.SimpleNamespace(active_doomed=True)
    sh_off = pilot._threat_shadow(obs, board_off)
    assert sh_off is not None and sh_off["decided"] is False
    pilot_on, _ma, _oa, _opp = _setup(recur_fuel_relax=True, fuel_energy_count=1)
    board_on = types.SimpleNamespace(active_doomed=False)
    sh_on = pilot_on._threat_shadow(obs, board_on)
    assert sh_on is not None and sh_on["decided"] is True
