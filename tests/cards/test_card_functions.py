"""Pure card-function classifier: static fields (+ probe record + overrides) -> tags.

Lib-free: feeds synthetic card / probe dicts (the probe shape mirrors cg/api.py ``Log``
+ ``SelectContext``, as the probe harness captures them) and asserts the derived tags.
"""
import pytest

from meta_tracker.card_functions import (
    DERIVED_TAGS, accumulate_tables, build_function_table, classify_functions)


@pytest.mark.req("REQ-FUNC-0001")
def test_structural_facts_are_not_tagged():
    # ex/Mega-ex, trainer subtype, ACE SPEC read straight off CardData at runtime -> function
    # table is purely *behavioral*; a card with no behavioral probe gets no tags.
    assert classify_functions({"name": "Pikachu ex", "ex": True}) == []
    assert classify_functions({"category": "stadium"}) == []
    assert classify_functions({"category": "item", "aceSpec": True}) == []
    assert classify_functions({"category": "supporter"}) == []


@pytest.mark.req("REQ-FUNC-0002")
def test_probe_actor_draw_is_draw_tag():
    drew = {"actor": 0, "logs": [{"type": 4, "playerIndex": 0}], "contexts": []}  # DRAW by actor
    assert "draw" in classify_functions({"category": "supporter"}, probe=drew)
    # opponent drawing (e.g. forced by my card) is not "I draw"
    opp = {"actor": 0, "logs": [{"type": 4, "playerIndex": 1}], "contexts": []}
    assert "draw" not in classify_functions({"category": "supporter"}, probe=opp)


@pytest.mark.req("REQ-FUNC-0002")
def test_probe_deck_to_hand_move_is_search():
    # MOVE_CARD(6) DECK(1) -> HAND(2) by actor = tutor
    p = {"actor": 0, "logs": [{"type": 6, "playerIndex": 0, "fromArea": 1, "toArea": 2}], "contexts": []}
    assert "search" in classify_functions({"category": "item"}, probe=p)


@pytest.mark.req("REQ-FUNC-0002")
def test_probe_damage_counter_any_context_is_spread():
    p = {"actor": 0, "logs": [], "contexts": [14]}   # SelectContext.DAMAGE_COUNTER_ANY
    assert "spread" in classify_functions({"category": "pokemon"}, probe=p)


@pytest.mark.req("REQ-FUNC-0002")
def test_probe_deck_look_is_dig():
    # MOVE(6) DECK(1)->LOOK(12) by actor = looked at top of deck (Roto-Stick)
    p = {"actor": 0, "logs": [{"type": 6, "playerIndex": 0, "fromArea": 1, "toArea": 12}], "contexts": []}
    assert "dig" in classify_functions({"category": "item"}, probe=p)


@pytest.mark.req("REQ-FUNC-0002")
def test_probe_look_to_hand_is_draw_not_search():
    # "look at top N, put 1 into your hand" (Drakloak's Recon Directive) is a *draw* engine,
    # not a deck-wide tutor — only direct DECK->HAND move is `search`.
    p = {"actor": 0, "logs": [{"type": 6, "playerIndex": 0, "fromArea": 12, "toArea": 2}], "contexts": []}
    tags = classify_functions({"category": "item"}, probe=p)
    assert "draw" in tags and "search" not in tags


@pytest.mark.req("REQ-FUNC-0002")
def test_probe_deck_to_bench_is_search():
    # tutoring a Basic from deck into play (Precious Trolley) = search
    p = {"actor": 0, "logs": [{"type": 6, "playerIndex": 0, "fromArea": 1, "toArea": 5}], "contexts": []}
    assert "search" in classify_functions({"category": "item"}, probe=p)


@pytest.mark.req("REQ-FUNC-0002")
def test_probe_own_switch_is_switch():
    # SWITCH(8) on actor's side = moved my own Active out (Switch item)
    p = {"actor": 0, "logs": [{"type": 8, "playerIndex": 0}], "contexts": []}
    assert "switch" in classify_functions({"category": "item"}, probe=p)


@pytest.mark.req("REQ-FUNC-0002")
def test_probe_opponent_switch_is_gust():
    # SWITCH(8) on *opponent's* side = forced their Active to change (Boss's Orders)
    p = {"actor": 0, "logs": [{"type": 8, "playerIndex": 1}], "contexts": []}
    tags = classify_functions({"category": "supporter"}, probe=p)
    assert "gust" in tags and "switch" not in tags


