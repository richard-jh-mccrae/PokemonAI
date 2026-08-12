"""Corpus v2 generator (ADR-0053 WP0): the resumable, manifested, cap-bounded all-deck-pair corpus
the ML training pipeline trains on, built on `battle.play_match` + `MatchRecorder`.

DISK IS AUTHORITATIVE and the manifest is only a header: a resumed run recounts each pairing from
the max on-disk film index, so a crash between a film write and a manifest flush self-heals.

The matrix is our agents × our agents (unordered cross + mirror), seat-balanced (ADR-0021). Extra
opponent bundles drop into the ``opponents`` slot with no rewrite.
"""
from __future__ import annotations

import gzip
import json
from pathlib import Path

CORPUS_DIRNAME = "corpus"
MANIFEST_VERSION = 1
BELLMAN_CORRECTION_FORMAT = 1
_MANIFEST_FLUSH_EVERY = 10                 # games between manifest header flushes (disk is authoritative)


def corpus_pairings(agents: list[str], opponents: tuple[str, ...] = ()) -> list[tuple[str, str]]:
    """Every unordered pair among ``agents`` (cross + mirror), plus ``(agent, opponent)`` per extra
    bundle. Opponent×opponent is omitted: we only learn from OUR seats."""
    out: list[tuple[str, str]] = []
    for i, a in enumerate(agents):
        for b in agents[i:]:
            out.append((a, b))
    for a in agents:
        for opp in opponents:
            out.append((a, opp))
    return out


def pairing_stem(a: str, b: str) -> str:
    """The per-pairing subdir name within a run — ``<a>__<b>``. Stable across resume (the run_id
    carries the run's uniqueness), so a resumed run continues filling the same folder."""
    return f"{a}__{b}"


FILM_GLOB = "*.json.gz"                     # films are gzip-compressed (~8× smaller; load_replay reads
                                            # .gz transparently). manifest.json is plain, excluded by this.


def film_name(index: int, episode_id: int) -> str:
    """``{index:06d}_{episode_id}.json.gz``. The zero-padded index is what makes disk the resume
    cursor (max + 1); the episode_id keeps it globally unique."""
    return f"{index:06d}_{episode_id}.json.gz"


def next_index(run_dir: Path) -> int:
    """The next film index for a pairing dir — ``max(existing leading index) + 1``, or 0 when
    empty. Parses the ``{index:06d}_`` prefix; ignores any file that doesn't match (never raises)."""
    best = -1
    for f in Path(run_dir).glob(FILM_GLOB):
        head = f.name.split("_", 1)[0]
        if head.isdigit():
            best = max(best, int(head))
    return best + 1


def build_manifest(*, run_id: str, created_at: str, git_rev: str, agents: list[str],
                   opponents: tuple[str, ...], agent_versions: dict, per_pairing: int,
                   max_games: int, max_bytes: int) -> dict:
    """The initial run manifest (contract C1a). ``pairings[].done`` starts at 0 and is recounted
    from disk on resume; ``totals`` accumulate as films are written."""
    pairings = [{"a": a, "b": b, "stem": pairing_stem(a, b), "target": per_pairing, "done": 0}
                for a, b in corpus_pairings(agents, opponents)]
    return {
        "manifest_version": MANIFEST_VERSION,
        "run_id": run_id,
        "created_at": created_at,
        "git_rev": git_rev,
        "agents": list(agents),
        "opponents": list(opponents),
        "agent_versions": dict(agent_versions),
        "pairings": pairings,
        "per_pairing": per_pairing,
        "caps": {"max_games": max_games, "max_bytes": max_bytes},
        "corpus_schema": {"replay_shape": "cabt-visualize",
                          "bellman_correction_format": BELLMAN_CORRECTION_FORMAT},
        "status": "running",
        "totals": {"games": 0, "bytes": 0},
    }


