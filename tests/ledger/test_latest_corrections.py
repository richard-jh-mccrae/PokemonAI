from pathlib import Path

import pytest

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


def replay_frame(frame):
    result = sweep(
        store=CORRECTIONS,
        decks=("dragapult_ex", "mega_starmie"),
        correction_filter=lambda correction: correction.decision.get("frame") == frame,
    )
    [row] = result["rows"]
    return row


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
    result = sweep(
        store=WIN_CORRECTIONS,
        decks=("dragapult_ex", "mega_starmie"),
        correction_filter=lambda correction: correction.decision.get("frame") in {75, 86},
    )

    assert len(result["rows"]) == 2
    assert all(row["graded"] for row in result["rows"]), result["rows"]
    assert all(row["agrees"] for row in result["rows"]), result["rows"]


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
    result = sweep(
        store=LUCARIO_CORRECTIONS,
        decks=("mega_lucario",),
        correction_filter=lambda correction: correction.decision.get("frame") == 21,
    )
    [row] = result["rows"]

    assert row["graded"]
    assert row["agrees"], row


def test_trainer_fetch_values_its_feasible_downstream_line():
    result = sweep(
        store=LUCARIO_CORRECTIONS,
        decks=("mega_lucario",),
        correction_filter=lambda correction: correction.decision.get("frame") == 38,
    )
    [row] = result["rows"]

    assert row["graded"]
    assert row["agrees"], row


def test_positive_dead_hand_refresh_precedes_minor_item_value():
    result = sweep(
        store=LUCARIO_CORRECTIONS,
        decks=("mega_lucario",),
        correction_filter=lambda correction: correction.decision.get("frame") == 77,
    )
    [row] = result["rows"]

    assert row["graded"]
    assert row["agrees"], row


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


def test_first_turn_switch_does_not_promote_future_combat_to_immediate_value():
    result = sweep(
        store=LUCARIO_CORRECTIONS,
        decks=("mega_lucario",),
        correction_filter=lambda correction: correction.decision.get("frame") == 5,
    )
    [row] = result["rows"]

    assert row["graded"]
    assert row["agrees"], row


@pytest.mark.parametrize(("store", "deck", "frame"), (
    (EARLIER_LUCARIO_CORRECTIONS, "mega_lucario", 9),
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


def test_darkness_is_not_attached_to_drakloak_for_a_colorless_side_attack():
    row = replay_frame(83)

    assert row["graded"]
    assert row["agrees"], row


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


@pytest.mark.parametrize("frame", (8, 30, 83, 107, 123, 125, 150))
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