@pytest.mark.req("REQ-FUNC-0002")
def test_probe_attach_by_nontool_is_energy_accel():
    # ATTACH(11) by actor from a non-Tool card = put Energy into play (Energy Coin / Waitress)
    p = {"actor": 0, "logs": [{"type": 11, "playerIndex": 0}], "contexts": []}
    assert "energy_accel" in classify_functions({"category": "item"}, probe=p)
    # a Tool attaching *itself* must NOT count as accel
    assert "energy_accel" not in classify_functions({"category": "tool"}, probe=p)


@pytest.mark.req("REQ-FUNC-0002")
def test_probe_each_special_condition_maps_to_its_own_tag():
    # the 5 Special Conditions split by purpose, not a vague `status` (chip: poison/burn; lock:
    # sleep/paralyze; confuse: deterrent)
    for log_type, tag in [(17, "poison"), (18, "burn"), (19, "sleep"), (20, "paralyze"), (21, "confuse")]:
        p = {"actor": 0, "logs": [{"type": log_type, "playerIndex": 1}], "contexts": []}
        tags = classify_functions({"category": "pokemon"}, probe=p)
        assert tag in tags and "status" not in tags
    # recovering from a condition != inflicting it
    rec = {"actor": 0, "logs": [{"type": 20, "playerIndex": 1, "isRecover": True}], "contexts": []}
    assert "paralyze" not in classify_functions({"category": "pokemon"}, probe=rec)


@pytest.mark.req("REQ-FUNC-0002")
def test_probe_hp_increase_is_heal():
    # HP_CHANGE(16) with value>0 on my Pokémon = removed damage (Potion)
    p = {"actor": 0, "logs": [{"type": 16, "playerIndex": 0, "value": 30}], "contexts": []}
    assert "heal" in classify_functions({"category": "item"}, probe=p)
    # taking damage (negative value / a damage counter) is NOT heal
    dmg = {"actor": 0, "logs": [{"type": 16, "playerIndex": 0, "value": -30, "putDamageCounter": True}],
           "contexts": []}
    assert "heal" not in classify_functions({"category": "item"}, probe=dmg)


@pytest.mark.req("REQ-FUNC-0002")
def test_probe_opponent_hand_to_deck_is_hand_disruption():
    # MOVE_CARD_REVERSE(7) opp HAND(2)->DECK(1) = forced opponent to shuffle hand (Iono/Judge)
    p = {"actor": 0, "logs": [{"type": 7, "playerIndex": 1, "fromArea": 2, "toArea": 1}], "contexts": []}
    assert "hand_disruption" in classify_functions({"category": "supporter"}, probe=p)
    # MY OWN hand reshuffling (Judge resets me too) != disruption *of the opponent*
    mine = {"actor": 0, "logs": [{"type": 6, "playerIndex": 0, "fromArea": 2, "toArea": 1}], "contexts": []}
    assert "hand_disruption" not in classify_functions({"category": "supporter"}, probe=mine)


@pytest.mark.req("REQ-FUNC-0002")
def test_probe_opponent_energy_to_discard_is_energy_denial():
    # MOVE_CARD(6) opp ENERGY(8)->DISCARD(3) = knocked Energy off opponent (Crushing Hammer)
    p = {"actor": 0, "logs": [{"type": 6, "playerIndex": 1, "fromArea": 8, "toArea": 3}], "contexts": []}
    assert "energy_denial" in classify_functions({"category": "item"}, probe=p)
    # discarding MY OWN Energy (attack cost) != denial
    mine = {"actor": 0, "logs": [{"type": 6, "playerIndex": 0, "fromArea": 8, "toArea": 3}], "contexts": []}
    assert "energy_denial" not in classify_functions({"category": "pokemon"}, probe=mine)


@pytest.mark.req("REQ-FUNC-0002")
def test_probe_discard_to_hand_is_recycle():
    # MOVE_CARD(6) mine DISCARD(3)->HAND(2) = pulled a card back out of my discard (Night Stretcher)
    p = {"actor": 0, "logs": [{"type": 6, "playerIndex": 0, "fromArea": 3, "toArea": 2}], "contexts": []}
    assert "recycle" in classify_functions({"category": "item"}, probe=p)
    # DECK->HAND is search, not recycle (different origin)
    deck = {"actor": 0, "logs": [{"type": 6, "playerIndex": 0, "fromArea": 1, "toArea": 2}], "contexts": []}
    assert "recycle" not in classify_functions({"category": "item"}, probe=deck)


@pytest.mark.req("REQ-FUNC-0003")
def test_overrides_union_with_derived_tags():
    drew = {"actor": 0, "logs": [{"type": 4, "playerIndex": 0}], "contexts": []}   # probe -> draw
    tags = classify_functions({}, probe=drew, overrides=["gust"])  # probe can't reach gust -> curate it
    assert "gust" in tags and "draw" in tags                       # union, not replace


