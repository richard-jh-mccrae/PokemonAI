"""Restriction OBSERVATION (ADR-0032 item 6, H3) — pure rules, lib-free.

A heal clause's ``restriction`` is derived from which in-play targets the engine's
select actually OFFERS on a seeded board (damaged bench Mega + damaged non-Mega
Active), not from card text. Synthetic shapes mirror the real engine dumps
(cg/api.py Option/Log/Pokemon).
"""
import pytest

from meta_tracker.card_effects import (
    apply_observed_restrictions, derive_restriction, upgrade_restriction)
from meta_tracker.probe_restrictions import (
    find_chip_attacker, healed_serials, offered_heal_targets, pick_sturdies,
    restriction_deck, snapshot_board)

# The canonical observation board: damaged Mega on the Bench, damaged non-Mega
# Active, plus an undamaged benched body — disambiguates mega_only / active_only /
# unrestricted in ONE offer.
MEGA_BENCH = {"serial": 11, "mega": True, "active": False, "damaged": True}
NONMEGA_ACT = {"serial": 21, "mega": False, "active": True, "damaged": True}
NONMEGA_BENCH = {"serial": 31, "mega": False, "active": False, "damaged": False}
BOARD = [NONMEGA_ACT, MEGA_BENCH, NONMEGA_BENCH]


# --- derivation (REQ-EFFECT-0013) ---------------------------------------------------

@pytest.mark.req("REQ-EFFECT-0013")
def test_offer_of_both_classes_derives_unrestricted():
    # Potion: the select offers the damaged Active AND the damaged bench Mega
    assert derive_restriction(BOARD, [21, 11]) == {"restriction": None}


@pytest.mark.req("REQ-EFFECT-0013")
def test_offer_of_mega_only_derives_mega_only():
    # Wally's Compassion: ONLY the bench Mega offered while the damaged Active exists
    assert derive_restriction(BOARD, [11]) == {"restriction": "mega_only"}


@pytest.mark.req("REQ-EFFECT-0013")
def test_offer_of_active_only_derives_active_only():
    # Arven's Sandwich: ONLY the Active offered while the damaged bench Mega exists
    assert derive_restriction(BOARD, [21]) == {"restriction": "active_only"}


@pytest.mark.req("REQ-EFFECT-0013")
def test_empty_or_unknown_offer_is_an_error_not_a_guess():
    assert "error" in derive_restriction(BOARD, [])
    assert "error" in derive_restriction(BOARD, [99])       # serial not on my board


@pytest.mark.req("REQ-EFFECT-0013")
def test_mega_offer_without_an_excluded_damaged_non_mega_is_uninformative():
    # the Mega was the only damaged body -> its exclusivity proves nothing
    board = [{"serial": 11, "mega": True, "active": True, "damaged": True},
             {"serial": 31, "mega": False, "active": False, "damaged": False}]
    assert "error" in derive_restriction(board, [11])


@pytest.mark.req("REQ-EFFECT-0013")
def test_active_offer_without_an_excluded_damaged_benched_body_is_uninformative():
    board = [NONMEGA_ACT,
             {"serial": 11, "mega": True, "active": False, "damaged": False}]
    assert "error" in derive_restriction(board, [21])


@pytest.mark.req("REQ-EFFECT-0013")
def test_bench_non_mega_only_offer_is_ambiguous():
    # no vocabulary value explains "benched non-Mega only" — explicit error
    board = BOARD + [{"serial": 41, "mega": False, "active": False, "damaged": True}]
    assert "error" in derive_restriction(board, [41])


# --- clause upgrade (REQ-EFFECT-0014) ------------------------------------------------

@pytest.mark.req("REQ-EFFECT-0014")
def test_observed_confirming_the_authored_restriction_changes_nothing():
    cls = [{"kind": "heal", "amount": "all", "restriction": "mega_only",
            "rider": "bounce_energy_to_hand"}]
    out, conflicts = upgrade_restriction(cls, "mega_only")
    assert out == cls and conflicts == []
    cls = [{"kind": "heal", "amount": 30}]
    out, conflicts = upgrade_restriction(cls, None)
    assert out == cls and conflicts == []


@pytest.mark.req("REQ-EFFECT-0014")
def test_observed_restriction_upgrades_an_unrestricted_measured_clause():
    out, conflicts = upgrade_restriction([{"kind": "heal", "amount": 60}], "mega_only")
    assert out == [{"kind": "heal", "amount": 60, "restriction": "mega_only"}]
    assert conflicts == []                       # None -> observed is the normal upgrade


@pytest.mark.req("REQ-EFFECT-0014")
def test_conflicting_authored_restriction_loses_to_the_observed_one():
    # engine is authority: a differing hand-authored gate is replaced AND reported
    out, conflicts = upgrade_restriction(
        [{"kind": "heal", "amount": 60, "restriction": "active_only"}], "mega_only")
    assert out == [{"kind": "heal", "amount": 60, "restriction": "mega_only"}]
    assert conflicts == [("active_only", "mega_only")]


