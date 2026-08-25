import json

from common.telemetry import RecordAssembler, build_episode_receipt, build_outcome_record
from sim.artifacts import episode_id, save_legacy_telemetry, tag_replay
from train.blunder.batch import load_game
from train.blunder.seats import detect_seat


def test_episode_id_and_replay_tags_are_stable():
    assert episode_id("run", 0) == episode_id("run", 0)
    assert episode_id("run", 0) != episode_id("run", 1)
    replay = {"steps": [], "info": {"existing": 1}}
    tagged = tag_replay(replay, episode_id=42, team_names=["a", "b"])
    assert tagged["info"] == {"existing": 1, "EpisodeId": 42, "TeamNames": ["a", "b"]}
    assert detect_seat(tagged, "b") == 1


def test_legacy_telemetry_artifacts_remain_inspector_readable(tmp_path):
    replay = tmp_path / "42.json"
    replay.write_text("{}", encoding="utf-8")
    records = [{"chosen": [0], "seat": 0}, {"chosen": [1], "seat": 1}]
    save_legacy_telemetry(tmp_path, 42, records)
    assert load_game(replay)["live_records_by_seat"] == {0: [records[0]], 1: [records[1]]}


def test_legacy_telemetry_keeps_the_authoritative_episode_stream(tmp_path):
    receipt = build_episode_receipt(episode_key="42", reservations=[])
    outcome = build_outcome_record(
        episode_key="42", decision_records=[], telemetry_receipt=receipt,
        winner=None, terminal_reason="draw",
        public_prizes={0: 1, 1: 1}, rewards={0: 0.0, 1: 0.0}, duration_seconds=2.0,
        external_episode_id="42")
    save_legacy_telemetry(tmp_path, 42, [outcome])
    assembler = RecordAssembler()
    records = [record for line in (tmp_path / "episode-42-telemetry.jsonl").read_text().splitlines()
               if (record := assembler.ingest(line)) is not None]
    assert records == [outcome]