@pytest.mark.req("REQ-FUNC-0003")
def test_no_signal_degrades_to_empty():
    assert classify_functions({}) == []
    assert classify_functions({}, probe={"actor": 0, "logs": [], "contexts": []}) == []


# --- build_function_table ---------------------------------------------------------

@pytest.mark.req("REQ-FUNC-0006")
def test_build_table_merges_probe_and_omits_untagged():
    cards = {1: {"category": "supporter"}, 2: {"category": "pokemon"}}   # 2 is a vanilla basic
    probes = {1: {"actor": 0, "logs": [{"type": 4, "playerIndex": 0}], "contexts": []}}  # 1 draws
    table = build_function_table(cards, probes)
    assert table[1] == ["draw"]     # behavioral only (supporter category is *not* a tag)
    assert 2 not in table           # no behavioral tags -> omitted from shipped table


@pytest.mark.req("REQ-FUNC-0006")
def test_build_table_applies_overrides():
    table = build_function_table({5: {"category": "item"}}, probes={}, overrides={5: ["gust"]})
    assert table[5] == ["gust"]     # override only (item category isn't a tag)


# --- accumulate_tables (monotonic cross-run merge) --------------------------------

@pytest.mark.req("REQ-FUNC-0011")
def test_accumulate_unions_prior_run_tags():
    new = {1: ["draw"], 2: ["status"]}
    prior = {1: ["heal"], 3: ["recycle"]}        # card 1 gained heal before; card 3 not seen this run
    acc = accumulate_tables(new, prior)
    assert acc[1] == ["draw", "heal"]            # union of this run + prior, sorted
    assert acc[2] == ["status"]                  # card seen only this run is kept
    assert acc[3] == ["recycle"]                 # prior-only card NOT dropped (stochastic miss)


@pytest.mark.req("REQ-FUNC-0011")
def test_accumulate_never_removes_a_once_observed_tag():
    # this run's probe missed the (rng-gated) tag, but a prior run caught it -> survives
    assert accumulate_tables({1: ["item"]}, {1: ["item", "recycle"]})[1] == ["item", "recycle"]


@pytest.mark.req("REQ-FUNC-0011")
def test_accumulate_from_empty_prior_is_identity():
    assert accumulate_tables({1: ["draw"]}, {}) == {1: ["draw"]}


@pytest.mark.req("REQ-FUNC-0002")
def test_DERIVED_TAGS_is_exactly_what_the_classifier_can_emit():
    """A stale `DERIVED_TAGS` fails in the direction that HIDES data loss: a tag wrongly listed
    reads as re-derivable, so the audit stays green while a `--fresh` rebuild deletes it."""
    records = [
        {"actor": 0, "logs": [{"type": 4, "playerIndex": 0}]},                       # draw
        {"actor": 0, "logs": [{"type": 6, "playerIndex": 0, "fromArea": 1, "toArea": 2}]},   # search
        {"actor": 0, "logs": [{"type": 6, "playerIndex": 0, "fromArea": 1, "toArea": 12}]},  # dig
        {"actor": 0, "logs": [{"type": 6, "playerIndex": 0, "fromArea": 3, "toArea": 2}]},   # recycle
        {"actor": 0, "logs": [{"type": 8, "playerIndex": 0}]},                       # switch
        {"actor": 0, "logs": [{"type": 8, "playerIndex": 1}]},                       # gust
        {"actor": 0, "logs": [{"type": 11, "playerIndex": 0}]},                      # energy_accel
        {"actor": 0, "logs": [{"type": 16, "playerIndex": 0, "value": 30}]},         # heal
        {"actor": 0, "logs": [{"type": 6, "playerIndex": 1, "fromArea": 2, "toArea": 1}]},   # hand_disruption
        {"actor": 0, "logs": [{"type": 6, "playerIndex": 1, "fromArea": 8, "toArea": 3}]},   # energy_denial
        {"actor": 0, "logs": [], "contexts": [14]},                                  # spread
    ] + [{"actor": 0, "logs": [{"type": t, "playerIndex": 0}]}                       # the 5 conditions
         for t in (17, 18, 19, 20, 21)]

    emitted = set()
    for rec in records:
        emitted |= set(classify_functions({"category": "item"}, probe=rec))

    assert emitted - DERIVED_TAGS == set(), \
        f"the classifier emits tags DERIVED_TAGS does not declare: {sorted(emitted - DERIVED_TAGS)}"
    assert DERIVED_TAGS - emitted == set(), \
        f"DERIVED_TAGS declares tags no classify rule produced: {sorted(DERIVED_TAGS - emitted)}"
    # Positive control on the same run: the sweep really did classify something, so the two empty
    # differences above are an agreement rather than two empty sets compared with each other.
    assert len(emitted) > 10, sorted(emitted)
