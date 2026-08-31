from __future__ import annotations

from dataclasses import replace
from types import MappingProxyType

import pytest

from ledger_helpers import (AIR_BALLOON, DRAGAPULT, DREEPY, FIRE, LILLIES, MAKUHITA,
                            MEGA_STARMIE, PSYCHIC, body, player, printout)

from common.cards.card_facts import BASIC, Attack, Clause, PokemonCard
from common.ledger import EvaluationModel, evaluate
from common.ledger.capabilities import (body_capability, card_option_units,
                                        has_payable_active_ko)
from common.observation import ObservationStateBuilder


READY, UNPAYABLE, TARGET, THREAT, STURDY, FRAGILE = range(9_990_001, 9_990_007)
BOSS, SWITCH, BUDEW = 1182, 1123, 235
FEZANDIPITI_EX, RIOLU = 140, 677


def board(**kwargs):
    return ObservationStateBuilder().root(printout(**kwargs))


def model(*cards):
    context = EvaluationModel.build()
    store = {**context.store}
    store.update((card.card_id, card) for card in cards)
    return replace(context, store=MappingProxyType(store))


def pokemon(card_id, name, *, hp=100, energy_type=FIRE, weakness=None,
            resistance=None, retreat_cost=1, damage=0, cost=(), roles=(), clauses=()):
    attacks = (() if damage <= 0 else
               (Attack(card_id, f"{name} attack", tuple(cost), damage,
                       clauses=tuple(clauses)),))
    return PokemonCard(
        card_id, name, hp, energy_type, BASIC, weakness=weakness,
        resistance=resistance, retreat_cost=retreat_cost, attacks=attacks,
        default_roles=roles, covers="full")


def test_direct_promotion_prefers_payable_ko_over_unpayable_printed_damage():
    context = model(
        pokemon(READY, "Ready", damage=100, cost=(FIRE,)),
        pokemon(UNPAYABLE, "Unpayable", damage=300, cost=(PSYCHIC, PSYCHIC)),
        pokemon(TARGET, "Target", hp=100),
    )
    ready = board(
        me=player(active=body(READY, 1, energies=(FIRE,)),
                  bench=[body(UNPAYABLE, 2, energies=(FIRE,))]),
        them=player(own=False, active=body(TARGET, 3)))
    unpayable = board(
        me=player(active=body(UNPAYABLE, 2, energies=(FIRE,)),
                  bench=[body(READY, 1, energies=(FIRE,))]),
        them=player(own=False, active=body(TARGET, 3)))

    assert evaluate(ready, context).total > evaluate(unpayable, context).total


def test_direct_promotion_uses_weakness_and_resistance_for_attack_yield():
    context = model(
        pokemon(READY, "Fire attacker", damage=70, cost=(FIRE,)),
        pokemon(UNPAYABLE, "Psychic attacker", energy_type=PSYCHIC,
                damage=70, cost=(PSYCHIC,)),
        pokemon(TARGET, "Target", hp=120, weakness=FIRE, resistance=PSYCHIC),
    )
    fire = board(
        me=player(active=body(READY, 1, energies=(FIRE,)),
                  bench=[body(UNPAYABLE, 2, energies=(PSYCHIC,))]),
        them=player(own=False, active=body(TARGET, 3, hp=120, max_hp=120)))
    psychic = board(
        me=player(active=body(UNPAYABLE, 2, energies=(PSYCHIC,)),
                  bench=[body(READY, 1, energies=(FIRE,))]),
        them=player(own=False, active=body(TARGET, 3, hp=120, max_hp=120)))

    assert evaluate(fire, context).total > evaluate(psychic, context).total


def test_direct_promotion_avoids_doomed_prize_exposure_at_equal_attack_yield():
    context = model(
        pokemon(STURDY, "Sturdy", hp=200, retreat_cost=2,
                damage=100, cost=(FIRE,)),
        pokemon(FRAGILE, "Fragile", hp=60, retreat_cost=2,
                damage=100, cost=(FIRE,)),
        pokemon(THREAT, "Threat", damage=80, cost=(FIRE,)),
    )
    sturdy = board(
        me=player(active=body(STURDY, 1, hp=200, max_hp=200, energies=(FIRE,)),
                  bench=[body(FRAGILE, 2, hp=60, max_hp=60, energies=(FIRE,))]),
        them=player(own=False, active=body(THREAT, 3, energies=(FIRE,))))
    fragile = board(
        me=player(active=body(FRAGILE, 2, hp=60, max_hp=60, energies=(FIRE,)),
                  bench=[body(STURDY, 1, hp=200, max_hp=200, energies=(FIRE,))]),
        them=player(own=False, active=body(THREAT, 3, energies=(FIRE,))))

    assert evaluate(sturdy, context).total > evaluate(fragile, context).total


