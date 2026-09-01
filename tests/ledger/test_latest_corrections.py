from pathlib import Path

import pytest

from train.blunder.reviewed import load_reviewed, review_key
from train.blunder.store import load_corrections
from train.ledger_corpus import sweep


CORRECTIONS = (Path(__file__).parents[2] / "data" / "corrections"
               / "20260830-104048_1ea82212_mega_starmie")
KO_CORRECTIONS = (Path(__file__).parents[2] / "data" / "corrections"
                  / "20260830-185708_2aecef25_mega_starmie")
LUCARIO_CORRECTIONS = (Path(__file__).parents[2] / "data" / "corrections"
                       / "20260830-172634_2aecef25_mega_lucario")
EARLIER_LUCARIO_CORRECTIONS = (Path(__file__).parents[2] / "data" / "corrections"
                               / "20260830-083418_d00f93d6_mega_lucario")
EARLIER_DRAGAPULT_CORRECTIONS = (Path(__file__).parents[2] / "data" / "corrections"
                                / "20260830-083953_d00f93d6_dragapult_ex")
WIN_CORRECTIONS = (Path(__file__).parents[2] / "data" / "corrections"
                   / "20260831-051533_d74ec20f_mega_starmie")
NEW_LUCARIO_CORRECTIONS = (Path(__file__).parents[2] / "data" / "corrections"
                           / "20260831-120851_7d11660f_mega_lucario")
NEW_STARMIE_CORRECTIONS = (Path(__file__).parents[2] / "data" / "corrections"
                          / "20260831-124008_7d11660f_mega_starmie")
SEPTEMBER_LUCARIO_CORRECTIONS = (
    Path(__file__).parents[2] / "data" / "corrections"
    / "20260901-065330_58f85282_mega_lucario")
SEPTEMBER_DRAGAPULT_CORRECTIONS = (
    Path(__file__).parents[2] / "data" / "corrections"
    / "20260901-075825_58f85282_dragapult_ex")


def replay_frame(frame):
    result = sweep(
        store=CORRECTIONS,
        decks=("dragapult_ex", "mega_starmie"),
        correction_filter=lambda correction: correction.decision.get("frame") == frame,
    )
    [row] = result["rows"]
    return row


def assert_deferred(store, frame, *, disposition="deferred-multi-turn"):
    correction = next(
        correction for correction in load_corrections(store)
        if correction.decision.get("frame") == frame)
    assert load_reviewed()[review_key(correction)]["disposition"] == disposition


def test_turbo_flare_ko_beats_negative_setup_and_end():
    result = sweep(
        store=KO_CORRECTIONS,
        decks=("mega_starmie",),
        correction_filter=lambda correction: correction.decision.get("frame") == 20,
    )
    [row] = result["rows"]

    assert row["graded"]
    assert row["agrees"], row


def test_lethal_attachment_is_taken_before_the_winning_attack():
    result = sweep(
        store=WIN_CORRECTIONS,
        decks=("mega_starmie",),
        correction_filter=lambda correction: correction.decision.get("frame") == 163,
    )
    [row] = result["rows"]

    assert row["graded"]
    assert row["agrees"], row


def test_bench_damage_targets_developed_attackers():
    assert_deferred(WIN_CORRECTIONS, 75)
    assert_deferred(WIN_CORRECTIONS, 86)


@pytest.mark.parametrize("frame", (35, 117))
def test_development_targets_the_invested_body(frame):
    result = sweep(
        store=WIN_CORRECTIONS,
        decks=("dragapult_ex",),
        correction_filter=lambda correction: correction.decision.get("frame") == frame,
    )
    [row] = result["rows"]

    assert row["graded"]
    assert row["agrees"], row


def test_ready_game_winning_attack_ends_the_game_now():
    result = sweep(
        store=WIN_CORRECTIONS,
        decks=("mega_starmie",),
        correction_filter=lambda correction: correction.decision.get("frame") == 153,
        reviewed={},
    )
    [row] = result["rows"]

    assert row["graded"]
    assert row["chosen"] == [10], row


def test_looking_selection_uses_the_revealed_card_identity():
    result = sweep(
        store=LUCARIO_CORRECTIONS,
        decks=("dragapult_ex", "mega_lucario"),
        correction_filter=lambda correction: correction.decision.get("frame") == 28,
    )
    [row] = result["rows"]

    assert row["graded"]
    assert row["agrees"], row


def test_deck_only_energy_does_not_enable_an_immediate_ability():
    result = sweep(
        store=LUCARIO_CORRECTIONS,
        decks=("dragapult_ex",),
        correction_filter=lambda correction: correction.decision.get("frame") == 30,
    )
    [row] = result["rows"]

    assert row["graded"]
    assert row["agrees"], row


def test_cost_free_draw_ability_precedes_evolution():
    result = sweep(
        store=LUCARIO_CORRECTIONS,
        decks=("dragapult_ex",),
        correction_filter=lambda correction: correction.decision.get("frame") == 78,
    )
    [row] = result["rows"]

    assert row["graded"]
    assert row["agrees"], row


def test_doomed_active_keeps_its_immediate_denial_attack():
    result = sweep(
        store=LUCARIO_CORRECTIONS,
        decks=("dragapult_ex",),
        correction_filter=lambda correction: correction.decision.get("frame") == 16,
    )
    [row] = result["rows"]

    assert row["graded"]
    assert row["agrees"], row


