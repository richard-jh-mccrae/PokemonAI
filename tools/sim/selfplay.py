"""Self-play Corpus generator: our agent's own mirror games, saved as taggable, Tuner-usable
replays for the ADR-0009 own-Pilot correction loop (ADR-0057).

Runs N mirror games on the cabt-env path (reusing `check_agent._run_match` -> `env.toJSON()`, the
only path that carries the per-frame agent `obs` the Tuner replays the Pilot on) and saves each to
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
    """A globally-unique deterministic `EpisodeId` for one corpus game. Unique across runs and
    games because the dedup/review keys (`store._dedup_key`, per-replay review) assume each game
    has a distinct id — colliding ids would silently merge two games' Corrections."""
    return int(hashlib.sha1(f"{run_stem}:{index}".encode("utf-8")).hexdigest()[:12], 16)


def run_stem(agent: str, when, sha: str, overlay=None) -> str:
    """The provenance stem `<agent>_<YYYYMMDD-HHMMSS>_<sha>-selfplay[-<overlay_digest>]` — matches
    `provenance.build_identity` so self-play Corrections file under a real build folder; an overlay
    digest keeps a candidate-config corpus distinct from the baseline."""
    marker = "selfplay"
    if overlay:
        marker += "-" + hashlib.sha1(str(overlay).encode("utf-8")).hexdigest()[:8]
    return f"{agent}_{when:%Y%m%d-%H%M%S}_{sha}-{marker}"


def tag_replay(replay: dict, *, episode_id: int, team_names: list[str]) -> dict:
    """Inject `info.EpisodeId` + `info.TeamNames` into an `env.toJSON()` replay (a local `env.run`
    leaves them unset) so the inspector keys Corrections and `detect_seat` resolves a seat. The
    film (`steps`) is left untouched."""
    info = {**(replay.get("info") or {}), "EpisodeId": episode_id, "TeamNames": list(team_names)}
    return {**replay, "info": info}


@contextmanager
def _overlay_env(overlay):
    """Expose `overlay` (absolute) as `AGENT_OVERLAY` for the in-process `env.run` games, then
    restore — so both mirror seats play the chosen config, and nothing leaks to later code. A
    baseline run (`overlay=None`) clears any inherited overlay so the corpus is truly the default."""
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
                    syspath_roots=()) -> Path:
    """Run `n` mirror games of `agent` and save each as a tagged, Tuner-usable replay under
    `out_root/selfplay/<stem>/<episode_id>.json`; return the run dir. Reuses `check_agent._run_match`
    (the cabt-env path whose `env.toJSON()` carries the per-frame `obs` the Tuner needs)."""
    from sim.check_agent import _run_match  # lazy: pulls in kaggle_environments only when generating

    stem = run_stem(agent, when, sha, overlay)
    run_dir = Path(out_root) / "selfplay" / stem
    run_dir.mkdir(parents=True, exist_ok=True)
    agent_dir = Path(agents_root) / agent
    team_names = [f"{stem}#0", f"{stem}#1"]
    with _overlay_env(overlay):
        for i in range(n):
            _statuses, env = _run_match(agent_dir, syspath_roots)
            eid = episode_id(stem, i)
            tagged = tag_replay(env.toJSON(), episode_id=eid, team_names=team_names)
            (run_dir / f"{eid}.json").write_text(json.dumps(tagged, ensure_ascii=False),
                                                 encoding="utf-8")
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
                    "auto-filing replays for the own-Pilot correction loop (ADR-0057).")
    ap.add_argument("agent", help="agent under src/agents/ to self-play")
    ap.add_argument("-n", "--games", type=int, default=20, help="games to generate (default 20)")
    ap.add_argument("--overlay", default=None, help="experiment overlay JSON -> corpus of that config")
    ap.add_argument("--agents-root", default=str(repo / "src" / "agents"))
    ap.add_argument("--out", default=str(repo / "data" / "replays"),
                    help="corpus root (the run lands under <out>/selfplay/<stem>/)")
    args = ap.parse_args(argv)

    run_dir = generate_corpus(args.agent, args.games, agents_root=args.agents_root, out_root=args.out,
                              when=datetime.now(), sha=_git_short(), overlay=args.overlay,
                              syspath_roots=[repo / "src"])
    saved = len(list(Path(run_dir).glob("*.json")))
    print(f"Self-play Corpus: {saved} games -> {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
