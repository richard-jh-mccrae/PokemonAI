"""Replay parsing against the gzipped sample fixture (episode 81364540)."""
from conftest import FIXTURES

from meta_tracker.parse import extract_decks, load_replay, parse_replay, winner_index

FIXTURE = FIXTURES / "episode-81364540-replay.json.gz"


def test_extract_full_decks():
    replay = load_replay(FIXTURE)
    d0, d1 = extract_decks(replay)
    assert len(d0) == 60 and len(d1) == 60
    assert all(isinstance(c, int) for c in d0 + d1)


def test_winner_from_rewards():
    assert winner_index(load_replay(FIXTURE)) == 0  # rewards [1, -1]


def test_parse_record_fields():
    rec = parse_replay(FIXTURE, band="Elite", sampled_team="keidroid",
                       sampled_rating=1367.5, sampled_episodes=165)
    assert rec.episode_id == 81364540
    assert {rec.team0, rec.team1} == {"Jaga", "keidroid"}
    assert rec.winner_index == 0
    assert rec.team1 == "keidroid" and rec.sampled_index == 1  # sampled team -> its side
    assert rec.band == "Elite" and rec.sampled_rating == 1367.5


def test_parse_archetypes_present():
    rec = parse_replay(FIXTURE, sampled_team="keidroid")
    keid = rec.arch0 if rec.team0 == "keidroid" else rec.arch1
    assert "Cinderace" in keid and "Mega Starmie ex" in keid


def test_sampled_index_none_when_team_absent():
    rec = parse_replay(FIXTURE, sampled_team="nobody")
    assert rec.sampled_index is None
