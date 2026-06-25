"""Detecting which seat is our agent, by team name."""
from conftest import FIXTURES

from meta_tracker.parse import load_replay
from train.blunder.seats import detect_seat

FIXTURE = FIXTURES / "episode-81364540-replay.json.gz"   # TeamNames == ['Jaga', 'keidroid']


def test_detect_seat_matches_team_name():
    """REQ-BLUNDER-0007: our seat is found by matching our team name in info.TeamNames."""
    replay = load_replay(FIXTURE)
    assert detect_seat(replay, "keidroid") == 1
    assert detect_seat(replay, "Jaga") == 0


def test_detect_seat_is_case_insensitive():
    """REQ-BLUNDER-0007: matching is forgiving about case."""
    assert detect_seat(load_replay(FIXTURE), "KeiDroid") == 1


def test_detect_seat_none_when_absent():
    """REQ-BLUNDER-0007: unmatchable team -> None (caller falls back to manual pick)."""
    assert detect_seat(load_replay(FIXTURE), "SomeoneElse") is None
