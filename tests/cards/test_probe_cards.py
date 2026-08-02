"""Probe-harness pure helpers: legal deck construction (+ later play-option / record).

Lib-free — the engine-driving shell is validated by running, not unit-tested (like
``dump_cards.py``).
"""
import pytest

from meta_tracker.card_functions import classify_functions
from meta_tracker.probe_cards import (
    _attack_turn_logs, _damaged_option_indices, _setup_active_option, _strip_serials,
    _TRIGGER_SUPPORTERS, build_evolution_deck, build_pokemon_deck, build_probe_deck,
    build_trigger_deck,
    evolution_chain, extract_probe, find_ability_option, find_evolve_option, find_play_option,
    select_shape,
)

BASIC_ENERGY, BASIC_MON, STAGE1, ITEM, ACE = 3, 100, 101, 200, 300
SUPPORTER_A, SUPPORTER_B, SUPPORTER_C = 400, 401, 402
SUPPORTER_D, SUPPORTER_E = 403, 404      # the pool must exceed `_TRIGGER_SUPPORTERS`,
                                         # or "exactly N, lowest first" cannot be tested


def _pool():
    return {
        BASIC_ENERGY: {"category": "basic_energy", "name": "Basic {F} Energy"},
        BASIC_MON: {"category": "pokemon", "stage": "basic", "name": "Filler Mon"},
        STAGE1: {"category": "pokemon", "stage": "stage1", "name": "Filler Stage1"},
        ITEM: {"category": "item", "name": "Nest Ball"},
        ACE: {"category": "item", "name": "Master Ball", "aceSpec": True},
        SUPPORTER_A: {"category": "supporter", "name": "Filler Supporter A"},
        SUPPORTER_B: {"category": "supporter", "name": "Filler Supporter B"},
        SUPPORTER_C: {"category": "supporter", "name": "Filler Supporter C"},
        SUPPORTER_D: {"category": "supporter", "name": "Filler Supporter D"},
        SUPPORTER_E: {"category": "supporter", "name": "Filler Supporter E"},
    }


@pytest.mark.req("REQ-FUNC-0004")
def test_probe_deck_is_60_and_contains_target():
    deck = build_probe_deck(ITEM, _pool())
    assert len(deck) == 60
    assert ITEM in deck


@pytest.mark.req("REQ-FUNC-0004")
def test_probe_deck_has_a_basic_pokemon_to_be_startable():
    deck = build_probe_deck(ITEM, _pool())     # Item target -> deck needs a filler basic
    assert BASIC_MON in deck


@pytest.mark.req("REQ-FUNC-0004")
def test_normal_target_gets_several_legal_copies():
    deck = build_probe_deck(ITEM, _pool())
    assert 1 < deck.count(ITEM) <= 4           # several copies (drawable), within 4-copy rule


@pytest.mark.req("REQ-FUNC-0004")
def test_ace_spec_target_is_a_single_copy():
    deck = build_probe_deck(ACE, _pool())      # ACE SPEC: max one per deck
    assert deck.count(ACE) == 1
    assert len(deck) == 60


@pytest.mark.req("REQ-FUNC-0004")
def test_probe_deck_has_pokemon_for_fetch_effects():
    pool = _pool()
    deck = build_probe_deck(ITEM, pool)
    n_pokemon = sum(pool.get(c, {}).get("category") == "pokemon" for c in deck)
    assert n_pokemon >= 2      # search/fetch effects need Pokémon in deck to find


@pytest.mark.req("REQ-FUNC-0004")
def test_probe_deck_prefers_high_hp_basics():
    pool = {3: {"category": "basic_energy", "name": "E"}, 200: {"category": "item", "name": "T"}}
    for i, hp in enumerate([40, 60, 90, 120, 200, 330]):
        pool[10 + i] = {"category": "pokemon", "stage": "basic", "name": f"B{hp}", "hp": hp}
    deck = build_probe_deck(200, pool)     # _BENCH_BASICS of 6 basics -> highest-HP ones win
    assert 15 in deck                      # hp 330 (highest) seeded (survives chip damage)
    assert 10 not in deck                  # hp 40 (lowest) left out


