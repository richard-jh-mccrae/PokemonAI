"""`compute_active_damage` branch pins: every clause family, gate, and bound (ADR-0032/0083).

Synthetic records pin each branch in isolation; a handful of store-backed cases tie the same
paths to real printings. Expected numbers are worked by hand from the printed rules, never by
re-running the formula."""
from __future__ import annotations

from common.cards.card_facts import (
    BASIC, Ability, Attack, Clause, FIGHTING, FIRE, PokemonCard, STAGE1, WATER)
from common.cards.functions.damage import bench_reach, compute_active_damage, wr_adjust


def attack(damage=100, clauses=(), cost=(FIRE,)):
    return Attack(attack_id=1, name="Test Blast", cost=cost, damage=damage, clauses=tuple(clauses))


def mon(card_id=1, *, hp=120, energy_type=FIRE, stage=BASIC, evolves_from=None, ex=False,
        mega_ex=False, weakness=None, resistance=None, abilities=()):
    return PokemonCard(card_id=card_id, name=f"Mon {card_id}", hp=hp, energy_type=energy_type,
                       stage=stage, evolves_from=evolves_from, ex=ex, mega_ex=mega_ex,
                       weakness=weakness, resistance=resistance, abilities=tuple(abilities))


def test_no_attack_record_deals_nothing():
    assert compute_active_damage(None, mon(), mon()) == 0


def test_printed_damage_with_no_modifiers():
    assert compute_active_damage(attack(70), mon(), mon()) == 70


def test_weakness_doubles_and_resistance_floors_at_zero():
    assert compute_active_damage(attack(70), mon(energy_type=FIRE),
                                 mon(weakness=FIRE)) == 140
    assert compute_active_damage(attack(20), mon(energy_type=FIRE),
                                 mon(resistance=FIRE)) == 0    # 20 - 30 floors at 0
    assert compute_active_damage(attack(70), mon(energy_type=FIRE),
                                 mon(resistance=FIRE)) == 40


def test_ignores_wr_pierces_weakness_and_resistance():
    pierce = attack(70, clauses=(Clause("ignores_wr"),))
    assert compute_active_damage(pierce, mon(energy_type=FIRE), mon(weakness=FIRE)) == 70
    assert compute_active_damage(pierce, mon(energy_type=FIRE), mon(resistance=FIRE)) == 70


def test_wr_adjust_is_the_attack_blind_fallback():
    assert wr_adjust(mon(energy_type=FIRE), mon(weakness=FIRE), 50) == 100
    assert wr_adjust(mon(energy_type=FIRE), mon(resistance=FIRE), 50) == 20
    assert wr_adjust(mon(energy_type=FIRE), mon(resistance=FIRE), 10) == 0
    assert wr_adjust(None, mon(weakness=FIRE), 50) == 50
    assert wr_adjust(mon(), mon(), 0) == 0


def test_damage_range_bounds_replace_the_printed_number():
    ranged = attack(60, clauses=(Clause("damage_range", minimum=0, maximum=180),))
    assert compute_active_damage(ranged, mon(), mon(), bound="min") == 0
    assert compute_active_damage(ranged, mon(), mon(), bound="max") == 180
    assert compute_active_damage(ranged, mon(), mon()) == 60


def test_bench_partner_gate_zeroes_exact_and_min_but_not_max():
    gated = attack(120, clauses=(Clause("requires_bench", name="Lunatone"),))
    absent = {"atk_bench_names": ("Staryu",)}
    present = {"atk_bench_names": ("Lunatone", "Staryu")}
    assert compute_active_damage(gated, mon(), mon(), context=absent) == 0
    assert compute_active_damage(gated, mon(), mon(), context=absent, bound="min") == 0
    # Incoming worst case: they can bench the partner before attacking.
    assert compute_active_damage(gated, mon(), mon(), context=absent, bound="max") == 120
    assert compute_active_damage(gated, mon(), mon(), context=present) == 120
    # An unread bench makes no claim either way.
    assert compute_active_damage(gated, mon(), mon(), context={}) == 120


