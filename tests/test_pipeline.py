"""End-to-end orchestration with the Kaggle CLI mocked (no network).

Drives run_daily against a canned leaderboard + episodes index + daily dataset
file (the gzipped sample replay), exercising rating->band, extract, dedup, and
the dataset-complete short-circuit.
"""
import gzip
from pathlib import Path

import pytest
from conftest import FIXTURES

from meta_tracker import config, run_daily

FIXTURE = FIXTURES / "episode-81364540-replay.json.gz"
EP_ID = 81364540  # Jaga vs keidroid


@pytest.fixture
def mocked(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "meta.db")
    monkeypatch.setattr(config, "DASHBOARD", tmp_path / "dash.html")

    # Jaga & keidroid at the top so the episode bands as Elite.
    lb = [{"rank": 1, "teamId": 1, "teamName": "Jaga", "score": 1367.0},
          {"rank": 2, "teamId": 2, "teamName": "keidroid", "score": 1323.0}]
    lb += [{"rank": i, "teamId": i, "teamName": f"t{i}", "score": float(1300 - i * 7)}
           for i in range(3, 101)]
    monkeypatch.setattr(run_daily.fetch, "leaderboard", lambda *a, **k: lb)
    monkeypatch.setattr(run_daily.fetch, "episodes_index",
                        lambda: [{"date": "2026-06-22", "slug": "daily-2026-06-22", "episode_count": 1}])
    # one page, no next token -> day gets marked complete
    monkeypatch.setattr(run_daily.fetch, "dataset_episode_page",
                        lambda slug, token=None, page_size=200: ([EP_ID], None))

    def fake_download(slug, eid, dest):
        out = Path(dest) / f"{eid}.json"
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as fin:
            out.write_text(fin.read(), encoding="utf-8")
        return out

    monkeypatch.setattr(run_daily.fetch, "download_dataset_episode", fake_download)
    return tmp_path


def test_pipeline_pulls_bands_and_builds_dashboard(mocked):
    res = run_daily.run(episode_cap=10, verbose=False)
    assert res["added"] == 1                  # one episode, banded into the kept range
    assert res["total"] == 1
    assert (mocked / "dash.html").exists()


def test_pipeline_idempotent_via_dataset_complete(mocked):
    run_daily.run(episode_cap=10, verbose=False)
    res2 = run_daily.run(episode_cap=10, verbose=False)
    assert res2["added"] == 0                  # dataset marked complete -> skipped
    assert res2["total"] == 1


def test_pipeline_stops_cleanly_on_rate_limit(monkeypatch, mocked):
    def boom(slug, token=None, page_size=200):
        raise run_daily.fetch.RateLimitError("rate-limited (403)")
    monkeypatch.setattr(run_daily.fetch, "dataset_episode_page", boom)
    res = run_daily.run(episode_cap=10, verbose=False)
    assert res["added"] == 0          # stopped gracefully, no crash, dashboard still built
    assert (mocked / "dash.html").exists()


def test_pipeline_off_band_episode_dropped(monkeypatch, mocked):
    # Drop Jaga/keidroid to the bottom so the episode falls below the kept range.
    lb = [{"rank": i, "teamId": i, "teamName": f"t{i}", "score": float(1400 - i)} for i in range(1, 99)]
    lb += [{"rank": 99, "teamId": 99, "teamName": "Jaga", "score": 605.0},
           {"rank": 100, "teamId": 100, "teamName": "keidroid", "score": 602.0}]
    monkeypatch.setattr(run_daily.fetch, "leaderboard", lambda *a, **k: lb)
    res = run_daily.run(episode_cap=10, verbose=False)
    assert res["added"] == 0 and res["filtered"] == 1   # below 50th percentile -> dropped
