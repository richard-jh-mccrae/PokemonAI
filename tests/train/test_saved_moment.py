from pathlib import Path

from train.saved_moment import load_saved_episode, parse_frame_key, resolve_saved_moment


FIXTURE = Path(__file__).parents[1] / "fixtures" / "match-replay.json"


def test_resolves_replay_frame_through_shared_saved_moment_seam():
    moment = resolve_saved_moment(81876998, 0, replay_path=FIXTURE)

    assert moment.episode_id == 81876998
    assert moment.frame == 0
    assert moment.source_path == FIXTURE
    assert moment.full_info is True
    assert moment.current["turn"] == 0


def test_parses_saved_moment_key():
    assert parse_frame_key("ep81876998 f12") == (81876998, 12)


def test_saved_episode_exposes_agent_decisions_and_deck_provenance():
    episode = load_saved_episode(FIXTURE)
    observation = episode.agent_observation(0, 0)

    assert episode.episode_id == 81876998
    assert episode.source_path == FIXTURE
    assert len(episode.source_sha256) == 64
    assert tuple(map(len, episode.decks)) == (60, 60)
    assert observation["step"] == 0
    assert observation["current"] is None

    observation["step"] = 999
    assert episode.agent_observation(0, 0)["step"] == 0


def test_saved_episode_rejects_invalid_agent_decision_coordinates():
    episode = load_saved_episode(FIXTURE)

    for step, seat in ((-1, 0), (0, 2), (999, 0)):
        try:
            episode.agent_observation(step, seat)
        except LookupError:
            pass
        else:
            raise AssertionError((step, seat))
