"""Card images for the Arena: official TPCi scans, fetched once, served locally.

The pool catalogs each card under one canonical printing (ADR-0013), and
EN_Card_Data.csv carries its (Expansion, Collection No.) — which maps straight
onto the Limitless CDN's official-scan URLs. We download the whole pool ONCE per
host into tools/arena/static/cards/<id>.png (gitignored) and serve from there, so
visitors never hit a third-party CDN and the board renders fast.

Usage (one-time per host, ~1260 files @ ~50 KB):
    python tools/arena/images.py

A handful of pool cards have no Expansion recorded — they stay imageless and the
frontend falls back to the text chip.
"""
from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_TOOLS = Path(__file__).resolve().parents[1]
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from deck_convert import _load_en  # noqa: E402

CARDS_DIR = Path(__file__).resolve().parent / "static" / "cards"

_CDN = "https://limitlesstcg.nyc3.cdn.digitaloceanspaces.com/tpci"
_SET_REMAP = {"PROMO": "SVP"}       # the CDN files promos under SVP


def image_url(card_id: int, size: str = "SM") -> str | None:
    """The official-scan URL for a pool card, or None when the set is unknown."""
    entry = _load_en().get(card_id)
    if entry is None:
        return None
    _name, sett, number = entry
    sett = _SET_REMAP.get(sett, sett)
    if not sett or not number:
        return None
    return f"{_CDN}/{sett}/{sett}_{number:0>3}_R_EN_{size}.png"


def _http_fetch(url: str) -> bytes:
    import requests

    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.content


def fetch_all(dest: Path, *, ids=None, size: str = "SM", fetcher=_http_fetch,
              workers: int = 8) -> dict:
    """Download every pool image into dest/<id>.png; skip files already there."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    ids = list(ids) if ids is not None else sorted(_load_en())
    summary = {"fetched": 0, "skipped": 0, "missing": [], "failed": []}
    jobs = []
    for cid in ids:
        path = dest / f"{cid}.png"
        if path.exists():
            summary["skipped"] += 1
            continue
        url = image_url(cid, size)
        if url is None:
            summary["missing"].append(cid)
            continue
        jobs.append((cid, url, path))

    def grab(job):
        cid, url, path = job
        try:
            path.write_bytes(fetcher(url))
            return cid, None
        except Exception as exc:  # noqa: BLE001 — a bad card must not sink the batch
            return cid, str(exc)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for cid, err in pool.map(grab, jobs):
            if err is None:
                summary["fetched"] += 1
            else:
                summary["failed"].append(cid)
    return summary


def main() -> None:
    summary = fetch_all(CARDS_DIR)
    print(f"fetched {summary['fetched']}, skipped {summary['skipped']}, "
          f"no-image {len(summary['missing'])}, failed {len(summary['failed'])}")
    if summary["failed"]:
        print("failed ids:", summary["failed"])


if __name__ == "__main__":
    main()