@pytest.mark.req("REQ-FUNC-0004")
def test_probe_deck_search_fodder_adds_frail_basic_and_supporter():
    pool = {3: {"category": "basic_energy", "name": "E"}, 200: {"category": "item", "name": "T"},
            300: {"category": "supporter", "name": "Prof"}}
    for i, hp in enumerate([40, 60, 90, 120, 200, 330]):
        pool[10 + i] = {"category": "pokemon", "stage": "basic", "name": f"B{hp}", "hp": hp}
    deck = build_probe_deck(200, pool, search_fodder=True)
    assert 10 in deck       # hp 40 (frail) -> target for HP-capped searches ("<=70 HP")
    assert 300 in deck      # a Supporter -> target for Supporter-fetch searches
    plain = build_probe_deck(200, pool)               # default: neither (sturdy bench only)
    assert 10 not in plain and 300 not in plain


@pytest.mark.req("REQ-FUNC-0010")
def test_probe_deck_low_hp_picks_fragile_basics():
    pool = {3: {"category": "basic_energy", "name": "E"}, 200: {"category": "item", "name": "T"}}
    for i, hp in enumerate([40, 60, 90, 120, 200, 330]):
        pool[10 + i] = {"category": "pokemon", "stage": "basic", "name": f"B{hp}", "hp": hp}
    deck = build_probe_deck(200, pool, low_hp=True)   # attrition pass wants fragile mons (get KO'd)
    assert 10 in deck                      # hp 40 (lowest) seeded -> KO'd -> stocks discard
    assert 15 not in deck                  # hp 330 (highest) left out


@pytest.mark.req("REQ-FUNC-0004")
def test_probe_deck_has_distinct_basics_for_a_bench():
    pool = dict(_pool())                                          # add 2 more distinct basics
    pool[110] = {"category": "pokemon", "stage": "basic", "name": "Basic Two"}
    pool[111] = {"category": "pokemon", "stage": "basic", "name": "Basic Three"}
    deck = build_probe_deck(ITEM, pool)
    distinct_basics = {c for c in set(deck)
                       if pool.get(c, {}).get("category") == "pokemon"
                       and pool[c].get("stage") == "basic"}
    assert len(distinct_basics) >= 2     # bench of *different* Pokémon enables gust/switch probing


# --- find_play_option -------------------------------------------------------------

OTHER, TARGET = 111, 222


def _obs(options, hand, you=0):
    """A minimal observation: my hand + the engine's option list."""
    players = [{"hand": None}, {"hand": None}]
    players[you] = {"hand": [{"id": c} for c in hand]}
    return {"select": {"option": options}, "current": {"yourIndex": you, "players": players}}


@pytest.mark.req("REQ-FUNC-0005")
def test_find_play_option_locates_the_target_among_options():
    # two PLAY options; must return the one whose hand card is TARGET (option list-index 1)
    obs = _obs(options=[{"type": 7, "index": 0}, {"type": 7, "index": 1}], hand=[OTHER, TARGET])
    assert find_play_option(obs, TARGET) == 1


@pytest.mark.req("REQ-FUNC-0005")
def test_find_play_option_none_when_target_not_in_hand():
    obs = _obs(options=[{"type": 7, "index": 0}], hand=[OTHER])
    assert find_play_option(obs, TARGET) is None


@pytest.mark.req("REQ-FUNC-0005")
def test_find_play_option_ignores_non_play_options():
    # ATTACK option (type 13) at index 1 must not be mistaken for playing TARGET
    obs = _obs(options=[{"type": 13, "index": 1}], hand=[OTHER, TARGET])
    assert find_play_option(obs, TARGET) is None


# --- extract_probe ----------------------------------------------------------------

@pytest.mark.req("REQ-FUNC-0005")
def test_extract_probe_builds_record_from_observation():
    obs_after = {"logs": [{"type": 4, "playerIndex": 0}], "select": {"context": 0}}
    assert extract_probe(obs_after, actor=0) == {
        "actor": 0, "logs": [{"type": 4, "playerIndex": 0}], "contexts": [0]}


@pytest.mark.req("REQ-FUNC-0005")
def test_extract_probe_tolerates_missing_select():
    assert extract_probe({"logs": []}, actor=1) == {"actor": 1, "logs": [], "contexts": []}


