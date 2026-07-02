"""Export the meta's head-N representative decks for the Matchup Brief workflow (ADR-0027).

The meta-tracker owns the meta; this is its deck-export half. For each of the top-N
Variant Clusters by play-rate it ships the cluster's Representative Build as a
``deck.csv`` (sorted ids, deck-genie format) + ``deck.txt`` (Limitless render) under
``data/meta/decks/<slug>/``, plus a ranked ``index.json`` menu carrying each cluster's
``covers`` (member Archetype strings) so ``matchup-genie`` can stamp a Brief's ``covers:``
list without re-deriving it. Standalone (reads the store, no scrape); the output is
gitignored + regenerated. See CONTEXT.md → Variant Cluster / Representative Build.
"""
from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from datetime import date
from pathlib import Path

from deck_convert import check_legality, render_txt

from . import config
from .aggregate import apply_merge, merge_map, rate_table
from .compile_scouting import _deck_observations, _representative_build
from .store import connect, load_episodes


def slugify(label: str) -> str:
    """Archetype/cluster label -> a filesystem slug (lowercase, underscore-joined)."""
    s = unicodedata.normalize("NFKD", label)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def _cluster_covers(merge: dict[str, str]) -> dict[str, list[str]]:
    """Invert the merge map: cluster label -> sorted member Archetype strings."""
    covers: dict[str, set] = defaultdict(set)
    for member, cluster in merge.items():
        covers[cluster].add(member)
    return {c: sorted(ms) for c, ms in covers.items()}


def export_decks(eps: list[dict], *, now: str, top_n: int, out_dir,
                 half_life_days: float = 21.0) -> list[dict]:
    """Write the top-N clusters' decks + ``index.json`` under ``out_dir``; return the index.

    Merges variants, ranks clusters by play-rate, and for each of the top-N ships its
    pooled-modal Representative Build. A cluster whose modal build isn't a legal 60 is
    skipped with a warning (never a malformed deck.csv). Raises on a slug collision.
    """
    out_dir = Path(out_dir)
    merge = merge_map(eps)
    covers = _cluster_covers(merge)
    eps_m = apply_merge(eps, merge)
    ranking = rate_table(eps_m, "arch")            # most_common order == play-rate desc

    by_cluster: dict[str, list] = defaultdict(list)
    for o in _deck_observations(eps_m, now, half_life_days):
        by_cluster[o[0]].append(o)

    index: list[dict] = []
    slugs: dict[str, str] = {}
    for row in ranking[:top_n]:
        cluster = row["name"]
        build = _representative_build(by_cluster.get(cluster, []))
        problems = check_legality(build)
        if problems:
            print(f"[export] skip {cluster!r}: representative build illegal "
                  f"({'; '.join(problems)})", flush=True)
            continue
        slug = slugify(cluster)
        if slugs.get(slug, cluster) != cluster:
            raise ValueError(f"slug collision: {cluster!r} and {slugs[slug]!r} both -> {slug!r}")
        slugs[slug] = cluster

        deck_dir = out_dir / slug
        deck_dir.mkdir(parents=True, exist_ok=True)
        (deck_dir / "deck.csv").write_text(
            "\n".join(str(c) for c in sorted(build)) + "\n", encoding="utf-8")
        (deck_dir / "deck.txt").write_text(render_txt(build), encoding="utf-8")
        index.append({
            "rank": len(index) + 1,
            "slug": slug,
            "label": cluster,
            "covers": covers.get(cluster, [cluster]),
            "play_rate": round(row["play_rate"], 4),
            "win_rate": round(row["win_rate"], 4) if row["win_rate"] is not None else None,
            "episodes": row["episodes"],
        })

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return index


def run(db_path=None, out_dir=None, top_n: int | None = None, now: str | None = None) -> list[dict]:
    """Load the store and export the head-N decks (standalone entry; no scrape)."""
    out_dir = Path(out_dir) if out_dir else config.DECKS_DIR
    top_n = top_n if top_n is not None else config.EXPORT_TOP_N
    now = now or date.today().isoformat()
    conn = connect(db_path)
    eps = load_episodes(conn)
    conn.close()
    index = export_decks(eps, now=now, top_n=top_n, out_dir=out_dir)
    print(f"[export] {len(index)} deck(s) -> {out_dir}", flush=True)
    return index


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Export the meta's head-N representative decks (ADR-0027)")
    ap.add_argument("--top", type=int, help=f"clusters to export (default {config.EXPORT_TOP_N})")
    ap.add_argument("--out", help="output dir (default data/meta/decks)")
    ap.add_argument("--db", help="meta.db path (default data/meta/meta.db)")
    args = ap.parse_args()
    run(db_path=args.db, out_dir=args.out, top_n=args.top)


if __name__ == "__main__":  # pragma: no cover
    main()
