"""Pure parsing logic in fetch (no network)."""
import pytest

from meta_tracker import fetch
from meta_tracker.fetch import _parse_csv


def test_parse_csv_basic():
    rows = _parse_csv("id,dateSubmitted,publicScore\n1,2026-06-21,955.5\n2,2026-06-22,1367.5\n")
    assert len(rows) == 2 and rows[1]["publicScore"] == "1367.5"


def test_parse_csv_skips_page_token_preamble():
    txt = 'Next Page Token = ABC123\nteamId,teamName,score\n10,"A, B",1200\n'
    rows = _parse_csv(txt)
    assert rows[0]["teamName"] == "A, B" and rows[0]["teamId"] == "10"  # quoted comma kept


def test_parse_csv_empty():
    assert _parse_csv("") == []


def test_dataset_episode_page_parses_ids_and_token(monkeypatch):
    monkeypatch.setattr(fetch, "_run", lambda args:
                        "Next Page Token = TOK\nname,size,creationDate\n"
                        "81.json,100,t\n82.json,200,t\nmanifest.csv,10,t\n")  # non-<id>.json filtered
    ids, token = fetch.dataset_episode_page("slug")
    assert ids == [81, 82] and token == "TOK"


def test_dataset_episode_page_last_page_has_no_token(monkeypatch):
    monkeypatch.setattr(fetch, "_run", lambda args: "name,size,creationDate\n99.json,1,t\n")
    ids, token = fetch.dataset_episode_page("slug", page_token="prev")
    assert ids == [99] and token is None


def test_manifest_slug_is_owner_qualified():
    # Regression: the CLI 403s on an unqualified slug; we must keep the owner.
    row = {"daily_dataset_slug": "pokemon-tcg-ai-battle-episodes-2026-06-22",
           "daily_dataset_url": "https://www.kaggle.com/datasets/kaggle/pokemon-tcg-ai-battle-episodes-2026-06-22"}
    assert fetch._manifest_slug(row) == "kaggle/pokemon-tcg-ai-battle-episodes-2026-06-22"
    # Fallback to kaggle/ owner when URL is missing.
    assert fetch._manifest_slug({"daily_dataset_slug": "foo"}) == "kaggle/foo"
    assert fetch._manifest_slug({}) is None


def test_run_raises_ratelimit_on_403(monkeypatch):
    class P:
        returncode, stdout = 1, ""
        stderr = "403 Client Error: Forbidden for url: .../ListDatasetFiles"
    monkeypatch.setattr(fetch.subprocess, "run", lambda *a, **k: P())
    monkeypatch.setattr(fetch.time, "sleep", lambda s: None)
    with pytest.raises(fetch.RateLimitError):
        fetch._run(["datasets", "files", "x", "-v"])  # no retry-storm on a 403