@pytest.mark.req("REQ-FUNC-0005")
def test_probe_record_feeds_the_classifier():
    # play that drew a card AND raised a free damage-counter placement
    obs_after = {"logs": [{"type": 4, "playerIndex": 0}], "select": {"context": 14}}
    rec = extract_probe(obs_after, actor=0)
    tags = classify_functions({"category": "supporter"}, probe=rec)
    assert "draw" in tags and "spread" in tags


@pytest.mark.req("REQ-FUNC-0007")
def test_attack_turn_logs_keeps_only_the_attacking_turn():
    # capture must not bleed into a LATER turn whose re-energize ATTACH(11) would be a
    # false `energy_accel` (the Blaziken bug). Keep [first ATTACK .. next turn boundary).
    logs = [
        {"type": 11},                  # pre-attack energize (before ATTACK) -> dropped
        {"type": 15},                  # ATTACK (kept from here)
        {"type": 16, "value": -50},    # its damage -> kept
        {"type": 3},                   # TURN_END -> boundary
        {"type": 11},                  # later turn's re-energize -> dropped (the false accel)
        {"type": 15},                  # later attack -> dropped
    ]
    assert [l["type"] for l in _attack_turn_logs(logs)] == [15, 16]


@pytest.mark.req("REQ-FUNC-0007")
def test_attack_turn_logs_without_boundary_keeps_to_end():
    # game ended on the attack (no TURN_END) -> keep everything from ATTACK (spread counters)
    logs = [{"type": 15}, {"type": 16}, {"type": 16}, {"type": 23}]
    assert [l["type"] for l in _attack_turn_logs(logs)] == [15, 16, 16, 23]


@pytest.mark.req("REQ-FUNC-0007")
def test_build_pokemon_deck_matches_attack_energy():
    deck = build_pokemon_deck(500, [5, 5])         # cheapest attack costs 2 Psychic (EnergyType 5)
    assert len(deck) == 60
    assert deck.count(500) == 4                     # target Pokémon
    assert set(deck) == {500, 5}                    # rest is Psychic basic Energy (card id 5)


@pytest.mark.req("REQ-FUNC-0007")
def test_setup_active_option_finds_target_in_hand():
    obs = {"select": {"option": [{"index": 0}, {"index": 1}]},
           "current": {"yourIndex": 0, "players": [{"hand": [{"id": 111}, {"id": 222}]}, {}]}}
    assert _setup_active_option(obs, 222) == 1      # option whose hand card is the target
    assert _setup_active_option(obs, 999) is None


@pytest.mark.req("REQ-FUNC-0005")
def test_damaged_option_indices_targets_hurt_pokemon():
    # heal target choice: my Active is damaged (opt 0), my Bench[0] is full (opt 1)
    obs = {"select": {"option": [
        {"type": 3, "area": 4, "index": 0, "playerIndex": 0},     # ACTIVE — 90/120
        {"type": 3, "area": 5, "index": 0, "playerIndex": 0},     # BENCH[0] — full
    ]}, "current": {"players": [
        {"active": [{"hp": 90, "maxHp": 120}], "bench": [{"hp": 70, "maxHp": 70}]}, {},
    ]}}
    assert _damaged_option_indices(obs) == [0]      # only the hurt Pokémon (so heal shows)


# --- find_ability_option (Phase 2b: Pokémon abilities) ----------------------------

@pytest.mark.req("REQ-FUNC-0008")
def test_find_ability_option_locates_target_active():
    # ATTACK option must not be mistaken for the target's ABILITY (type 10) on my Active
    obs = {"select": {"option": [
        {"type": 13, "attackId": 1},
        {"type": 10, "area": 4, "index": 0, "playerIndex": 0},
    ]}, "current": {"players": [{"active": [{"id": 555}], "bench": []}, {}]}}
    assert find_ability_option(obs, 555, me=0) == 1


@pytest.mark.req("REQ-FUNC-0008")
def test_find_ability_option_none_when_target_absent():
    obs = {"select": {"option": [{"type": 10, "area": 4, "index": 0, "playerIndex": 0}]},
           "current": {"players": [{"active": [{"id": 999}], "bench": []}, {}]}}
    assert find_ability_option(obs, 555, me=0) is None