def per_pairing_target(max_games: int, n_pairings: int, explicit: int | None = None) -> int:
    """Games per pairing: ``explicit``, else ``max_games`` spread evenly (floored at 1) so coverage
    stays balanced even if a byte cap stops the run early."""
    if explicit is not None:
        return max(1, explicit)
    if n_pairings <= 0:
        return 0
    return max(1, max_games // n_pairings)


def cap_hit(totals: dict, caps: dict) -> str | None:
    """Which hard cap ``totals`` has reached — ``"max_games"`` / ``"max_bytes"`` / None. The
    byte cap is the disk safety valve; the game cap is the nominal size."""
    if caps.get("max_games") and totals.get("games", 0) >= caps["max_games"]:
        return "max_games"
    if caps.get("max_bytes") and totals.get("bytes", 0) >= caps["max_bytes"]:
        return "max_bytes"
    return None


def prune_runs(root: Path, keep_bytes: int) -> list[str]:
    """Delete oldest COMPLETE runs (by ``created_at``) until total size ≤ ``keep_bytes`` -> the
    deleted run_ids. A running or capped run is never pruned."""
    import shutil

    root = Path(root)
    runs = []
    for d in root.iterdir() if root.exists() else []:
        mf = d / "manifest.json"
        if not mf.exists():
            continue
        try:
            m = json.loads(mf.read_text(encoding="utf-8"))
        except Exception:
            continue
        size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
        runs.append((m.get("created_at", ""), d, m.get("status"), size, m.get("run_id", d.name)))
    total = sum(r[3] for r in runs)
    deleted: list[str] = []
    for _created, d, status, size, rid in sorted(runs, key=lambda r: r[0]):
        if total <= keep_bytes:
            break
        if status != "complete":
            continue
        shutil.rmtree(d, ignore_errors=True)
        total -= size
        deleted.append(rid)
    return deleted


# ---- the engine-driving loop (covered by a live test; pure helpers above are unit-tested) --------

def _dir_size(path: Path) -> int:
    return sum(f.stat().st_size for f in Path(path).rglob("*") if f.is_file())


def _count_films(run_dir: Path) -> int:
    """Total films on disk — the authoritative game count a resumed run reconciles its header to.
    The manifest is plain ``.json`` and never matches the film glob."""
    return sum(1 for _ in Path(run_dir).rglob(FILM_GLOB))


def generate_corpus_run(*, run_id: str, created_at: str, git_rev: str, agents: list[str],
                        agents_root, out_root, agent_versions: dict, opponents: tuple[str, ...] = (),
                        per_pairing: int | None = None, max_games: int = 30_000,
                        max_bytes: int = 8 * 1024**3, extra_syspath=(), resume: bool = False) -> Path:
    """Run the matrix to its per-pairing target or the first cap -> the run dir. Crashed games are
    skipped; resume recounts from disk."""
    from sim.battle import AgentServer, play_match, read_deck
    from sim.record import MatchRecorder
    from sim.selfplay import episode_id

    run_dir = Path(out_root) / CORPUS_DIRNAME / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = run_dir / "manifest.json"

    pairs = corpus_pairings(agents, opponents)
    target = per_pairing_target(max_games, len(pairs), per_pairing)
    if resume and manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["status"] = "running"                    # a resumed run is running again
    else:
        manifest = build_manifest(run_id=run_id, created_at=created_at, git_rev=git_rev,
                                  agents=agents, opponents=opponents, agent_versions=agent_versions,
                                  per_pairing=target, max_games=max_games, max_bytes=max_bytes)
    manifest["totals"]["games"] = _count_films(run_dir)   # reconcile the header with disk (self-heals
    manifest["totals"]["bytes"] = _dir_size(run_dir)      # a crash between film write and flush)
    _flush(manifest, manifest_path)

    agents_root = Path(agents_root)
    by_stem = {p["stem"]: p for p in manifest["pairings"]}
    written_since_flush = 0
    capped: str | None = None

    for a, b in pairs:
        if capped:
            break
        stem = pairing_stem(a, b)
        pair_dir = run_dir / stem
        pair_dir.mkdir(parents=True, exist_ok=True)
        entry = by_stem.get(stem) or {"stem": stem, "target": target, "done": 0}
        start = next_index(pair_dir)                       # crash-safe resume cursor
        entry["done"] = start
        dir_a, dir_b = agents_root / a, agents_root / b
        deck_a, deck_b = read_deck(dir_a), read_deck(dir_b)
        sa = AgentServer(dir_a, extra_syspath)
        sb = AgentServer(dir_b, extra_syspath)
        try:
            i = start
            while i < entry["target"]:
                capped = cap_hit(manifest["totals"], manifest["caps"])
                if capped:
                    break
                if not sa.alive():
                    sa = AgentServer(dir_a, extra_syspath)
                if not sb.alive():
                    sb = AgentServer(dir_b, extra_syspath)
                rec = MatchRecorder()
                if i % 2 == 0:                             # seat-balance: alternate deck in seat 0
                    result = play_match(sa, sb, deck_a, deck_b, recorder=rec)
                    names = [f"{stem}#0-{a}", f"{stem}#1-{b}"]
                else:
                    result = play_match(sb, sa, deck_b, deck_a, recorder=rec)
                    names = [f"{stem}#0-{b}", f"{stem}#1-{a}"]
                if result.crashed:                         # unclean game -> don't poison the corpus
                    i += 1
                    continue
                eid = episode_id(f"{run_id}/{stem}", i)
                replay = rec.replay(episode_id=eid, team_names=names)
                path = pair_dir / film_name(i, eid)
                with gzip.open(path, "wt", encoding="utf-8") as fh:
                    json.dump(replay, fh, ensure_ascii=False)
                manifest["totals"]["games"] += 1
                manifest["totals"]["bytes"] += path.stat().st_size
                entry["done"] = i + 1
                i += 1
                written_since_flush += 1
                if written_since_flush >= _MANIFEST_FLUSH_EVERY:
                    _flush(manifest, manifest_path)
                    written_since_flush = 0
        finally:
            sa.close()
            sb.close()

    manifest["status"] = "capped" if capped else "complete"
    _flush(manifest, manifest_path)
    return run_dir


def _flush(manifest: dict, path: Path) -> None:
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _default_run_id(when, git_rev: str) -> str:
    return f"{when:%Y%m%d-%H%M%S}_{git_rev}"


def main(argv=None) -> int:
    import argparse
    import sys
    from datetime import datetime

    repo = Path(__file__).resolve().parents[2]
    sys.path[:0] = [str(repo / "tools"), str(repo / "src")]
    from sim.battle import _git_short

    ap = argparse.ArgumentParser(
        description="Corpus v2 (ADR-0053 WP0): resumable, cap-bounded all-deck-pair corpus for the "
                    "ML training pipeline. Reuses the gauntlet's process-isolated recorder.")
    ap.add_argument("agents", nargs="*", help="decision-owning agents (default: all under src/agents)")
    ap.add_argument("--opponents", nargs="*", default=[], help="extra opponent bundle names (meta-deck "
                    "drivers); empty in v1")
    ap.add_argument("--per-pairing", type=int, default=None, help="games per pairing (default: "
                    "max-games spread evenly)")
    ap.add_argument("--max-games", type=int, default=30_000, help="hard game cap (default 30000)")
    ap.add_argument("--max-gb", type=float, default=8.0, help="hard disk cap in GB (default 8)")
    ap.add_argument("--out", default=str(repo / "data" / "replays"),
                    help="corpus root (run lands under <out>/corpus/<run_id>/)")
    ap.add_argument("--agents-root", default=str(repo / "src" / "agents"))
    ap.add_argument("--resume", default=None, help="run_id to continue (else a fresh timestamped run)")
    ap.add_argument("--prune-to-gb", type=float, default=None, help="delete oldest COMPLETE runs "
                    "until <out>/corpus total <= this many GB, then exit")
    args = ap.parse_args(argv)

    out_root = Path(args.out)
    if args.prune_to_gb is not None:
        deleted = prune_runs(out_root / CORPUS_DIRNAME, int(args.prune_to_gb * 1024**3))
        print(f"pruned {len(deleted)} run(s): {', '.join(deleted) or '(none)'}")
        return 0

    agents = args.agents or sorted(p.parent.name for p in (repo / "src" / "agents").glob("*/main.py"))
    if not agents:
        print("error: no agents found (pass names, or populate src/agents/*/main.py)")
        return 1

    git_rev = _git_short()
    when = datetime.now()
    run_id = args.resume or _default_run_id(when, git_rev)
    agent_versions = {a: git_rev for a in (*agents, *args.opponents)}

    run_dir = generate_corpus_run(
        run_id=run_id, created_at=when.isoformat(), git_rev=git_rev, agents=agents,
        agents_root=args.agents_root, out_root=out_root, agent_versions=agent_versions,
        opponents=tuple(args.opponents), per_pairing=args.per_pairing, max_games=args.max_games,
        max_bytes=int(args.max_gb * 1024**3), extra_syspath=[repo / "src"],
        resume=bool(args.resume))

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    t = manifest["totals"]
    print(f"corpus {run_id}: {t['games']} games, {t['bytes'] / 1024**2:.1f} MB, "
          f"status={manifest['status']} -> {run_dir}")
    print(f"  resume: python tools/sim/corpus.py --resume {run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