@pytest.mark.req("REQ-EFFECT-0014")
def test_observed_unrestricted_strips_a_conflicting_authored_gate():
    out, conflicts = upgrade_restriction(
        [{"kind": "heal", "amount": 60, "restriction": "active_only"}], None)
    assert out == [{"kind": "heal", "amount": 60}]
    assert conflicts == [("active_only", None)]


@pytest.mark.req("REQ-EFFECT-0014")
def test_sibling_amount_modes_survive_when_the_observation_matches_one_clause():
    # Arven's Sandwich: observed active_only matches the 30-clause; the 100
    # arvens_pokemon amount-mode is NOT a conflict — it ships untouched
    cls = [{"kind": "heal", "amount": 30, "restriction": "active_only"},
           {"kind": "heal", "amount": 100, "restriction": "arvens_pokemon"}]
    out, conflicts = upgrade_restriction(cls, "active_only")
    assert sorted(out, key=str) == sorted(cls, key=str)
    assert conflicts == []


@pytest.mark.req("REQ-EFFECT-0014")
def test_upgrade_merges_the_upgraded_twin_into_the_authored_clause():
    # a stale unrestricted measurement + the authored mega_only clause: upgrading the
    # twin gives it the same merge key -> max-merge collapses them
    cls = [{"kind": "heal", "amount": 60},
           {"kind": "heal", "amount": "all", "restriction": "mega_only"}]
    out, _ = upgrade_restriction(cls, "mega_only")
    assert out == [{"kind": "heal", "amount": "all", "restriction": "mega_only"}]


@pytest.mark.req("REQ-EFFECT-0014")
def test_non_heal_clauses_and_heal_less_cards_are_untouched():
    cls = [{"kind": "draw", "amount": 3}]
    out, conflicts = upgrade_restriction(cls, "mega_only")
    assert out == cls and conflicts == []
    out, conflicts = upgrade_restriction([], "mega_only")
    assert out == [] and conflicts == []


# --- table pass (REQ-EFFECT-0015) ----------------------------------------------------

@pytest.mark.req("REQ-EFFECT-0015")
def test_apply_observed_upgrades_only_observed_cards_and_reports_conflicts():
    table = {1117: [{"kind": "heal", "amount": 30}],
             1229: [{"kind": "heal", "amount": "all", "restriction": "mega_only"}],
             7: [{"kind": "heal", "amount": 60, "restriction": "active_only"}],
             8: [{"kind": "draw", "amount": 2}]}
    observed = {1117: {"restriction": None},          # confirms
                1229: {"restriction": "mega_only"},   # confirms
                7: {"restriction": "mega_only"},      # conflict: observed wins
                9: {"restriction": "mega_only"}}      # not in table: ignored
    out, conflicts = apply_observed_restrictions(table, observed)
    assert out[1117] == table[1117]
    assert out[1229] == table[1229]
    assert out[7] == [{"kind": "heal", "amount": 60, "restriction": "mega_only"}]
    assert out[8] == table[8]
    assert conflicts == {7: [("active_only", "mega_only")]}
    assert 9 not in out


@pytest.mark.req("REQ-EFFECT-0015")
def test_apply_observed_with_nothing_observed_is_identity():
    table = {1: [{"kind": "heal", "amount": 30}]}
    out, conflicts = apply_observed_restrictions(table, {})
    assert out == table and conflicts == {}


# --- probe board pure helpers (REQ-EFFECT-0016) ---------------------------------------

def _pk(serial, cid, hp, max_hp):
    return {"id": cid, "serial": serial, "hp": hp, "maxHp": max_hp, "energies": []}


CARDS = {
    678: {"name": "Mega Lucario ex", "category": "pokemon", "stage": "stage1",
          "megaEx": True, "hp": 340, "retreat": 2, "energy": "fighting", "attacks": []},
    333: {"name": "Riolu", "category": "pokemon", "stage": "basic", "megaEx": False,
          "hp": 70, "retreat": 1, "energy": "fighting", "attacks": []},
    431: {"name": "TR Mewtwo ex", "category": "pokemon", "stage": "basic",
          "megaEx": False, "hp": 280, "retreat": 3, "energy": "psychic", "attacks": []},
    979: {"name": "Koraidon ex", "category": "pokemon", "stage": "basic",
          "megaEx": False, "hp": 230, "retreat": 2, "energy": "fighting", "attacks": []},
    28: {"name": "Poltchageist", "category": "pokemon", "stage": "basic",
         "megaEx": False, "hp": 60, "retreat": 1, "energy": "grass",
         "attacks": [{"name": "Splash", "damage": 10, "energies": [1], "text": ""}]},
    687: {"name": "Mega Absol ex", "category": "pokemon", "stage": "basic",
          "megaEx": True, "hp": 280, "retreat": 1, "energy": "darkness",
          "attacks": [{"name": "Chip", "damage": 20, "energies": [7], "text": ""}]},
    55: {"name": "Statusmon", "category": "pokemon", "stage": "basic", "megaEx": False,
         "hp": 100, "retreat": 1, "energy": "psychic",
         "attacks": [{"name": "Hypno", "damage": 10, "energies": [5],
                      "text": "The opponent is now Asleep."}]},
    1117: {"name": "Potion", "category": "item"},
    6: {"name": "Basic {F} Energy", "category": "basic_energy"},
}


