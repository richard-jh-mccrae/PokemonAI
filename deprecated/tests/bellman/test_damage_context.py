"""`SideFacts` -> `damage_context`: the one place a per-side fact becomes a directional key."""
from __future__ import annotations

from common.cards.card_facts import FIRE, WATER
from deprecated.bellman.damage_context import SideFacts, bench_gate_context, damage_context


def test_each_side_lands_under_its_directional_key():
    attacker = SideFacts(hand_size=5, active_energy=2, bench_count=3, prizes_taken=1,
                         active_counters=4, bench_names=("Lunatone",),
                         damage_boosts=((30, None, False),))
    defender = SideFacts(hand_size=7, active_energy=1, bench_count=2, prizes_taken=2,
                         active_counters=6, counters_in_play=9, ex_in_play=2)
    ctx = damage_context(attacker, defender)
    assert (ctx["atk_hand"], ctx["def_hand"]) == (5, 7)
    assert (ctx["atk_active_energy"], ctx["def_active_energy"]) == (2, 1)
    assert (ctx["atk_prizes_taken"], ctx["def_prizes_taken"]) == (1, 2)
    assert (ctx["atk_self_counters"], ctx["def_counters"]) == (4, 6)
    assert (ctx["def_counters_all"], ctx["def_ex_in_play"]) == (9, 2)
    assert ctx["atk_bench_names"] == ("Lunatone",)
    assert ctx["atk_boosts"] == ((30, None, False),)


def test_both_keys_are_direction_symmetric():
    a = SideFacts(bench_count=3, active_energy=2, in_play_names=("A",))
    b = SideFacts(bench_count=1, active_energy=4, in_play_names=("B",))
    forward, backward = damage_context(a, b), damage_context(b, a)
    assert forward["both_bench"] == backward["both_bench"] == 4
    assert forward["both_active_energy"] == backward["both_active_energy"] == 6
    assert set(forward["both_in_play_names"]) == set(backward["both_in_play_names"])


def test_unknown_deck_facts_are_omitted_never_zeroed():
    ctx = damage_context(SideFacts(), SideFacts())
    assert "atk_deck_count" not in ctx and "atk_deck_basic_by_type" not in ctx
    known = damage_context(SideFacts(deck_count=12, deck_basic_by_type={WATER: 4}), SideFacts())
    assert known["atk_deck_count"] == 12
    assert known["atk_deck_basic_by_type"] == {WATER: 4}


def test_the_discard_histogram_is_copied_not_aliased():
    histogram = {FIRE: 2}
    ctx = damage_context(SideFacts(discard_basic_by_type=histogram), SideFacts())
    histogram[FIRE] = 99
    assert ctx["atk_discard_basic_by_type"] == {FIRE: 2}


def test_bench_gate_context_is_only_the_partner_condition_slice():
    assert bench_gate_context(["Lunatone"]) == {"atk_bench_names": ("Lunatone",)}

