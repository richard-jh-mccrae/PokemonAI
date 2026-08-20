"""Typed-cost payment: exact colours pay their own slots, wildcards cover what nothing else can."""
from __future__ import annotations

from common.cards.functions.energy import (
    ENERGY_COLORLESS, ENERGY_FIRE, ENERGY_WATER, ENERGY_WILDCARD, payment_fraction,
    unmet_cost_slots)


def test_a_wildcard_is_spent_only_where_no_exact_colour_can_pay():
    provisions = [ENERGY_WILDCARD, ENERGY_FIRE]
    cost = [ENERGY_FIRE, ENERGY_WATER]
    assert unmet_cost_slots(provisions, cost) == ()
    assert payment_fraction(provisions, cost) == 1.0


def test_exact_colours_still_report_their_shortfall():
    assert unmet_cost_slots([ENERGY_FIRE], [ENERGY_FIRE, ENERGY_WATER]) == ((1, ENERGY_WATER),)


def test_leftover_wildcards_and_exacts_both_pay_colorless():
    cost = [ENERGY_FIRE, ENERGY_COLORLESS, ENERGY_COLORLESS]
    assert unmet_cost_slots([ENERGY_FIRE, ENERGY_WILDCARD, ENERGY_WATER], cost) == ()


def test_an_empty_cost_is_always_fully_paid():
    assert unmet_cost_slots([], []) == ()
    assert payment_fraction([], []) == 1.0
    assert payment_fraction([ENERGY_FIRE], [ENERGY_FIRE, ENERGY_WATER]) == 0.5


def test_provision_units_floors_at_one_and_reads_the_evolution_clause():
    from common.cards import energy_card_store
    from common.cards.card_facts import Clause, EnergyCard, SPECIAL_ENERGY
    from common.cards.functions.energy import provision_units
    ignition = energy_card_store()[17]
    assert provision_units(ignition) == 1
    assert provision_units(ignition, evolved=True) == 3
    assert provision_units(energy_card_store()[3]) == 1          # Basic Water: no clause
    zeroed = EnergyCard(card_id=99, name="Z", kind=SPECIAL_ENERGY,
                        clauses=(Clause("energy_provide", amount=0),))
    assert provision_units(zeroed) == 1                          # an attached card is 1 minimum
    assert provision_units(None) == 1
