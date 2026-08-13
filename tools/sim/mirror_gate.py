"""CI gate: run seat-balanced mirrors and bound every Match's wall time.

Usage:
    python tools/sim/mirror_gate.py mega_starmie --games 10 --max-match-seconds 600
    python tools/sim/mirror_gate.py mega_starmie --games 10 --workers 2 --max-match-seconds 600
"""
from __future__ import annotations

import sys
import os
import multiprocessing
import queue
import subprocess
import tempfile
import zipfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from time import monotonic
from threading import Thread, Lock

REPO = Path(__file__).resolve().parents[2]
MAX_CALLBACK_SECONDS = 120.0


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
    callback_seconds: list[float] = []
    callback_lock = Lock()

    class TimedAgentServer(AgentServer):
        def act(self, obs):
            started = monotonic()
            outcome = []

            def invoke():
                outcome.append(super(TimedAgentServer, self).act(obs))

            worker = Thread(target=invoke, daemon=True)
            worker.start()
            worker.join(MAX_CALLBACK_SECONDS)
            try:
                if worker.is_alive():
                    self.proc.kill()
                    self.proc.wait(timeout=5)
                    worker.join(5)
                    raise RuntimeError(
                        f"agent callback exceeded {MAX_CALLBACK_SECONDS:.1f}s at "
                        f"step={obs.get('step')} turn={(obs.get('current') or {}).get('turn')}")
                return outcome[0]
            finally:
                with callback_lock:
                    callback_seconds.append(monotonic() - started)

    servers = [TimedAgentServer(bundle), TimedAgentServer(bundle)]
    try:
        result = _play_seated(*servers, deck, deck, a_seat)
    finally:
        for server in servers:
            server.close()
    return {"a_seat": a_seat, "winner": result.winner, "crashed": list(result.crashed),
            "callback_seconds": callback_seconds}


def _match_process(bundle: Path, a_seat: int, output) -> None:
    """Isolated deadline target; queue either the result or a concise worker error."""
    try:
        output.put((True, _one_match(bundle, a_seat=a_seat)))
    except Exception as exc:  # noqa: BLE001 - cross-process failure must reach the gate
        output.put((False, f"{type(exc).__name__}: {exc}"))


def _one_match_with_deadline(bundle: Path, *, a_seat: int, timeout: float) -> dict:
    context = multiprocessing.get_context("spawn")
    output = context.Queue()
    process = context.Process(target=_match_process, args=(bundle, a_seat, output))
    process.start()
    process.join(timeout)
    if process.is_alive():
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
            )
        else:
            process.terminate()
        process.join(5)
        if process.is_alive():
            process.kill()
            process.join()
        raise RuntimeError(f"mirror match exceeded {timeout:.1f}s and was terminated")
    try:
        succeeded, payload = output.get(timeout=1)
    except queue.Empty as exc:
        raise RuntimeError(
            f"mirror worker exited {process.exitcode} without a result") from exc
    if not succeeded:
        raise RuntimeError(f"mirror worker failed: {payload}")
    return payload


def _timed_match(task: tuple[Path, int, float]) -> tuple[dict, float]:
    """Run one deadline-bounded match; suitable for a process-pool worker."""
    bundle, a_seat, timeout = task
    started = monotonic()
    return (_one_match_with_deadline(bundle, a_seat=a_seat, timeout=timeout),
            monotonic() - started)


def run_mirror(agent: str, *, games: int, max_match_seconds: float,
               agents_root: Path, workers: int = 1,
               clock=monotonic) -> dict[str, dict[str, float]]:
    """Run deadline-bounded deployable mirrors; default to serial execution."""
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
    callback_durations: list[float] = []
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
            completed = ((_one_match_with_deadline(
                bundle, a_seat=a_seat, timeout=max_match_seconds), clock() - started)
                         for a_seat in seats for started in (clock(),))
        else:
            with ProcessPoolExecutor(max_workers=min(workers, games)) as executor:
                tasks = ((bundle, a_seat, max_match_seconds) for a_seat in seats)
                completed = tuple(executor.map(_timed_match, tasks))
        for index, (result, elapsed) in enumerate(completed, start=1):
            durations.append(elapsed)
            callback_durations.extend(result["callback_seconds"])
            if result["crashed"]:
                raise RuntimeError(f"mirror match {index} crashed at contestant seat(s) {result['crashed']}")
            if elapsed > max_match_seconds:
                raise RuntimeError(
                    f"mirror match {index} took {elapsed:.1f}s; limit is {max_match_seconds:.1f}s")
            callback_stats = summarize(result["callback_seconds"])
            print(
                f"mirror {index}/{games}: match={elapsed:.3f}s "
                f"callback_avg={callback_stats['avg']:.3f}s "
                f"callback_min={callback_stats['min']:.3f}s "
                f"callback_max={callback_stats['max']:.3f}s",
                flush=True,
            )
    assert_within_limit(durations, max_match_seconds)
    return {"match": summarize(durations), "callback": summarize(callback_durations)}


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run a bounded mirror gate for one source agent")
    parser.add_argument("agent", help="source agent under src/agents/")
    parser.add_argument("--games", type=int, default=10)
    parser.add_argument("--max-match-seconds", type=float, default=600.0)
    parser.add_argument("--workers", type=int, default=1,
                        help="concurrent isolated matches (default: 1)")
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
    rendered = " ".join(
        f"{scope}_{key}={value:.3f}s"
        for scope, values in stats.items() for key, value in values.items())
    print("MIRROR GATE PASSED: " + rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
