from pathlib import Path

from train.saved_moment import parse_frame_key, resolve_saved_moment


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