@pytest.mark.req("REQ-FUNC-0008")
def test_find_ability_option_matches_benched_target():
    obs = {"select": {"option": [{"type": 10, "area": 5, "index": 1, "playerIndex": 0}]},
           "current": {"players": [{"active": [{"id": 1}], "bench": [{"id": 2}, {"id": 555}]}, {}]}}
    assert find_ability_option(obs, 555, me=0) == 0


@pytest.mark.req("REQ-FUNC-0008")
def test_find_ability_option_defaults_player_to_me():
    # ABILITY options always own -> missing playerIndex means "me"
    obs = {"select": {"option": [{"type": 10, "area": 4, "index": 0}]},
           "current": {"players": [{"active": [{"id": 555}], "bench": []}, {}]}}
    assert find_ability_option(obs, 555, me=0) == 0


# --- evolutions (Phase 3: Stage 1/2) ----------------------------------------------

def _evo_data():
    return {
        10: {"name": "Dreepy", "evolvesFrom": None},
        11: {"name": "Drakloak", "evolvesFrom": "Dreepy"},
        12: {"name": "Dragapult ex", "evolvesFrom": "Drakloak"},
        99: {"name": "Dreepy", "evolvesFrom": None},     # reprint: same name, higher id
    }


@pytest.mark.req("REQ-FUNC-0009")
def test_evolution_chain_walks_basic_first():
    assert evolution_chain(12, _evo_data()) == [10, 11, 12]


@pytest.mark.req("REQ-FUNC-0009")
def test_evolution_chain_basic_is_a_singleton():
    assert evolution_chain(10, _evo_data()) == [10]      # Basic has no pre-evolution


@pytest.mark.req("REQ-FUNC-0009")
def test_evolution_chain_resolves_preevo_by_lowest_id():
    assert evolution_chain(11, _evo_data()) == [10, 11]  # Dreepy -> id 10, not reprint 99


@pytest.mark.req("REQ-FUNC-0009")
def test_build_evolution_deck_stacks_chain_and_matching_energy():
    deck = build_evolution_deck([10, 11, 12], [2, 5])    # Fire + Psychic
    assert len(deck) == 60
    assert deck.count(10) == 4 and deck.count(11) == 4 and deck.count(12) == 4
    assert set(deck) == {10, 11, 12, 2, 5}               # rest is Fire(id 2) + Psychic(id 5) energy
    assert 10 in deck                                    # Basic -> legal start


@pytest.mark.req("REQ-FUNC-0009")
def test_find_evolve_option_locates_evolution_in_hand():
    # PLAY option must not be mistaken for the EVOLVE (type 9) that puts card 11 into play
    obs = {"select": {"option": [
        {"type": 7, "index": 0},
        {"type": 9, "area": 2, "index": 1, "inPlayArea": 4, "inPlayIndex": 0},
    ]}, "current": {"yourIndex": 0, "players": [{"hand": [{"id": 10}, {"id": 11}]}, {}]}}
    assert find_evolve_option(obs, 11, me=0) == 1


@pytest.mark.req("REQ-FUNC-0009")
def test_find_evolve_option_none_when_evolution_not_in_hand():
    obs = {"select": {"option": [{"type": 9, "area": 2, "index": 0, "inPlayArea": 4, "inPlayIndex": 0}]},
           "current": {"yourIndex": 0, "players": [{"hand": [{"id": 10}]}, {}]}}
    assert find_evolve_option(obs, 12, me=0) is None


# --- triggered-Ability probe helpers (Issue #305) ---------------------------------


