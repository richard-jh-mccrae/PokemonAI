"""`fetch_target_matches`: the target-class x reading matrix, gates, and safe fallbacks."""
from __future__ import annotations

from common.cards.card_facts import (
    BASIC, BASIC_ENERGY, Ability, Clause, EnergyCard, FIRE, ITEM, PokemonCard, SPECIAL_ENERGY,
    STADIUM, STAGE1, STAGE2, SUPPORTER, TOOL, TrainerCard, WATER)
from common.cards.functions.fetch import WINDOW, fetch_target_matches


def fetch(**params):
    return Clause("fetch", **params)


def mon(card_id=1, *, hp=120, energy_type=FIRE, stage=BASIC, evolves_from=None, ex=False,
        mega_ex=False, tera=False, abilities=()):
    return PokemonCard(card_id=card_id, name=f"Mon {card_id}", hp=hp, energy_type=energy_type,
                       stage=stage, evolves_from=evolves_from, ex=ex, mega_ex=mega_ex,
                       tera=tera, abilities=tuple(abilities))


def trainer(kind):
    return TrainerCard(card_id=9, name="T", kind=kind)


def energy(kind=BASIC_ENERGY, provides=WATER):
    return EnergyCard(card_id=8, name="E", kind=kind, provides=provides)


def test_none_card_never_matches():
    assert not fetch_target_matches(fetch(target="pokemon"), None)


def test_a_conditional_fetch_is_excluded_from_the_reach_reading_only():
    dug = fetch(target="pokemon", dig=3)
    assert not fetch_target_matches(dug, mon(), reading="reach")
    assert fetch_target_matches(dug, mon(), reading="deadness")
    assert fetch_target_matches(dug, mon(), reading=WINDOW)


def test_target_any_counts_only_for_deadness():
    anything = fetch(target="any")
    assert fetch_target_matches(anything, trainer(ITEM), reading="deadness")
    assert not fetch_target_matches(anything, trainer(ITEM), reading="reach")
    assert not fetch_target_matches(anything, trainer(ITEM), reading=WINDOW)


def test_a_supporter_tutor_never_counts_as_reach():
    supporter = fetch(target="supporter")
    assert not fetch_target_matches(supporter, trainer(SUPPORTER), reading="reach")
    assert fetch_target_matches(supporter, trainer(SUPPORTER), reading="deadness")
    assert not fetch_target_matches(supporter, trainer(ITEM), reading="deadness")


def test_trainer_kind_targets_match_their_kind():
    assert fetch_target_matches(fetch(target="item"), trainer(ITEM))
    assert fetch_target_matches(fetch(target="tool"), trainer(TOOL))
    assert fetch_target_matches(fetch(target="stadium"), trainer(STADIUM))
    assert fetch_target_matches(fetch(target="trainer"), trainer(SUPPORTER), reading="deadness")
    assert not fetch_target_matches(fetch(target="item"), trainer(TOOL))
    assert not fetch_target_matches(fetch(target="item"), mon())


def test_energy_targets_respect_kind_and_colour():
    assert fetch_target_matches(fetch(target="basic_energy"), energy())
    assert not fetch_target_matches(fetch(target="basic_energy"), energy(kind=SPECIAL_ENERGY))
    assert fetch_target_matches(fetch(target="basic_energy", energy_type=WATER), energy())
    assert not fetch_target_matches(fetch(target="basic_energy", energy_type=FIRE), energy())
    assert fetch_target_matches(fetch(target="energy"), energy(kind=SPECIAL_ENERGY))


def test_pokemon_stage_and_flag_targets():
    assert fetch_target_matches(fetch(target="basic_pokemon"), mon())
    assert not fetch_target_matches(fetch(target="basic_pokemon"),
                                    mon(stage=STAGE1, evolves_from="X"))
    assert fetch_target_matches(fetch(target="evolution"), mon(stage=STAGE1, evolves_from="X"))
    assert fetch_target_matches(fetch(target="stage1"), mon(stage=STAGE1, evolves_from="X"))
    assert not fetch_target_matches(fetch(target="stage2"), mon(stage=STAGE1, evolves_from="X"))
    assert fetch_target_matches(fetch(target="stage2"), mon(stage=STAGE2, evolves_from="X"))
    assert fetch_target_matches(fetch(target="mega"), mon(mega_ex=True))
    assert not fetch_target_matches(fetch(target="mega"), mon(ex=True))
    assert fetch_target_matches(fetch(target="tera"), mon(tera=True))
    assert fetch_target_matches(fetch(target="pokemon_ex"), mon(ex=True))
    assert not fetch_target_matches(fetch(target="pokemon_ex"), mon())


def test_body_gates_no_rule_box_no_ability_hp_max():
    with_ability = mon(abilities=(Ability(name="A", clauses=(Clause("draw", amount=1),)),))
    assert not fetch_target_matches(fetch(target="pokemon", no_rule_box=True), mon(ex=True))
    assert fetch_target_matches(fetch(target="pokemon", no_rule_box=True), mon())
    assert not fetch_target_matches(fetch(target="pokemon", no_ability=True), with_ability)
    assert not fetch_target_matches(fetch(target="pokemon", hp_max=100), mon(hp=120))
    assert fetch_target_matches(fetch(target="pokemon", hp_max=120), mon(hp=120))


def test_colour_narrowing_applies_to_reach_and_window_but_not_deadness():
    typed = fetch(target="pokemon", energy_type=WATER)
    fire_mon = mon(energy_type=FIRE)
    assert not fetch_target_matches(typed, fire_mon, reading="reach")
    assert not fetch_target_matches(typed, fire_mon, reading=WINDOW)
    assert fetch_target_matches(typed, fire_mon, reading="deadness")


def test_an_unknown_reading_falls_back_to_the_strictest():
    dug = fetch(target="pokemon", dig=3)
    assert not fetch_target_matches(dug, mon(), reading="made_up")   # reach rules apply
    assert fetch_target_matches(fetch(target="pokemon"), mon(), reading="made_up")
