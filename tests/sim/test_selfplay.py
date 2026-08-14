"""The self-play corpus generator saves Bellman-correction-readable mirror games."""
import json
import os
from datetime import datetime
from pathlib import Path

import pytest
from conftest import require_kaggle_environments

from sim.selfplay import _save_telemetry, episode_id, generate_corpus, run_stem, tag_replay
from train.blunder.decisions import iter_decisions
from train.blunder.batch import discover_replays, load_game
from train.blunder.provenance import build_identity
from train.blunder.seats import detect_seat

REPO = Path(__file__).resolve().parents[2]
FIXTURE_AGENTS = REPO / "tests" / "fixtures" / "agents"
WHEN = datetime(2026, 6, 29, 12, 0, 0)


@pytest.mark.req("REQ-SIM-0009")
def test_run_stem_is_resolvable_by_provenance():
    stem = run_stem("mega_starmie", WHEN, "577f603")
    bid = build_identity(f"data/replays/selfplay/{stem}/42.json")
    assert bid["agent"] == "mega_starmie"      # corrections auto-file under real build folder, not _UNFILED
    assert bid["agent_build"] == stem


@pytest.mark.req("REQ-SIM-0009")
def test_run_stem_distinguishes_an_overlay_corpus():
    base = run_stem("mega_starmie", WHEN, "577f603")
    ov = run_stem("mega_starmie", WHEN, "577f603", overlay="exp/cand.json")
    assert ov != base                                       # candidate corpus won't collide with baseline
    assert build_identity(f"x/{ov}/1.json")["agent"] == "mega_starmie"   # still provenance-resolvable


@pytest.mark.req("REQ-SIM-0009")
def test_episode_id_is_deterministic_and_globally_unique():
    s1 = run_stem("mega_starmie", WHEN, "577f603")
    s2 = run_stem("mega_starmie", datetime(2026, 6, 29, 13, 0, 0), "577f603")
    assert episode_id(s1, 0) == episode_id(s1, 0)   # deterministic (no clock dependency)
    assert episode_id(s1, 0) != episode_id(s1, 1)   # unique per game within a run
    assert episode_id(s1, 0) != episode_id(s2, 0)   # unique across runs (dedup/review needs it)
    assert isinstance(episode_id(s1, 0), int)       # info.EpisodeId is an int


@pytest.mark.req("REQ-SIM-0009")
def test_tag_replay_injects_ids_without_clobbering_the_film():
    replay = {"steps": [[{"visualize": [{"current": {}}]}]], "info": {"existing": 1}}
    tagged = tag_replay(replay, episode_id=12345, team_names=["ms#0", "ms#1"])
    assert tagged["info"]["EpisodeId"] == 12345
    assert tagged["info"]["existing"] == 1          # prior info preserved
    assert tagged["steps"] == replay["steps"]       # film untouched
    assert detect_seat(tagged, "ms#1") == 1         # inspector resolves seat from injected TeamNames


@pytest.mark.req("REQ-SIM-0009")
def test_generate_corpus_saves_bellman_correction_replays(tmp_path):
    require_kaggle_environments()
    run_dir = generate_corpus("mega_starmie", 2, agents_root=FIXTURE_AGENTS, out_root=tmp_path,
                              when=WHEN, sha="abc1234", syspath_roots=[REPO / "src"])
    files = discover_replays(run_dir)
    assert len(files) == 2                                  # every game saved
    assert build_identity(files[0])["agent"] == "mega_starmie"   # path resolves -> not _UNFILED
    replay = json.loads(files[0].read_text(encoding="utf-8"))
    decisions = iter_decisions(replay)
    assert decisions                                       # film yields taggable decisions
    assert any(d.obs is not None for d in decisions)


def test_save_telemetry_writes_seat_specific_inspector_logs(tmp_path):
    line0 = '@T {"chosen":[0],"seat":0}'
    line1 = '@T {"chosen":[1],"seat":1}'
    replay = tmp_path / "42.json"
    replay.write_text("{}", encoding="utf-8")

    _save_telemetry(tmp_path, 42, [json.loads(line0[3:]), json.loads(line1[3:])])

    game = load_game(replay)
    assert game["live_records"] == [{"chosen": [0], "seat": 0}]
    assert game["live_seat"] == 0


@pytest.mark.req("REQ-SIM-0009")
def test_generate_corpus_exposes_overlay_to_games_and_restores_env(tmp_path, monkeypatch):
    seen = []

    class _FakeEnv:
        def toJSON(self):
            return {"steps": [[{"visualize": []}]], "info": {}}

    def fake_run_match(agent_dir, syspath_roots):
        seen.append(os.environ.get("AGENT_OVERLAY"))       # what each game sees at import
        return (["DONE", "DONE"], _FakeEnv())

    monkeypatch.setattr("sim.check_agent._run_match", fake_run_match)
    monkeypatch.delenv("AGENT_OVERLAY", raising=False)
    overlay = tmp_path / "ov.json"
    overlay.write_text("{}", encoding="utf-8")

    generate_corpus("mega_starmie", 2, agents_root=FIXTURE_AGENTS, out_root=tmp_path,
                    when=WHEN, sha="abc", overlay=str(overlay))
    assert seen == [str(overlay.resolve())] * 2            # every game saw the overlay (absolute path)
    assert "AGENT_OVERLAY" not in os.environ               # restored after run -> no leak to later code