def _obs(players, you=0, select=None, logs=None):
    return {"current": {"yourIndex": you, "result": -1, "players": players},
            "select": select or {"context": 0, "option": [], "minCount": 0, "maxCount": 0},
            "logs": logs or []}


def _players(active, bench):
    return [{"active": active, "bench": bench, "benchMax": 5},
            {"active": [], "bench": [], "benchMax": 5}]


@pytest.mark.req("REQ-EFFECT-0016")
def test_snapshot_board_flags_mega_active_damaged():
    obs = _obs(_players([_pk(21, 431, 270, 280)], [_pk(11, 678, 330, 340), _pk(31, 979, 230, 230)]))
    board = snapshot_board(obs, 0, CARDS)
    by_serial = {b["serial"]: b for b in board}
    assert by_serial[21]["active"] and not by_serial[21]["mega"] and by_serial[21]["damaged"]
    assert not by_serial[11]["active"] and by_serial[11]["mega"] and by_serial[11]["damaged"]
    assert not by_serial[31]["damaged"]
    # the snapshot + a real offer drive the derivation end to end
    assert derive_restriction(board, [11]) == {"restriction": "mega_only"}


@pytest.mark.req("REQ-EFFECT-0016")
def test_offered_heal_targets_resolves_my_card_options_to_serials():
    players = _players([_pk(21, 431, 270, 280)], [_pk(11, 678, 330, 340)])
    select = {"context": 17, "minCount": 1, "maxCount": 1, "option": [
        {"type": 3, "area": 4, "index": 0, "playerIndex": 0},     # my Active
        {"type": 3, "area": 5, "index": 0, "playerIndex": 0},     # my bench Mega
        {"type": 3, "area": 5, "index": 0, "playerIndex": 1},     # opponent's — not mine
        {"type": 3, "area": 2, "index": 0, "playerIndex": 0},     # HAND area — not in play
        {"type": 6, "area": 4, "index": 0, "playerIndex": 0},     # ENERGY option — not a target
    ]}
    assert offered_heal_targets(_obs(players, select=select), 0) == [21, 11]


@pytest.mark.req("REQ-EFFECT-0016")
def test_healed_serials_reads_actor_positive_non_counter_hp_changes():
    logs = [
        {"type": 16, "playerIndex": 0, "serial": 21, "value": 10, "putDamageCounter": False},
        {"type": 16, "playerIndex": 0, "serial": 22, "value": -30, "putDamageCounter": False},
        {"type": 16, "playerIndex": 0, "serial": 23, "value": 30, "putDamageCounter": True},
        {"type": 16, "playerIndex": 1, "serial": 24, "value": 40, "putDamageCounter": False},
        {"type": 4, "playerIndex": 0},
    ]
    assert healed_serials(logs, 0) == [21]


@pytest.mark.req("REQ-EFFECT-0016")
def test_find_chip_attacker_picks_a_small_vanilla_self_type_attack():
    cid, energy = find_chip_attacker(CARDS)
    assert cid == 28          # vanilla 10-damage; 687 is a Mega, 55 has effect text
    assert energy == 1        # its grass basic-Energy card


@pytest.mark.req("REQ-EFFECT-0016")
def test_pick_sturdies_excludes_megas_frail_and_line_names():
    got = pick_sturdies(CARDS, exclude_names={"Riolu", "Mega Lucario ex"})
    assert got and set(got) <= {431, 979}
    assert 678 not in got and 687 not in got and 333 not in got and 28 not in got
    # lowest retreat first (the case-B Active must retreat cheaply)
    assert got[0] == 979


@pytest.mark.req("REQ-EFFECT-0016")
def test_restriction_deck_is_legal_and_caps_ace_spec():
    deck = restriction_deck(1117, CARDS, chain=[333, 678], sturdies=[979, 431], energy=6)
    assert len(deck) == 60
    assert deck.count(1117) == 4 and deck.count(333) == 4 and deck.count(678) == 4
    assert deck.count(979) == 4 and deck.count(431) == 4
    ace = {**CARDS, 1096: {"name": "Poke Vital A", "category": "item", "aceSpec": True}}
    deck = restriction_deck(1096, ace, chain=[333, 678], sturdies=[979], energy=6)
    assert deck.count(1096) == 1 and len(deck) == 60
