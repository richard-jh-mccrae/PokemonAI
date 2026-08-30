from pathlib import Path

import pytest

from train.ledger_corpus import sweep


CORRECTIONS = (Path(__file__).parents[2] / "data" / "corrections"
               / "20260830-104048_1ea82212_mega_starmie")


def replay_frame(frame):
    result = sweep(
        store=CORRECTIONS,
        decks=("dragapult_ex", "mega_starmie"),
        correction_filter=lambda correction: correction.decision.get("frame") == frame,
    )
    [row] = result["rows"]
    return row


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


def test_turbo_flare_preview_finishes_before_comparing_it_to_evolution():
    row = replay_frame(37)

    assert row["graded"], row
    assert row["agrees"], row


def test_poffin_and_hammer_are_both_accepted_before_hand_disruption():
    row = replay_frame(55)

    assert row["acceptable"] == [[3], [2]]
    assert row["graded"]
    assert row["agrees"], row
