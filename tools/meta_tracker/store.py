"""SQLite extract store.

One row per Episode (deduped by ``episode_id``), plus a tiny table tracking the
newest Episode already pulled per submission so daily runs stay incremental.
Decklists are kept as JSON so archetype logic can be recomputed later; the raw
replay is not retained (ADR-0002).
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from . import config
from .parse import EpisodeRecord

_JSON_FIELDS = ("deck0", "deck1", "mains0", "mains1", "subs0", "subs1", "energy0", "energy1")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes (
    episode_id      INTEGER PRIMARY KEY,
    band            TEXT,
    created_at      TEXT,
    end_time        TEXT,
    team0           TEXT,
    team1           TEXT,
    winner_index    INTEGER,
    sampled_index   INTEGER,
    sampled_team    TEXT,
    sampled_rating  REAL,
    sampled_sub_date TEXT,
    sampled_episodes INTEGER,
    deck0 TEXT, deck1 TEXT,
    arch0 TEXT, arch1 TEXT,
    mains0 TEXT, mains1 TEXT,
    subs0 TEXT, subs1 TEXT,
    energy0 TEXT, energy1 TEXT,
    ingested_date   TEXT
);
CREATE INDEX IF NOT EXISTS idx_band ON episodes(band);
CREATE INDEX IF NOT EXISTS idx_end_time ON episodes(end_time);

CREATE TABLE IF NOT EXISTS seen_submissions (
    submission_id   INTEGER PRIMARY KEY,
    last_episode_id INTEGER,
    last_seen       TEXT
);

CREATE TABLE IF NOT EXISTS seen_datasets (
    slug       TEXT PRIMARY KEY,
    complete   INTEGER DEFAULT 0,
    page_token TEXT,
    last_seen  TEXT
);
"""


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else config.DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    try:  # migrate older DBs created before the cursor column existed
        conn.execute("ALTER TABLE seen_datasets ADD COLUMN page_token TEXT")
    except sqlite3.OperationalError:
        pass
    return conn


def episode_exists(conn: sqlite3.Connection, episode_id: int) -> bool:
    return conn.execute("SELECT 1 FROM episodes WHERE episode_id=?", (episode_id,)).fetchone() is not None


def upsert_episode(conn: sqlite3.Connection, rec: EpisodeRecord, ingested_date: str) -> bool:
    """Insert an episode; return False if it was already present (deduped)."""
    d = rec.as_dict()
    for f in _JSON_FIELDS:
        d[f] = json.dumps(d[f])
    d["sampled_team"] = (rec.team0 if rec.sampled_index == 0
                         else rec.team1 if rec.sampled_index == 1 else None)
    d["ingested_date"] = ingested_date
    cols = ",".join(d.keys())
    ph = ",".join("?" for _ in d)
    cur = conn.execute(f"INSERT OR IGNORE INTO episodes ({cols}) VALUES ({ph})", list(d.values()))
    conn.commit()
    return cur.rowcount > 0


def get_last_episode(conn: sqlite3.Connection, submission_id: int) -> int | None:
    row = conn.execute("SELECT last_episode_id FROM seen_submissions WHERE submission_id=?",
                       (submission_id,)).fetchone()
    return row[0] if row else None


def set_last_episode(conn: sqlite3.Connection, submission_id: int, episode_id: int, when: str) -> None:
    conn.execute(
        "INSERT INTO seen_submissions (submission_id, last_episode_id, last_seen) VALUES (?,?,?) "
        "ON CONFLICT(submission_id) DO UPDATE SET last_episode_id=excluded.last_episode_id, "
        "last_seen=excluded.last_seen",
        (submission_id, episode_id, when))
    conn.commit()


def dataset_complete(conn: sqlite3.Connection, slug: str) -> bool:
    row = conn.execute("SELECT complete FROM seen_datasets WHERE slug=?", (slug,)).fetchone()
    return bool(row and row[0])


def mark_dataset_complete(conn: sqlite3.Connection, slug: str, when: str) -> None:
    conn.execute(
        "INSERT INTO seen_datasets (slug, complete, last_seen) VALUES (?,1,?) "
        "ON CONFLICT(slug) DO UPDATE SET complete=1, last_seen=excluded.last_seen", (slug, when))
    conn.commit()


def get_dataset_cursor(conn: sqlite3.Connection, slug: str) -> str | None:
    """Resume token for the next file-listing page of a daily dataset (None = start)."""
    row = conn.execute("SELECT page_token FROM seen_datasets WHERE slug=?", (slug,)).fetchone()
    return row[0] if row else None


def save_dataset_cursor(conn: sqlite3.Connection, slug: str, token: str | None, when: str) -> None:
    conn.execute(
        "INSERT INTO seen_datasets (slug, page_token, last_seen) VALUES (?,?,?) "
        "ON CONFLICT(slug) DO UPDATE SET page_token=excluded.page_token, "
        "last_seen=excluded.last_seen", (slug, token, when))
    conn.commit()


def load_episodes(conn: sqlite3.Connection) -> list[dict]:
    """All episodes as plain dicts, with JSON fields decoded."""
    rows = conn.execute("SELECT * FROM episodes").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        for f in _JSON_FIELDS:
            d[f] = json.loads(d[f]) if d[f] else []
        out.append(d)
    return out


def episode_count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]


def reclassify(conn: sqlite3.Connection) -> int:
    """Recompute archetypes from the stored decklists using current logic.

    Possible because decks (not just labels) are retained — lets archetype/engine
    tweaks apply to history without re-downloading. Returns rows updated.
    """
    from .archetype import classify
    rows = conn.execute("SELECT episode_id, deck0, deck1 FROM episodes").fetchall()
    n = 0
    for r in rows:
        a0 = classify(json.loads(r["deck0"]))
        a1 = classify(json.loads(r["deck1"]))
        conn.execute(
            "UPDATE episodes SET arch0=?, arch1=?, mains0=?, mains1=?, subs0=?, subs1=?, "
            "energy0=?, energy1=? WHERE episode_id=?",
            (a0.name, a1.name, json.dumps(a0.main_lines), json.dumps(a1.main_lines),
             json.dumps(a0.sub_lines), json.dumps(a1.sub_lines),
             json.dumps(a0.energy), json.dumps(a1.energy), r["episode_id"]))
        n += 1
    conn.commit()
    return n