def test_discard_energy_scaler_typed_and_untyped():
    typed = attack(20, clauses=(
        Clause("scale", var="atk_discard_energy", per_unit=20, energy_type=WATER),))
    untyped = attack(20, clauses=(Clause("scale", var="atk_discard_energy", per_unit=20),))
    ctx = {"atk_discard_basic_by_type": {WATER: 3, FIRE: 5}, "atk_discard_energy_total": 9}
    assert compute_active_damage(typed, mon(), mon(), context=ctx) == 20 + 3 * 20
    assert compute_active_damage(untyped, mon(), mon(), context=ctx) == 20 + 9 * 20
    assert compute_active_damage(typed, mon(), mon(), context={}) == 20   # no facts, no add


def test_open_filtered_count_is_substring_and_fails_closed():
    named = attack(10, clauses=(
        Clause("scale", var="both_in_play_named", per_unit=20, filter=["Squawkabilly"]),))
    ctx = {"both_in_play_names": ("Squawkabilly ex", "Pikachu", "Squawkabilly")}
    assert compute_active_damage(named, mon(), mon(), context=ctx) == 10 + 2 * 20
    unfiltered = attack(10, clauses=(Clause("scale", var="both_in_play_named", per_unit=20),))
    assert compute_active_damage(unfiltered, mon(), mon(), context=ctx) == 10
    assert compute_active_damage(named, mon(), mon(), context={}) == 10


def test_filtered_count_over_attack_names_counts_bodies():
    by_attack = attack(0, clauses=(
        Clause("scale", var="atk_in_play_with_attack", per_unit=30, filter=["Hammer In"]),))
    ctx = {"atk_in_play_attack_names": (("Hammer In", "Raging Hammer"), ("Tackle",),
                                       ("Hammer In",))}
    assert compute_active_damage(by_attack, mon(), mon(), context=ctx) == 2 * 30


def test_plain_variable_scaler_reads_its_context_key():
    per_prize = attack(30, clauses=(Clause("scale", var="atk_prizes_taken", per_unit=30),))
    assert compute_active_damage(per_prize, mon(), mon(),
                                 context={"atk_prizes_taken": 4}) == 30 + 120
    assert compute_active_damage(per_prize, mon(), mon(), context={}) == 30


def test_hidden_scale_floor_mean_and_ceiling_from_exact_deck_facts():
    mill = attack(0, clauses=(Clause("hidden_scale", per_unit=100, sample=6,
                                     energy_type=WATER),))
    ctx = {"atk_deck_count": 10, "atk_deck_basic_by_type": {WATER: 8}}
    # Floor: 6 drawn from 10 with only 2 non-Water must include at least 4 Water.
    assert compute_active_damage(mill, mon(), mon(), context=ctx, bound="min") == 400
    assert compute_active_damage(mill, mon(), mon(), context=ctx, bound="max") == 600
    assert compute_active_damage(mill, mon(), mon(), context=ctx) == 400  # int(6*8/10)=4
    # No deck facts: only the ceiling assumes every card fuels.
    assert compute_active_damage(mill, mon(), mon(), context={}, bound="max") == 600
    assert compute_active_damage(mill, mon(), mon(), context={}) == 0


def test_hidden_scale_from_a_known_empty_deck_adds_nothing_at_any_bound():
    """`atk_deck_count == 0` is an exact fact, not missing facts — no phantom ceiling."""
    mill = attack(0, clauses=(Clause("hidden_scale", per_unit=100, sample=6,
                                     energy_type=WATER),))
    empty = {"atk_deck_count": 0, "atk_deck_basic_by_type": {}}
    assert compute_active_damage(mill, mon(), mon(), context=empty, bound="max") == 0
    assert compute_active_damage(mill, mon(), mon(), context=empty, bound="min") == 0
    assert compute_active_damage(mill, mon(), mon(), context=empty) == 0
    # An UNKNOWN deck (no count at all) keeps the assume-every-card-fuels ceiling.
    assert compute_active_damage(mill, mon(), mon(), context={}, bound="max") == 600