@pytest.mark.req("REQ-FUNC-0015")
def test_build_trigger_deck_stacks_the_line_and_N_supporter_targets():
    """`_TRIGGER_SUPPORTERS` DISTINCT Supporter lines, lowest card ids first: a Supporter-fetching
    trigger is skipped entirely by the engine when the deck holds none, so too few lines let the
    shuffle decide the recorded shape.

    The STRUCTURE is asserted against the constant; the constant's VALUE is asserted against a
    literal floor. Both halves are needed and neither alone is honest:

    * parameterising by `_TRIGGER_SUPPORTERS` stops the test breaking when the knob is tuned — this
      test previously spelled "two" in its name and body and broke on Issue #326's retune for no
      behavioural reason;
    * but parameterising ALONE makes it vacuous, because `build_trigger_deck` reads the same
      constant, so both sides move together and no value can ever fail. Measured, not assumed: with
      the floor removed, setting the constant to 3 still passed. That is the "assert the join from
      the side that built it" trap.

    So the floor below is a LITERAL, and it is the Issue #326 finding: 2 lines lost to the mulligan
    tail (the probe deck's only Basic is the target line, 4 in 60, so ~60% of hands miss for both
    players and every opponent mulligan deals another card). Lowering the knob past 4 must fail."""
    assert _TRIGGER_SUPPORTERS >= 4, (
        "Issue #326: fewer than 4 Supporter lines lets the mulligan tail strip the deck of search "
        "targets, and the engine then skips the select entirely — the probe records the draw's "
        "shape instead of the card's")
    pool = _pool()
    deck = build_trigger_deck([BASIC_MON, STAGE1], BASIC_ENERGY, pool)
    sups = sorted(c for c in pool if pool[c]["category"] == "supporter")
    assert len(sups) > _TRIGGER_SUPPORTERS, "pool too small to test 'exactly N, lowest first'"
    taken, skipped = sups[:_TRIGGER_SUPPORTERS], sups[_TRIGGER_SUPPORTERS:]
    assert len(deck) == 60
    assert deck.count(BASIC_MON) == 4 and deck.count(STAGE1) == 4
    assert all(deck.count(s) == 4 for s in taken)        # every chosen line at 4 copies
    assert not any(s in deck for s in skipped)           # exactly N lines, lowest ids first
    assert deck.count(BASIC_ENERGY) == 60 - 8 - 4 * _TRIGGER_SUPPORTERS


@pytest.mark.req("REQ-FUNC-0015")
def test_build_trigger_deck_never_double_counts_a_target_already_in_the_line():
    """A Supporter can't be the evolution line, but the guard is the same one that keeps a card
    from exceeding its 4-copy cap — assert it rather than assume the categories stay disjoint."""
    deck = build_trigger_deck([SUPPORTER_A], BASIC_ENERGY, _pool())
    assert deck.count(SUPPORTER_A) == 4
    assert deck.count(SUPPORTER_B) == 4 and deck.count(SUPPORTER_C) == 4


@pytest.mark.req("REQ-FUNC-0015")
def test_strip_serials_drops_shuffle_dependent_ids_only():
    """A card's `serial` is its position in a SHUFFLED deck, so it differs run to run while the
    select's shape does not — dropping it is what makes a captured raw select comparable."""
    sel = {"type": 9, "contextCard": {"id": 648, "serial": 12, "playerIndex": 0},
           "option": [{"type": 1}, {"type": 2}], "deck": [{"id": 7, "serial": 43}]}
    assert _strip_serials(sel) == {
        "type": 9, "contextCard": {"id": 648, "playerIndex": 0},
        "option": [{"type": 1}, {"type": 2}], "deck": [{"id": 7}]}


@pytest.mark.req("REQ-FUNC-0015")
def test_select_shape_keeps_the_kind_and_drops_the_candidate_count():
    """The shape is what KIND of decision a select is. A deck search over 42 remaining cards offers
    a different count every game, so `n_options` and the `deck` payload must not reach a fixture."""
    sel = {"type": 1, "context": 22, "minCount": 0, "maxCount": 5,
           "option": [{"type": 3, "index": i} for i in range(34)],
           "deck": [{"id": 7}] * 42, "contextCard": None}
    assert select_shape(sel) == {"select_type": 1, "context": 22, "min_count": 0, "max_count": 5,
                                 "option_types": [3], "context_card_id": None}


@pytest.mark.req("REQ-FUNC-0015")
def test_select_shape_names_the_card_a_gate_belongs_to():
    """`contextCard` is how a consumer knows whose trigger an ACTIVATE gate is."""
    sel = {"type": 9, "context": 43, "minCount": 1, "maxCount": 1,
           "option": [{"type": 1}, {"type": 2}], "contextCard": {"id": 1071, "playerIndex": 0}}
    assert select_shape(sel)["context_card_id"] == 1071
    assert select_shape(sel)["option_types"] == [1, 2]