def test_direct_promotion_values_return_hp_before_either_body_is_doomed():
    context = model(
        pokemon(STURDY, "Sturdy", hp=150),
        pokemon(FRAGILE, "Fragile", hp=80),
        pokemon(THREAT, "Threat", damage=70, cost=(FIRE,)),
    )
    sturdy = board(
        me=player(active=body(STURDY, 1, hp=150, max_hp=150),
                  bench=[body(FRAGILE, 2, hp=80, max_hp=80)]),
        them=player(own=False, active=body(THREAT, 3, energies=(FIRE,))))
    fragile = board(
        me=player(active=body(FRAGILE, 2, hp=80, max_hp=80),
                  bench=[body(STURDY, 1, hp=150, max_hp=150)]),
        them=player(own=False, active=body(THREAT, 3, energies=(FIRE,))))

    assert evaluate(sturdy, context).total > evaluate(fragile, context).total


def test_direct_promotion_values_a_payable_ko_over_item_lock_denial():
    context = model(
        pokemon(READY, "Ready", damage=100, cost=(FIRE,)),
        pokemon(TARGET, "Loaded target", hp=100, damage=100, cost=(FIRE,),
                roles=("primary_attacker",)),
    )
    ready = board(
        me=player(active=body(READY, 1, energies=(FIRE,)),
                  bench=[body(BUDEW, 2, energies=(FIRE,))]),
        them=player(own=False, active=body(
            TARGET, 3, hp=100, max_hp=100)))
    denial = board(
        me=player(active=body(BUDEW, 2, hp=30, max_hp=30, energies=(FIRE,)),
                  bench=[body(READY, 1, energies=(FIRE,))]),
        them=player(own=False, active=body(
            TARGET, 3, hp=100, max_hp=100)))

    assert evaluate(ready, context).total > evaluate(denial, context).total


def test_direct_promotion_values_ko_of_a_live_forward_attacker():
    context = EvaluationModel.build()
    fez = board(
        me=player(
            active=body(FEZANDIPITI_EX, 1, hp=210, max_hp=210,
                        energies=(7, 7, PSYCHIC)),
            bench=[body(BUDEW, 2, hp=30, max_hp=30)]),
        them=player(own=False, active=body(RIOLU, 3, hp=80, max_hp=80)))
    budew = board(
        me=player(
            active=body(BUDEW, 2, hp=30, max_hp=30),
            bench=[body(FEZANDIPITI_EX, 1, hp=210, max_hp=210,
                        energies=(7, 7, PSYCHIC))]),
        them=player(own=False, active=body(RIOLU, 3, hp=80, max_hp=80)))

    assert evaluate(fez, context).total > evaluate(budew, context).total


def test_bench_only_snipe_does_not_claim_an_active_ko():
    context = model(
        pokemon(READY, "Sniper", damage=1, cost=(FIRE,),
                clauses=(Clause("bench_snipe", amount=120, target="opp_bench"),)),
        pokemon(TARGET, "Target", hp=100),
    )
    state = board(
        me=player(active=body(READY, 1, energies=(FIRE,))),
        them=player(own=False, active=body(TARGET, 2, hp=100, max_hp=100)))

    assert not has_payable_active_ko(
        state.me.active, state.me, state.them, state, context)


def test_confused_attacker_does_not_claim_a_certain_active_ko():
    context = model(
        pokemon(READY, "Attacker", damage=100, cost=(FIRE,)),
        pokemon(TARGET, "Target", hp=100),
    )
    state = board(
        me=player(active=body(READY, 1, energies=(FIRE,)), confused=True),
        them=player(own=False, active=body(TARGET, 2, hp=100, max_hp=100)))

    assert not has_payable_active_ko(
        state.me.active, state.me, state.them, state, context)


def test_damaged_primary_relief_is_bounded_by_the_backup_prize_exposure():
    context = EvaluationModel.build()
    primary = board(
        me=player(
            active=body(DRAGAPULT, 1, hp=120, max_hp=320,
                        energies=(FIRE, PSYCHIC)),
            bench=[body(FEZANDIPITI_EX, 2, hp=210, max_hp=210,
                        energies=(7, 7, PSYCHIC))]),
        them=player(own=False, active=body(MAKUHITA, 3, hp=150, max_hp=150)))
    backup = board(
        me=player(
            active=body(FEZANDIPITI_EX, 2, hp=210, max_hp=210,
                        energies=(7, 7, PSYCHIC)),
            bench=[body(DRAGAPULT, 1, hp=120, max_hp=320,
                        energies=(FIRE, PSYCHIC))]),
        them=player(own=False, active=body(MAKUHITA, 3, hp=150, max_hp=150)))

    assert evaluate(primary, context).total > evaluate(backup, context).total


@pytest.mark.parametrize("status", ("asleep", "paralyzed"))
def test_attack_blocking_condition_does_not_claim_retreat_progress(status):
    state = board(me=player(
        active=body(DREEPY, 1, energies=(PSYCHIC,)), bench=[body(MAKUHITA, 2)],
        **{status: True}))

    capability = body_capability(
        state.me.active, state.me, state.them, state, EvaluationModel.build())

    assert capability.retreat_progress == 0.0


