"""Issue #495: one exact multi-attack profile across root and leaf consumers."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from train import composer_sensitivity as cs  # noqa: E402
from common import currency  # noqa: E402
from common.state_value import (allocate_energy_units, combat_build_profile,
                                combat_realization, energy_supply_for_units)  # noqa: E402
from common.cards import CardFunctions  # noqa: E402
from common.effects import CardEffects  # noqa: E402
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider  # noqa: E402
from common.strategy.combat import CombatMath  # noqa: E402


def _model(attacks="multi", energies=()):
    combat = cs.synthetic_combat(attacks)
    body = cs._body()
    body["energies"] = list(energies)
    body["energyCards"] = []
    model = cs._model(cs._obs(mine=cs._player(active=body)), combat=combat)
    return model, body


def test_each_attack_keeps_its_own_payoff_cost_and_envelope():
    model, body = _model("multi")
    zero = combat_build_profile(model, body)
    one = combat_build_profile(model, body, supply=energy_supply_for_units((cs.WATER,)))
    three = combat_build_profile(model, body,
                                 supply=energy_supply_for_units((cs.WATER,) * 3))
    assert zero.value_prizes == 0.0
    assert one.value_prizes == 120 / currency.PRIZE_DAMAGE_RATE
    assert one.winning_attack_id == cs.SYN_ATTACK_CHEAP
    assert three.value_prizes == 210 / currency.PRIZE_DAMAGE_RATE
    assert one.value_prizes < sum(candidate.standing_prizes for candidate in one.candidates)


def test_wrong_type_does_not_unlock_water_and_root_adapter_is_exact():
    model, body = _model("single")
    before = combat_build_profile(model, body)
    wrong = combat_build_profile(model, body, supply=energy_supply_for_units((cs.FIRE,)))
    right = combat_build_profile(model, body, supply=energy_supply_for_units((cs.WATER,)))
    assert wrong.value_prizes == before.value_prizes == 0.0
    assert (right.value_prizes - before.value_prizes) * currency.PRIZE_DAMAGE_RATE == 120.0


def test_removal_is_the_exact_inverse_and_identity_does_not_matter():
    original, body = _model("multi")
    clone_combat = cs.synthetic_combat("multi", cs.SYN_BODY_CLONE)
    clone_body = cs._body(cs.SYN_BODY_CLONE)
    clone = cs._model(cs._obs(mine=cs._player(active=clone_body)), combat=clone_combat)
    supply = energy_supply_for_units((cs.WATER,))
    original_delta = (combat_build_profile(original, body, supply=supply).value_prizes
                      - combat_build_profile(original, body).value_prizes)
    clone_delta = (combat_build_profile(clone, clone_body, supply=supply).value_prizes
                   - combat_build_profile(clone, clone_body).value_prizes)
    assert original_delta == clone_delta
    assert -original_delta == combat_build_profile(original, body).value_prizes - \
        combat_build_profile(original, body, supply=supply).value_prizes


def test_exact_allocator_can_concentrate_convex_units():
    model, body = _model("partial")
    second = dict(body, serial=999, energies=[], energyCards=[])
    allocation = allocate_energy_units(model, (body, second), (cs.WATER, cs.WATER))
    assert allocation.used_units == 2
    assert sorted(map(len, allocation.allocation)) == [0, 2]
    assert allocation.value_prizes > 0.0


def test_combat_math_distinguishes_unknown_and_known_cost():
    combat = cs.synthetic_combat("single")
    assert combat.attack_cost_slots(987654321) is None
    assert combat.attack_cost_slots(cs.SYN_ATTACK_CHEAP) == (cs.WATER,)
    match = combat.match_attack_slots(cs._body(), cs.SYN_ATTACK_CHEAP)
    assert match is not None and (match.matched, match.required) == (0, 1)


def test_known_zero_cost_is_fully_standing_and_realization_uses_an_envelope():
    free_id = 992_100
    stats = {
        cs.SYN_BODY: CardStat(cs.SYN_BODY, name="Free Attacker", hp=100,
                              attacks=(free_id,), stage="basic", synthetic=True),
        cs.SYN_OPP: CardStat(cs.SYN_OPP, name="Target", hp=100, stage="basic", synthetic=True),
    }
    combat = CombatMath(
        DictCardStatProvider(stats, attacks={free_id: AttackStat(free_id, damage=60, cost=0)}),
        CardFunctions({}), transients=None, effects=CardEffects({}))
    body = cs._body()
    model = cs._model(cs._obs(mine=cs._player(active=body)), combat=combat)
    profile = combat_build_profile(model, body)
    realization = combat_realization(model, body)
    assert combat.attack_cost_slots(free_id) == ()
    assert profile.value_damage == 60.0
    assert realization.value_prizes == max(realization.build_prizes,
                                            realization.now_prizes,
                                            realization.future_prizes)


def test_forward_forms_are_branched_zone_aware_deterministic_and_cycle_guarded():
    base, left, right, top, cycle = 992_200, 992_201, 992_202, 992_203, 992_204
    stats = {
        base: CardStat(base, name="Base", hp=60, stage="basic", synthetic=True),
        left: CardStat(left, name="Left", hp=90, stage="stage1", evolvesFrom="Base",
                       synthetic=True),
        right: CardStat(right, name="Right", hp=90, stage="stage1", evolvesFrom="Base",
                        synthetic=True),
        top: CardStat(top, name="Top", hp=120, stage="stage2", evolvesFrom="Left",
                      synthetic=True),
        cycle: CardStat(cycle, name="Base", hp=150, stage="stage2", evolvesFrom="Top",
                        synthetic=True),
        cs.SYN_OPP: CardStat(cs.SYN_OPP, name="Target", hp=100, stage="basic", synthetic=True),
    }
    combat = CombatMath(DictCardStatProvider(stats), CardFunctions({}), transients=None,
                        effects=CardEffects({}))
    mine = cs._player(active=cs._body(base))
    mine["discard"] = [cs._card(right, 88)]
    deck = (left, right, top, cycle)
    model = cs._model(cs._obs(mine=mine), combat=combat, deck=deck)
    forms = model.mine.forward_forms(base)
    assert forms == model.mine.forward_forms(base)
    assert [(form.card_id, form.hops, form.reachable) for form in forms] == [
        (left, 1, True), (right, 1, False), (top, 2, True), (cycle, 3, True)]
