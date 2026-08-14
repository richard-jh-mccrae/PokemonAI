"""Self-play Corpus generator: our agent's own mirror games, saved as taggable, Tuner-usable
replays for Bellman correction analysis.

Runs N mirror games on the cabt-env path (reusing `check_agent._run_match` -> `env.toJSON()`, the
only path that carries the per-frame agent `obs` used by correction replay) and saves each to
`data/replays/selfplay/<stem>/<episode_id>.json`. The stem matches `provenance.build_identity`, so
Corrections auto-file under a real build folder; `EpisodeId` is globally unique (the dedup/review
keys assume per-game uniqueness). Set `AGENT_OVERLAY` to mine a specific config's error surface.
"""
from __future__ import annotations

import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path


def episode_id(run_stem: str, index: int) -> int:
    """A globally-unique deterministic `EpisodeId` for one corpus game. Must be unique across runs
    AND games: the Correction dedup keys assume it, so a collision silently merges two games."""
    return int(hashlib.sha1(f"{run_stem}:{index}".encode("utf-8")).hexdigest()[:12], 16)


def run_stem(agent: str, when, sha: str, overlay=None) -> str:
    """The provenance stem, matching `provenance.build_identity` so self-play Corrections file under
    a real build folder. The overlay digest keeps a candidate-config corpus off the baseline's."""
    marker = "selfplay"
    if overlay:
        marker += "-" + hashlib.sha1(str(overlay).encode("utf-8")).hexdigest()[:8]
    return f"{agent}_{when:%Y%m%d-%H%M%S}_{sha}-{marker}"


def tag_replay(replay: dict, *, episode_id: int, team_names: list[str]) -> dict:
    """Inject `info.EpisodeId` + `info.TeamNames` into an `env.toJSON()` replay, which a local
    `env.run` leaves unset. The film (`steps`) is untouched."""
    info = {**(replay.get("info") or {}), "EpisodeId": episode_id, "TeamNames": list(team_names)}
    return {**replay, "info": info}


def _save_telemetry(run_dir: Path, eid: int, captured: list[dict]) -> None:
    from common.telemetry import TAG

    by_seat = {0: [], 1: []}
    for record in captured:
        seat = record.get("seat")
        if seat in by_seat:
            line = f"{TAG} " + json.dumps(record, separators=(",", ":"))
            by_seat[seat].append([{"stderr": line}])
    for seat, records in by_seat.items():
        if records:
            path = run_dir / f"episode-{eid}-agent-{seat}-logs.json"
            path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")


@contextmanager
def _overlay_env(overlay):
    """Expose `overlay` as `AGENT_OVERLAY` for the in-process `env.run` games, then restore.
    ``overlay=None`` CLEARS any inherited one, so a baseline corpus is truly the default."""
    prev = os.environ.get("AGENT_OVERLAY")
    if overlay:
        os.environ["AGENT_OVERLAY"] = str(Path(overlay).resolve())
    else:
        os.environ.pop("AGENT_OVERLAY", None)
    try:
        yield
    finally:
        if prev is None:
            os.environ.pop("AGENT_OVERLAY", None)
        else:
            os.environ["AGENT_OVERLAY"] = prev


def generate_corpus(agent: str, n: int, *, agents_root, out_root, when, sha, overlay=None,
                    syspath_roots=(), configuration=None) -> Path:
    """Run `n` mirror games of `agent`, saving each as a tagged replay -> the run dir. Uses
    `check_agent._run_match`, the cabt-env path whose `env.toJSON()` carries the per-frame `obs`."""
    from sim.check_agent import _run_match  # lazy: pulls in kaggle_environments only when generating

    stem = run_stem(agent, when, sha, overlay)
    run_dir = Path(out_root) / "selfplay" / stem
    run_dir.mkdir(parents=True, exist_ok=True)
    agent_dir = Path(agents_root) / agent
    team_names = [f"{stem}#0", f"{stem}#1"]
    with _overlay_env(overlay):
        for i in range(n):
            from common.telemetry import capture_records
            with capture_records() as captured:
                if configuration is None:
                    _statuses, env = _run_match(agent_dir, syspath_roots)
                else:
                    _statuses, env = _run_match(agent_dir, syspath_roots, configuration=configuration)
            eid = episode_id(stem, i)
            tagged = tag_replay(env.toJSON(), episode_id=eid, team_names=team_names)
            (run_dir / f"{eid}.json").write_text(json.dumps(tagged, ensure_ascii=False),
                                                 encoding="utf-8")
            _save_telemetry(run_dir, eid, captured)
    return run_dir


def main(argv=None) -> int:
    import argparse
    import sys
    from datetime import datetime

    repo = Path(__file__).resolve().parents[2]
    sys.path[:0] = [str(repo / "tools"), str(repo / "src")]   # standalone CLI: import sim / cg / common
    from sim.battle import _git_short

    ap = argparse.ArgumentParser(
        description="Generate a self-play Corpus: our agent's own mirror games as Tuner-usable, "
                    "auto-filing replays for Bellman correction analysis.")
    ap.add_argument("agent", help="agent under src/agents/ to self-play")
    ap.add_argument("-n", "--games", type=int, default=20, help="games to generate (default 20)")
    ap.add_argument("--overlay", default=None, help="experiment overlay JSON -> corpus of that config")
    ap.add_argument("--agents-root", default=str(repo / "src" / "agents"))
    ap.add_argument("--out", default=str(repo / "data" / "replays"),
                    help="corpus root (the run lands under <out>/selfplay/<stem>/)")
    ap.add_argument("--decision-timeout", type=float, default=None,
                    help="per-decision CABT actTimeout in seconds")
    ap.add_argument("--no-match-timeout", action="store_true",
                    help="disable the CABT run timeout (uses a JSON-safe effectively-unlimited value)")
    args = ap.parse_args(argv)

    configuration = {}
    if args.decision_timeout is not None:
        configuration["actTimeout"] = args.decision_timeout
    if args.no_match_timeout:
        configuration["runTimeout"] = 1e100
    run_dir = generate_corpus(args.agent, args.games, agents_root=args.agents_root, out_root=args.out,
                              when=datetime.now(), sha=_git_short(), overlay=args.overlay,
                              syspath_roots=[repo / "src"], configuration=configuration or None)
    saved = len([path for path in Path(run_dir).glob("*.json") if "-logs" not in path.name])
    print(f"Self-play Corpus: {saved} games -> {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
