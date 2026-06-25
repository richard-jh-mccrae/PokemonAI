"""SQLite store: dedup, incremental state, round-trip."""
from meta_tracker.parse import EpisodeRecord
from meta_tracker.store import (connect, dataset_complete, episode_exists, get_dataset_cursor,
                                get_last_episode, load_episodes, mark_dataset_complete, reclassify,
                                save_dataset_cursor, set_last_episode, upsert_episode)


def _rec(eid=1):
    return EpisodeRecord(
        episode_id=eid, band="Elite", created_at="2026-06-22 10:00:00", end_time="2026-06-22 10:02:00",
        team0="A", team1="B", winner_index=0, sampled_index=1, sampled_rating=1200.0,
        sampled_sub_date="2026-06-21", sampled_episodes=42,
        deck0=[1030, 1031], deck1=[666], arch0="Mega Starmie ex", arch1="Cinderace",
        mains0=["Mega Starmie ex"], mains1=["Cinderace"], subs0=[], subs1=[],
        energy0=["water"], energy1=["fire"])


def test_upsert_dedups_by_episode_id(tmp_path):
    conn = connect(tmp_path / "t.db")
    assert upsert_episode(conn, _rec(1), "2026-06-22") is True
    assert upsert_episode(conn, _rec(1), "2026-06-22") is False   # duplicate ignored
    assert episode_exists(conn, 1) and not episode_exists(conn, 2)


def test_round_trip_decodes_json(tmp_path):
    conn = connect(tmp_path / "t.db")
    upsert_episode(conn, _rec(7), "2026-06-22")
    (row,) = load_episodes(conn)
    assert row["deck0"] == [1030, 1031] and row["mains1"] == ["Cinderace"]
    assert row["sampled_team"] == "B"          # derived from sampled_index=1
    assert row["winner_index"] == 0


def test_reclassify_recomputes_from_decks(tmp_path):
    conn = connect(tmp_path / "t.db")
    r = _rec(1)
    r.arch0, r.mains0 = "STALE", ["STALE"]      # pretend old logic mislabeled it
    upsert_episode(conn, r, "2026-06-22")
    assert reclassify(conn) == 1
    (row,) = load_episodes(conn)
    assert row["arch0"] == "Mega Starmie ex"    # recomputed from deck0 = [Staryu, Mega Starmie ex]
    assert row["mains0"] == ["Mega Starmie ex"]


def test_dataset_complete_flag(tmp_path):
    conn = connect(tmp_path / "t.db")
    assert not dataset_complete(conn, "daily-2026-06-22")
    mark_dataset_complete(conn, "daily-2026-06-22", "2026-06-23")
    assert dataset_complete(conn, "daily-2026-06-22")


def test_dataset_cursor_resume(tmp_path):
    conn = connect(tmp_path / "t.db")
    assert get_dataset_cursor(conn, "d") is None
    save_dataset_cursor(conn, "d", "TOK1", "2026-06-23")
    assert get_dataset_cursor(conn, "d") == "TOK1"
    save_dataset_cursor(conn, "d", None, "2026-06-23")   # exhausted -> None
    assert get_dataset_cursor(conn, "d") is None


def test_incremental_state(tmp_path):
    conn = connect(tmp_path / "t.db")
    assert get_last_episode(conn, 555) is None
    set_last_episode(conn, 555, 81000, "2026-06-22")
    assert get_last_episode(conn, 555) == 81000
    set_last_episode(conn, 555, 81500, "2026-06-22")
    assert get_last_episode(conn, 555) == 81500
