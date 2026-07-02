"""Daily pipeline (dataset source).

Pulls from the official daily top-episode datasets: read the index manifest,
then for each day download only the episode `<id>.json` files not already in the
store. Each episode is banded by its participants' current rating (leaderboard
name->score join); episodes below the kept range are dropped. Raw files are
deleted after parsing (ADR-0002); see docs/adr/0001 for the source.

Run via the path-shimming wrapper (this module uses package-relative imports, so it
isn't launched directly):
    python tools/run_meta_tracker.py [--bands Elite High] [--cap 500]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import tempfile
from pathlib import Path

from . import config, fetch
from .bands import band_of_rating, rating_cutoffs
from .parse import parse_replay
from .store import (connect, dataset_complete, episode_count, get_dataset_cursor,
                    mark_dataset_complete, save_dataset_cursor, upsert_episode)


def _today() -> str:
    return _dt.date.today().isoformat()


def _episode_band(rec, name2score: dict, cutoffs) -> tuple[str | None, float | None]:
    """Band + rating for an episode, from its two teams' current ratings."""
    scores = [s for s in (name2score.get(rec.team0), name2score.get(rec.team1)) if s is not None]
    if not scores:
        return None, None
    rating = sum(scores) / len(scores)
    return band_of_rating(rating, cutoffs), rating


def run(*, only_bands: list[str] | None = None, episode_cap: int | None = None,
        verbose: bool = True) -> dict:
    cap = episode_cap if episode_cap is not None else config.DAILY_EPISODE_CAP
    today = _today()
    conn = connect()
    log = (lambda *a: print(*a, flush=True)) if verbose else (lambda *a: None)

    try:
        log("[meta] leaderboard (rating -> band) ...")
        lb = fetch.leaderboard()
        manifest = fetch.episodes_index()
    except fetch.RateLimitError as e:
        log(f"[meta] {e} -- try again in a few minutes.")
        total = episode_count(conn); conn.close()
        return {"added": 0, "filtered": 0, "downloads": 0, "errors": 1, "total": total}

    name2score: dict[str, float] = {}
    for r in lb:
        name2score[r["teamName"]] = max(name2score.get(r["teamName"], -1.0), r["score"])
    cutoffs = rating_cutoffs(lb)
    log("[meta] band cutoffs: " + ", ".join(f"{b}>={s:.0f}" for b, s in cutoffs))
    log(f"[meta] {len(manifest)} daily datasets in index (cap {cap} this run)")
    per_day = max(1, cap // max(len(manifest), 1))  # spread across days so trend has points
    existing = {row[0] for row in conn.execute("SELECT episode_id FROM episodes")}

    added = filtered = unranked = errors = downloads = 0
    with tempfile.TemporaryDirectory() as td:
        for day in manifest:
            if downloads >= cap:
                break
            slug = day["slug"]
            if dataset_complete(conn, slug):
                continue
            token = get_dataset_cursor(conn, slug)  # resume paging where left off
            day_new, day_dl, pages = 0, 0, 0
            try:
                while pages < config.LIST_PAGES_PER_DATASET and downloads < cap and day_dl < per_day:
                    ids, token = fetch.dataset_episode_page(slug, token)
                    pages += 1
                    for eid in ids:
                        if downloads >= cap or day_dl >= per_day:
                            break
                        if eid in existing:
                            continue
                        try:
                            rp = fetch.download_dataset_episode(slug, eid, td)
                            downloads += 1; day_dl += 1
                            # stamp episode with dataset's date (replays carry no timestamp)
                            rec = parse_replay(rp, created_at=day["date"], end_time=day["date"])
                            Path(rp).unlink(missing_ok=True)  # extracts-only
                            existing.add(eid)
                            band, rating = _episode_band(rec, name2score, cutoffs)
                            if band is None:
                                unranked += int(rating is None); filtered += int(rating is not None); continue
                            if only_bands and band not in only_bands:
                                filtered += 1; continue
                            rec.band, rec.sampled_rating = band, rating
                            if upsert_episode(conn, rec, today):
                                added += 1; day_new += 1
                        except Exception as ex:  # noqa: BLE001 - keep run going
                            log(f"  ! episode {eid}: {ex}"); errors += 1
                    save_dataset_cursor(conn, slug, token, today)
                    if token is None:  # listed to end of this day
                        mark_dataset_complete(conn, slug, today); break
            except fetch.RateLimitError as e:
                log(f"[meta] {e} -- stopping; re-run in a few minutes."); errors += 1
                break  # don't cascade through remaining datasets (deepens the penalty)
            except fetch.FetchError as e:
                log(f"  ! list {slug}: {e}"); errors += 1
            log(f"  [{day['date']}] +{day_new} kept · run: {downloads} dl / {added} kept / "
                f"{filtered} off-band / {errors} err")

    total = episode_count(conn)
    log(f"[meta] +{added} kept, {filtered} off-band, {unranked} unranked, {errors} err, "
        f"{downloads} dl; store now {total} episodes")
    conn.close()

    from .dashboard import build_dashboard
    out = build_dashboard()
    log(f"[meta] dashboard -> {out}")
    return {"added": added, "filtered": filtered, "downloads": downloads,
            "errors": errors, "total": total}


def main() -> None:
    ap = argparse.ArgumentParser(description="Daily Pokémon TCG meta tracker (dataset source)")
    ap.add_argument("--bands", nargs="*", help="limit to these bands (e.g. Elite High)")
    ap.add_argument("--cap", type=int, help="max new episode files to download this run")
    args = ap.parse_args()
    run(only_bands=args.bands, episode_cap=args.cap)


if __name__ == "__main__":
    main()
