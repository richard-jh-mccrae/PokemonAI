"""Thin wrappers over the Kaggle CLI (v2.2.x) for simulation competitions.

Auth: the CLI reads ``KAGGLE_API_TOKEN`` or ``~/.kaggle/access_token`` — this
module never handles the token itself. All calls retry with backoff; downloads
are sequential to stay polite to the API (see config).
"""
from __future__ import annotations

import csv
import io
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path

from . import config


class FetchError(RuntimeError):
    pass


class RateLimitError(FetchError):
    """Kaggle returned 403/Forbidden — a rate-limit penalty that won't clear via
    rapid retries. Callers should stop and try again in a few minutes."""


def _run(args: list[str], *, capture: bool = True) -> str:
    """Run a kaggle CLI command with retries; return stdout (utf-8)."""
    last = ""
    for attempt in range(config.MAX_RETRIES):
        try:
            proc = subprocess.run(
                ["kaggle", *args], capture_output=capture, text=True, encoding="utf-8",
                timeout=config.SUBPROCESS_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            last = f"timed out after {config.SUBPROCESS_TIMEOUT_S}s"
            time.sleep(config.BACKOFF_BASE_S * (2 ** attempt))
            continue
        if proc.returncode == 0:
            time.sleep(config.REQUEST_SLEEP_S)
            return proc.stdout or ""
        last = (proc.stderr or proc.stdout or "").strip()
        if "403" in last or "Forbidden" in last:  # don't retry-storm a rate-limit penalty
            raise RateLimitError(f"rate-limited (403) on `kaggle {' '.join(args)}`")
        time.sleep(config.BACKOFF_BASE_S * (2 ** attempt))
    raise FetchError(f"`kaggle {' '.join(args)}` failed after {config.MAX_RETRIES} tries: {last}")


def _parse_csv(text: str) -> list[dict]:
    # Drop non-CSV preamble (e.g. a "Next Page Token =" line).
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if lines and "=" in lines[0] and "," not in lines[0]:
        lines = lines[1:]
    return list(csv.DictReader(io.StringIO("\n".join(lines))))


def leaderboard(competition: str = config.COMPETITION) -> list[dict]:
    """Full public leaderboard as rows: {rank, teamId, teamName, score}."""
    with __import__("tempfile").TemporaryDirectory() as td:
        _run(["competitions", "leaderboard", competition, "-d", "-p", td, "-q"])
        files = list(Path(td).iterdir())
        csv_text = None
        for f in files:
            if f.suffix == ".zip":
                with zipfile.ZipFile(f) as z:
                    name = next(n for n in z.namelist() if n.endswith(".csv"))
                    csv_text = z.read(name).decode("utf-8")
            elif f.suffix == ".csv":
                csv_text = f.read_text(encoding="utf-8")
        if csv_text is None:
            raise FetchError(f"no leaderboard CSV downloaded for {competition}")
    rows = []
    for r in _parse_csv(csv_text.lstrip("﻿")):
        rows.append({
            "rank": int(r["Rank"]),
            "teamId": int(r["TeamId"]),
            "teamName": r.get("TeamName", ""),
            "score": float(r["Score"]),
        })
    rows.sort(key=lambda x: x["rank"])
    return rows


def team_submissions(team_id: int) -> list[dict]:
    """A team's submissions: {id, dateSubmitted, publicScore}."""
    rows = _parse_csv(_run(["competitions", "team-submissions", str(team_id), "-v", "-q"]))
    out = []
    for r in rows:
        try:
            out.append({"id": int(r["id"]), "dateSubmitted": r.get("dateSubmitted"),
                        "publicScore": float(r["publicScore"]) if r.get("publicScore") else None})
        except (KeyError, ValueError):
            continue
    return out


def episodes(submission_id: int) -> list[dict]:
    """Episodes for a submission: {id, createTime, endTime, state, type}, newest first."""
    rows = _parse_csv(_run(["competitions", "episodes", str(submission_id), "-v", "-q"]))
    out = []
    for r in rows:
        try:
            out.append({"id": int(r["id"]), "createTime": r.get("createTime"),
                        "endTime": r.get("endTime"), "state": r.get("state"), "type": r.get("type")})
        except (KeyError, ValueError):
            continue
    return out


def download_replay(episode_id: int, dest_dir: str | Path) -> Path:
    """Download one replay JSON; return its path."""
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    _run(["competitions", "replay", str(episode_id), "-p", str(dest), "-q"])
    path = dest / f"episode-{episode_id}-replay.json"
    if not path.exists():
        raise FetchError(f"replay {episode_id} not downloaded")
    return path


# --- Daily top-episode datasets (the official export) --------------------

def _manifest_slug(row: dict) -> str | None:
    """Owner-qualified dataset slug for a manifest row. The `daily_dataset_slug`
    column omits the owner, which the CLI rejects with 403 — so prefer the
    owner/name parsed from the URL, falling back to the `kaggle/` owner."""
    name = row.get("daily_dataset_slug")
    if not name:
        return None
    url = row.get("daily_dataset_url", "")
    if "/datasets/" in url:
        return url.split("/datasets/", 1)[1].strip("/")
    return f"kaggle/{name}"


def episodes_index() -> list[dict]:
    """Parse the index dataset's manifest -> [{date, slug, episode_count}], newest first."""
    with tempfile.TemporaryDirectory() as td:
        _run(["datasets", "download", config.EPISODES_INDEX, "-p", td, "--unzip", "-q"])
        csvp = Path(td) / "manifest.csv"
        rows = _parse_csv(csvp.read_text(encoding="utf-8"))
    out = [{"date": r["date"], "slug": _manifest_slug(r),
            "episode_count": int(r.get("episode_count") or 0)}
           for r in rows if _manifest_slug(r)]
    out.sort(key=lambda r: r["date"], reverse=True)
    return out


def dataset_episode_page(slug: str, page_token: str | None = None,
                         page_size: int = 200) -> tuple[list[int], str | None]:
    """One page of a daily dataset's files -> (episode_ids, next_page_token).

    `ListDatasetFiles` is rate-limited, so callers page incrementally (a few pages
    per run, resuming from the saved token) rather than listing all ~5k at once.
    """
    args = ["datasets", "files", slug, "-v", "--page-size", str(page_size)]  # no -q here
    if page_token:
        args += ["--page-token", page_token]
    text = _run(args)
    next_token = None
    for ln in text.splitlines():
        if ln.strip().startswith("Next Page Token ="):
            next_token = ln.split("=", 1)[1].strip()
    ids = []
    for r in _parse_csv(text):
        name = (r.get("name") or "").strip()
        if name.endswith(".json"):
            try:
                ids.append(int(name[:-5]))
            except ValueError:
                pass
    return ids, next_token


def download_dataset_episode(slug: str, episode_id: int, dest_dir: str | Path) -> Path:
    """Download one episode <id>.json from a daily dataset; return its path."""
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    fname = f"{episode_id}.json"
    _run(["datasets", "download", slug, "-f", fname, "-p", str(dest), "-q"])
    path = dest / fname
    zpath = dest / (fname + ".zip")
    if zpath.exists():
        with zipfile.ZipFile(zpath) as zf:
            zf.extractall(dest)
        zpath.unlink(missing_ok=True)
    if not path.exists():
        raise FetchError(f"dataset episode {episode_id} not downloaded from {slug}")
    return path