def test_boosts_are_type_gated_ex_gated_and_never_wake_a_zero():
    plain = attack(50)
    boosted = {"atk_boosts": ((30, None, False),)}
    assert compute_active_damage(plain, mon(), mon(), context=boosted) == 80
    typed = {"atk_boosts": ((30, WATER, False),)}
    assert compute_active_damage(plain, mon(energy_type=FIRE), mon(), context=typed) == 50
    vs_ex = {"atk_boosts": ((30, None, True),)}
    assert compute_active_damage(plain, mon(), mon(), context=vs_ex) == 50
    assert compute_active_damage(plain, mon(), mon(ex=True), context=vs_ex) == 80
    assert compute_active_damage(attack(0), mon(), mon(), context=boosted) == 0


def test_boosts_apply_before_weakness_doubles():
    ctx = {"atk_boosts": ((30, None, False),)}
    assert compute_active_damage(attack(50), mon(energy_type=FIRE), mon(weakness=FIRE),
                                 context=ctx) == 160    # (50+30)*2, not 50*2+30


def test_an_unresolved_attacker_record_fails_open():
    """Opponent cards outside the deck stores resolve to None; every attacker-side gate must
    read that as no-claim, never as a crash or an invented modifier."""
    # A typed boost cannot claim the attacker's colour matches; an untyped one still lands.
    typed = {"atk_boosts": ((30, WATER, False),)}
    assert compute_active_damage(attack(50), None, mon(), context=typed) == 50
    untyped = {"atk_boosts": ((30, None, False),)}
    assert compute_active_damage(attack(50), None, mon(), context=untyped) == 80
    # No attacker type: Weakness/Resistance make no claim either way.
    assert compute_active_damage(attack(50), None, mon(weakness=FIRE)) == 50
    assert compute_active_damage(attack(50), None, mon(resistance=FIRE)) == 50
    # An unknown attacker is never "an ex": prevention does not fire.
    assert compute_active_damage(attack(50), None, _prevents("ex")) == 50
    assert compute_active_damage(attack(50), None, mon(),
                                 defender_tags=frozenset({"prevent_ex_damage"})) == 50


def test_an_unresolved_defender_record_fails_open():
    typed = {"atk_boosts": ((30, WATER, False),)}
    vs_ex = {"atk_boosts": ((30, None, True),)}
    plain = {"atk_boosts": ((30, None, False),)}
    # A vs-ex boost cannot claim an unknown defender is an ex; a plain boost still lands.
    assert compute_active_damage(attack(50), mon(), None, context=vs_ex) == 50
    assert compute_active_damage(attack(50), mon(), None, context=plain) == 80
    # No defender record: no Weakness claim, and the attacker-type boost gate still reads.
    assert compute_active_damage(attack(50), mon(energy_type=FIRE), None) == 50
    assert compute_active_damage(attack(50), mon(energy_type=FIRE), None, context=typed) == 50
    assert compute_active_damage(attack(50), None, None) == 50


def _prevents(scope):
    return mon(abilities=(Ability(name="Wall", clauses=(
        Clause("prevents_damage_from", scope=scope),)),))


def test_ex_prevention_by_tag_scope_and_basic_scope():
    ex_attacker = mon(ex=True)
    basic_ex = mon(ex=True)                                  # no evolves_from -> Basic
    evolved_ex = mon(ex=True, stage=STAGE1, evolves_from="Something")
    plain_attacker = mon()
    assert compute_active_damage(attack(), ex_attacker, mon(),
                                 defender_tags=frozenset({"prevent_ex_damage"})) == 0
    assert compute_active_damage(attack(), plain_attacker, mon(),
                                 defender_tags=frozenset({"prevent_ex_damage"})) == 100
    assert compute_active_damage(attack(), ex_attacker, _prevents("ex")) == 0
    assert compute_active_damage(attack(), basic_ex, _prevents("basic_ex")) == 0
    assert compute_active_damage(attack(), evolved_ex, _prevents("basic_ex")) == 100


