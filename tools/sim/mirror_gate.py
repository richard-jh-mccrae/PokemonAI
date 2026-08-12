"""CI gate: run a serial, seat-balanced mirror and bound every Match's wall time.

Usage:
    python tools/sim/mirror_gate.py mega_starmie --games 10 --max-match-seconds 300
"""
from __future__ import annotations

import sys
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


def run_mirror(agent: str, *, games: int, max_match_seconds: float,
               agents_root: Path, clock=monotonic) -> dict[str, float]:
    """Run ``games`` source-agent mirrors serially so each returned duration is one Match."""
    if games <= 0:
        raise ValueError("games must be positive")
    if max_match_seconds <= 0:
        raise ValueError("max_match_seconds must be positive")

    from sim.battle import AgentServer, _play_seated, read_deck, seat_plan

    agent_dir = Path(agents_root) / agent
    if not (agent_dir / "main.py").is_file():
        raise ValueError(f"no agent at {agent_dir}")
    deck = read_deck(agent_dir)
    servers = [AgentServer(agent_dir, [REPO / "src"]), AgentServer(agent_dir, [REPO / "src"])]
    durations: list[float] = []
    try:
        for index, a_seat in enumerate(seat_plan(games), start=1):
            started = clock()
            result = _play_seated(*servers, deck, deck, a_seat)
            elapsed = clock() - started
            durations.append(elapsed)
            if result.crashed:
                raise RuntimeError(f"mirror match {index} crashed at contestant seat(s) {result.crashed}")
            if elapsed > max_match_seconds:
                raise RuntimeError(
                    f"mirror match {index} took {elapsed:.1f}s; limit is {max_match_seconds:.1f}s")
            for position, server in enumerate(servers):
                if not server.alive():
                    server.close()
                    servers[position] = AgentServer(agent_dir, [REPO / "src"])
    finally:
        for server in servers:
            server.close()
    assert_within_limit(durations, max_match_seconds)
    return summarize(durations)


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run a bounded serial mirror gate for one source agent")
    parser.add_argument("agent", help="source agent under src/agents/")
    parser.add_argument("--games", type=int, default=10)
    parser.add_argument("--max-match-seconds", type=float, default=300.0)
    parser.add_argument("--agents-root", default=str(REPO / "src" / "agents"))
    args = parser.parse_args(argv)

    sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]
    try:
        stats = run_mirror(
            args.agent, games=args.games, max_match_seconds=args.max_match_seconds,
            agents_root=Path(args.agents_root))
    except (RuntimeError, ValueError) as exc:
        print(f"MIRROR GATE FAILED: {exc}")
        return 1
    print("MIRROR GATE PASSED: " + " ".join(f"{key}={value:.3f}s" for key, value in stats.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