def test_gust_must_improve_the_attack_target_enough_to_spend_it():
    assert_deferred(LUCARIO_CORRECTIONS, 21)


def test_chained_trainer_fetch_waits_for_turn_planning():
    assert_deferred(LUCARIO_CORRECTIONS, 38)


def test_refresh_for_a_later_evolution_waits_for_turn_planning():
    assert_deferred(LUCARIO_CORRECTIONS, 77)


def test_lethal_damage_boost_is_played_before_attacking():
    result = sweep(
        store=LUCARIO_CORRECTIONS,
        decks=("mega_lucario",),
        correction_filter=lambda correction: correction.decision.get("frame") == 42,
    )
    [row] = result["rows"]

    assert row["graded"]
    assert row["agrees"], row


def test_dead_hand_refresh_preserves_the_loaded_attack_line():
    result = sweep(
        store=LUCARIO_CORRECTIONS,
        decks=("mega_lucario",),
        correction_filter=lambda correction: correction.decision.get("frame") == 81,
    )
    [row] = result["rows"]

    assert row["graded"]
    assert row["agrees"], row


def test_first_turn_switch_ruling_is_covered_by_preserving_the_active():
    result = sweep(
        store=LUCARIO_CORRECTIONS,
        decks=("mega_lucario",),
        correction_filter=lambda correction: correction.decision.get("frame") == 5,
    )
    assert result["rows"] == []
    [row] = result["retired"]

    assert row["disposition"] == "covered"


@pytest.mark.parametrize(("store", "deck", "frame"), (
    (EARLIER_LUCARIO_CORRECTIONS, "mega_lucario", 29),
    (EARLIER_DRAGAPULT_CORRECTIONS, "dragapult_ex", 10),
))
def test_sequence_and_discard_regressions_stay_fixed(store, deck, frame):
    result = sweep(
        store=store,
        decks=(deck,),
        correction_filter=lambda correction: correction.decision.get("frame") == frame,
    )
    [row] = result["rows"]

    assert row["graded"]
    assert row["agrees"], row


def test_play_before_retreat_ruling_waits_for_turn_search():
    assert_deferred(EARLIER_LUCARIO_CORRECTIONS, 9)


def test_darkness_is_not_attached_to_drakloak_for_a_colorless_side_attack():
    assert_deferred(CORRECTIONS, 83, disposition="covered")


def test_dudunsparce_draw_and_recycle_is_used_before_ending_the_turn():
    row = replay_frame(36)

    assert row["graded"]
    assert row["agrees"], row


def test_salvatore_precedes_retreat_when_it_unlocks_the_attacking_evolution():
    row = replay_frame(17)

    assert row["graded"]
    assert row["agrees"], row


@pytest.mark.parametrize("frame", (75, 76))
def test_nebula_beam_damages_the_loaded_active_threat(frame):
    row = replay_frame(frame)

    assert row["graded"]
    assert row["agrees"], row


def test_ready_knockout_policy_supersedes_the_old_negative_evolve_ruling():
    row = replay_frame(37)

    assert row["graded"], row
    assert row["chosen"] != [1], row
    assert not row["agrees"], row


def test_poffin_and_hammer_are_both_accepted_before_hand_disruption():
    row = replay_frame(55)

    assert row["acceptable"] == [[3], [2]]
    assert row["graded"]
    assert row["agrees"], row


@pytest.mark.parametrize("frame", (54, 89, 124))
def test_new_lucario_atomic_corrections(frame):
    result = sweep(
        store=NEW_LUCARIO_CORRECTIONS,
        decks=("dragapult_ex", "mega_lucario"),
        correction_filter=lambda correction: correction.decision.get("frame") == frame,
        reviewed={},
    )
    [row] = result["rows"]

    assert row["graded"], row
    assert row["agrees"], row


@pytest.mark.parametrize(("frame", "condemned"), ((26, [12]), (144, [7])))
def test_new_lucario_covered_defects_are_not_repeated(frame, condemned):
    result = sweep(
        store=NEW_LUCARIO_CORRECTIONS,
        decks=("dragapult_ex", "mega_lucario"),
        correction_filter=lambda correction: correction.decision.get("frame") == frame,
        reviewed={},
    )
    [row] = result["rows"]

    assert row["graded"], row
    assert row["chosen"] != condemned, row


@pytest.mark.parametrize("frame", (8, 83, 107, 123, 125, 150))
def test_new_starmie_atomic_corrections(frame):
    result = sweep(
        store=NEW_STARMIE_CORRECTIONS,
        decks=("dragapult_ex", "mega_starmie"),
        correction_filter=lambda correction: correction.decision.get("frame") == frame,
        reviewed={},
    )
    [row] = result["rows"]

    assert row["graded"], row
    assert row["agrees"], row


def test_future_munkidori_ability_attachment_waits_for_turn_search():
    assert_deferred(NEW_STARMIE_CORRECTIONS, 30)


def test_second_ultra_ball_discard_defect_is_not_repeated():
    result = sweep(
        store=SEPTEMBER_LUCARIO_CORRECTIONS,
        decks=("mega_lucario",),
        correction_filter=lambda correction: correction.decision.get("frame") == 42,
        reviewed={},
    )
    [row] = result["rows"]

    assert row["graded"], row
    assert 6 not in row["chosen"], row


def test_multiple_later_bench_vacancies_wait_for_turn_search():
    assert_deferred(SEPTEMBER_DRAGAPULT_CORRECTIONS, 135)