def test_confusion_allows_retreat_progress_and_paid_retreat_cures_every_condition():
    context = EvaluationModel.build()
    before = board(me=player(
        active=body(DREEPY, 1, energies=(PSYCHIC,)), bench=[body(MAKUHITA, 2)],
        confused=True, poisoned=True, burned=True))
    healthy = board(me=player(
        active=body(DREEPY, 1, energies=(PSYCHIC,)), bench=[body(MAKUHITA, 2)]))
    after = board(me=player(
        active=body(MAKUHITA, 2), bench=[body(DREEPY, 1)]))
    illegally_preserved_energy = board(me=player(
        active=body(MAKUHITA, 2), bench=[body(DREEPY, 1, energies=(PSYCHIC,))]))

    capability = body_capability(
        before.me.active, before.me, before.them, before, context)
    assert capability.retreat_progress == 1.0
    assert evaluate(healthy, context).total > evaluate(before, context).total
    assert evaluate(after, context).total < evaluate(illegally_preserved_energy, context).total


def test_tool_reduction_makes_free_retreat_fully_ready():
    state = board(me=player(
        active=body(DREEPY, 1, tools=(AIR_BALLOON,)), bench=[body(MAKUHITA, 2)]))

    capability = body_capability(
        state.me.active, state.me, state.them, state, EvaluationModel.build())

    assert capability.retreat_progress == 1.0


def test_doomed_sacrifice_has_less_exposure_than_developed_attacker():
    context = model(pokemon(THREAT, "Threat", hp=500, damage=500, cost=(FIRE,)))
    sacrifice = board(
        me=player(active=body(BUDEW, 1, hp=30, max_hp=30),
                  bench=[body(MEGA_STARMIE, 2, hp=330, max_hp=330)], asleep=True),
        them=player(own=False, active=body(THREAT, 3, hp=500, max_hp=500,
                                           energies=(FIRE,))))
    developed = board(
        me=player(active=body(MEGA_STARMIE, 2, hp=330, max_hp=330),
                  bench=[body(BUDEW, 1, hp=30, max_hp=30)], asleep=True),
        them=player(own=False, active=body(THREAT, 3, hp=500, max_hp=500,
                                           energies=(FIRE,))))

    def exposure(state):
        return abs(next(
            item.activation for item in evaluate(state, context).contributions
            if item.feature == "active.doomed" and item.provenance == ("me.bodies",)))

    assert exposure(sacrifice) < exposure(developed)


def test_draw_supporter_option_does_not_depend_on_uncommitted_sibling_card():
    context = EvaluationModel.build()
    with_boss = board(me=player(
        active=body(DREEPY, 1, tools=(AIR_BALLOON,)),
        bench=[body(MAKUHITA, 2)], hand=[LILLIES, BOSS]))
    with_redundant_switch = board(me=player(
        active=body(DREEPY, 1, tools=(AIR_BALLOON,)),
        bench=[body(MAKUHITA, 2)], hand=[LILLIES, SWITCH]))

    boss_units = card_option_units(
        context.facts(LILLIES), with_boss.me, with_boss.them, with_boss, context)
    switch_units = card_option_units(
        context.facts(LILLIES), with_redundant_switch.me, with_redundant_switch.them,
        with_redundant_switch, context)

    assert boss_units == switch_units


def test_redundant_retreat_tool_is_better_held_for_a_later_carrier():
    context = EvaluationModel.build()
    held = board(me=player(
        active=body(DREEPY, 1, energies=(PSYCHIC,)), bench=[body(MAKUHITA, 2)],
        hand=[AIR_BALLOON]))
    attached = board(me=player(
        active=body(DREEPY, 1, energies=(PSYCHIC,), tools=(AIR_BALLOON,)),
        bench=[body(MAKUHITA, 2)]))

    assert evaluate(held, context).total > evaluate(attached, context).total


def test_retreat_tool_attachment_is_worthwhile_when_it_creates_mobility():
    context = EvaluationModel.build()
    held = board(me=player(
        active=body(DREEPY, 1), bench=[body(MAKUHITA, 2)], hand=[AIR_BALLOON]))
    attached = board(me=player(
        active=body(DREEPY, 1, tools=(AIR_BALLOON,)), bench=[body(MAKUHITA, 2)]))

    assert evaluate(attached, context).total > evaluate(held, context).total


def test_retreat_tool_is_better_held_than_parked_on_the_bench():
    context = EvaluationModel.build()
    held = board(me=player(
        active=body(DREEPY, 1), bench=[body(MAKUHITA, 2)], hand=[AIR_BALLOON]))
    attached = board(me=player(
        active=body(DREEPY, 1), bench=[body(MAKUHITA, 2, tools=(AIR_BALLOON,))]))

    assert evaluate(held, context).total > evaluate(attached, context).total
