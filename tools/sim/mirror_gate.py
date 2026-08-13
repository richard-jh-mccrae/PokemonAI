"""CI gate: run seat-balanced mirrors and bound every Match's wall time.

Usage:
    python tools/sim/mirror_gate.py mega_starmie --games 10 --workers 10 --max-match-seconds 300
"""
from __future__ import annotations

import sys
import os
import tempfile
import zipfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from time import monotonic

REPO = Path(__file__).resolve().parents[2]


def summarize(seconds: list[float]) -> dict[str, float]:
    """Return stable seconds statistics; an empty Mirror is never a valid gate result."""
    if not seconds:
        raise ValueError("mirror produced no matches")
    return {"avg": sum(seconds) / len(seconds), "min": min(seconds), "max": max(seconds)}


def assert_within_limit(seconds: list[float], limit: float) -> None:
    """Fail against the slowest individual Match, never an average hiding a timeout."""
    stats = summarize(seconds)
    if stats["max"] > limit:
        raise RuntimeError(
            f"mirror max match time {stats['max']:.1f}s exceeds {limit:.1f}s")


def _one_match(bundle: Path, *, a_seat: int) -> dict:
    """Worker entry point: one isolated engine plus two isolated agent servers."""
    from sim.battle import AgentServer, _play_seated, read_deck

    bundle = Path(bundle)
    if not (bundle / "main.py").is_file():
        raise ValueError(f"no bundle at {bundle}")
    deck = read_deck(bundle)
    # Do not add src/: the Bundle must be the only agent runtime available to each server.
    # A caller may have selected the offline parity engine; deployable mirrors must not.
    os.environ.pop("CG_ENGINE", None)
    servers = [AgentServer(bundle), AgentServer(bundle)]
    try:
        result = _play_seated(*servers, deck, deck, a_seat)
    finally:
        for server in servers:
            server.close()
    return {"a_seat": a_seat, "winner": result.winner, "crashed": list(result.crashed)}


def _timed_match(bundle: Path, a_seat: int) -> tuple[dict, float]:
    """Run one match in its own process so mirrors can share CI wall time safely."""
    started = monotonic()
    return _one_match(bundle, a_seat=a_seat), monotonic() - started


def run_mirror(agent: str, *, games: int, max_match_seconds: float,
               agents_root: Path, workers: int = 1, clock=monotonic) -> dict[str, float]:
    """Run deployable-agent mirrors; each worker measures one completed Match wall time."""
    if games <= 0:
        raise ValueError("games must be positive")
    if max_match_seconds <= 0:
        raise ValueError("max_match_seconds must be positive")
    if workers <= 0:
        raise ValueError("workers must be positive")

    from sim.battle import seat_plan
    from submit.package import package

    agent_dir = Path(agents_root) / agent
    if not (agent_dir / "main.py").is_file():
        raise ValueError(f"no agent at {agent_dir}")
    durations: list[float] = []
    with tempfile.TemporaryDirectory() as tmp:
        work_dir = Path(tmp)
        archive = package(agent, work_dir / "dist", agents_root=agents_root)
        bundle = work_dir / "bundle"
        with zipfile.ZipFile(archive) as zipped:
            zipped.extractall(bundle)
        if (bundle / "cgpy").exists():
            raise RuntimeError("mirror bundle contains offline-only cgpy")
        seats = seat_plan(games)
        if workers == 1:
            completed = ((_one_match(bundle, a_seat=a_seat), clock() - started)
                         for a_seat in seats for started in (clock(),))
        else:
            with ProcessPoolExecutor(max_workers=min(workers, games)) as executor:
                completed = tuple(executor.map(_timed_match, (bundle,) * games, seats))
        for index, (result, elapsed) in enumerate(completed, start=1):
            durations.append(elapsed)
            if result["crashed"]:
                raise RuntimeError(f"mirror match {index} crashed at contestant seat(s) {result['crashed']}")
            if elapsed > max_match_seconds:
                raise RuntimeError(
                    f"mirror match {index} took {elapsed:.1f}s; limit is {max_match_seconds:.1f}s")
    assert_within_limit(durations, max_match_seconds)
    return summarize(durations)


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run a bounded mirror gate for one source agent")
    parser.add_argument("agent", help="source agent under src/agents/")
    parser.add_argument("--games", type=int, default=10)
    parser.add_argument("--workers", type=int, default=1,
                        help="concurrent isolated matches (default: 1)")
    parser.add_argument("--max-match-seconds", type=float, default=300.0)
    parser.add_argument("--agents-root", default=str(REPO / "src" / "agents"))
    args = parser.parse_args(argv)

    sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]
    try:
        stats = run_mirror(
            args.agent, games=args.games, max_match_seconds=args.max_match_seconds,
            agents_root=Path(args.agents_root), workers=args.workers)
    except (RuntimeError, ValueError) as exc:
        print(f"MIRROR GATE FAILED: {exc}")
        return 1
    print("MIRROR GATE PASSED: " + " ".join(f"{key}={value:.3f}s" for key, value in stats.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