def test_ignores_effects_pierces_prevention_and_defender_reductions():
    nebula = attack(210, clauses=(Clause("ignores_wr"), Clause("ignores_effects")))
    assert compute_active_damage(nebula, mon(ex=True), _prevents("ex")) == 210
    reduced = mon(abilities=(Ability(name="Hide", clauses=(
        Clause("damage_reduction", amount=30),)),))
    assert compute_active_damage(nebula, mon(), reduced) == 210
    assert compute_active_damage(nebula, mon(), mon(),
                                 defender_transient={"prevent_all": True}) == 210


def test_defender_printed_reduction_applies_after_weakness():
    reduced = mon(weakness=FIRE, abilities=(Ability(name="Hide", clauses=(
        Clause("damage_reduction", amount=30),)),))
    assert compute_active_damage(attack(50), mon(energy_type=FIRE), reduced) == 70  # 50*2-30
    gated = mon(abilities=(Ability(name="Hide", clauses=(
        Clause("damage_reduction", amount=30, attacker_types=[WATER]),)),))
    assert compute_active_damage(attack(50), mon(energy_type=FIRE), gated) == 50


def test_prevents_big_enough_hits_outright():
    wall = mon(abilities=(Ability(name="Shell", clauses=(
        Clause("prevents_damage_at_least", amount=100),)),))
    assert compute_active_damage(attack(100), mon(), wall) == 0
    assert compute_active_damage(attack(90), mon(), wall) == 90


def test_transient_grants_on_the_defending_body():
    assert compute_active_damage(attack(80), mon(), mon(),
                                 defender_transient={"prevent_all": True}) == 0
    assert compute_active_damage(attack(80), mon(), mon(),
                                 defender_transient={"reduction": 30}) == 50
    typed = {"typed": ((30, (WATER,), False),)}
    assert compute_active_damage(attack(80), mon(energy_type=FIRE), mon(),
                                 defender_transient=typed) == 80
    matching = {"typed": ((30, (FIRE,), False),)}
    assert compute_active_damage(attack(80), mon(energy_type=FIRE), mon(),
                                 defender_transient=matching) == 50
    needs_ability = {"typed": ((30, None, True),)}
    assert compute_active_damage(attack(80), mon(), mon(),
                                 defender_transient=needs_ability) == 80


def test_store_backed_nebula_beam_and_jetting_blow():
    from common.cards import attack_index, pokemon_card_store
    store = pokemon_card_store()
    nebula = next(a for a in store[1031].attacks if a.attack_id == 1488)
    weak_to_water = mon(weakness=WATER)
    assert compute_active_damage(nebula, store[1031], weak_to_water) == 210   # pierces W/R
    jetting = attack_index()[1487]
    assert compute_active_damage(jetting, store[1031], weak_to_water) == 240  # 120 x2
    assert bench_reach(jetting) == 50 and bench_reach(nebula) == 0


def test_fighting_weakness_reads_off_the_store_records():
    from common.cards import pokemon_card_store
    store = pokemon_card_store()
    dudunsparce, land_crush = store[66], store[66].attacks[0]
    lucario = store[678]                                     # Fighting attacker
    assert dudunsparce.weakness == FIGHTING
    assert compute_active_damage(land_crush, dudunsparce, lucario) == 90
    mega_brave = next(a for a in lucario.attacks if a.attack_id == 983)
    assert mega_brave.damage == 270
    assert compute_active_damage(mega_brave, lucario, dudunsparce) == 540    # 270 x2 Weakness
