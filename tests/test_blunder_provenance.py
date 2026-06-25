"""Deriving the agent build identity from a replay's submission-folder path (ADR-0018)."""
from train.blunder.provenance import build_identity


def test_build_identity_parses_stem_with_date_time_and_dirty_sha():
    """REQ-BLUNDER-0015: the build identity is read off the submission folder
    `<agent>_<YYYYMMDD-HHMMSS>_<sha>[-dirty]` on the replay's path."""
    bid = build_identity("submissions/mega_starmie_20260625-034931_623a009-dirty/replays/81785223.json")
    assert bid["agent_build"] == "mega_starmie_20260625-034931_623a009-dirty"
    assert bid["agent_version"] == "623a009-dirty"
    assert bid["built_at"] == "2026-06-25T03:49:31"


def test_build_identity_parses_date_only_stem():
    """REQ-BLUNDER-0015: the deploy-stem form `<agent>_<YYYYMMDD>_<sha>` also parses."""
    bid = build_identity("submissions/mega_starmie_20260625_623ea73/replays/1.json")
    assert bid["agent_version"] == "623ea73"
    assert bid["built_at"] == "2026-06-25T00:00:00"


def test_build_identity_is_null_when_no_submission_stem_on_path():
    """REQ-BLUNDER-0015: a replay not under a submission stem yields a null identity, not an error."""
    bid = build_identity("tests/fixtures/episode-81364540-replay.json.gz")
    assert bid["agent_build"] is None and bid["agent_version"] is None and bid["built_at"] is None
