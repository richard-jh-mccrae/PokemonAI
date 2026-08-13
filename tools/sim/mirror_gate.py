"""Native exact-bundle mirror gate with isolated, deadline-bounded parallel matches.

Usage:
    python tools/sim/mirror_gate.py mega_starmie
    python tools/sim/mirror_gate.py mega_starmie --artifact data/submissions/build.zip
"""
from __future__ import annotations

import hashlib
import multiprocessing
import os
import queue
import subprocess
import sys
import tempfile
import zipfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import ExitStack
from pathlib import Path
from threading import Lock, Thread
from time import monotonic


REPO = Path(__file__).resolve().parents[2]
DEFAULT_FINAL_MATCHES = 5
DEFAULT_FINAL_WORKERS = 5
DEFAULT_MATCH_TIMEOUT_SECONDS = 600.0
MAX_CALLBACK_SECONDS = 120.0
PROCESS_SHUTDOWN_SECONDS = 5.0
RESULT_QUEUE_TIMEOUT_SECONDS = 1.0


class MirrorGateFailure(RuntimeError):
    """All match results are available even when the aggregate gate fails."""

    def __init__(self, report: dict, message: str):
        super().__init__(message)
        self.report = report


def summarize(seconds: list[float]) -> dict[str, float]:
    """Return sum and distribution; an empty mirror is never a valid gate result."""
    if not seconds:
        raise ValueError("mirror produced no matches")
    total = sum(seconds)
    return {"total": total, "avg": total / len(seconds),
            "min": min(seconds), "max": max(seconds)}


def assert_within_limit(seconds: list[float], limit: float) -> None:
    """Fail against the slowest individual match, never an average hiding a timeout."""
    stats = summarize(seconds)
    if stats["max"] > limit:
        raise RuntimeError(
            f"mirror max match time {stats['max']:.1f}s exceeds {limit:.1f}s")


def _artifact_sha256(archive: Path) -> str:
    digest = hashlib.sha256()
    with Path(archive).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _validate_archive(archive: Path) -> None:
    if not Path(archive).is_file() or not zipfile.is_zipfile(archive):
        raise ValueError(f"mirror artifact is not a zip: {archive}")
    with zipfile.ZipFile(archive) as zipped:
        names = zipped.namelist()
        if "main.py" not in names:
            raise ValueError(f"mirror artifact has no main.py: {archive}")
        if (any("cgpy" in name.lower() for name in names)
                or any(b"cgpy" in zipped.read(name).lower()
                       for name in names if not name.endswith("/"))):
            raise RuntimeError("mirror bundle contains offline-only cgpy")


def _one_match(bundle: Path, *, a_seat: int) -> dict:
    """Worker entry point: one isolated native engine plus two isolated agent servers."""
    from sim.battle import AgentServer, _play_seated, read_deck

    bundle = Path(bundle)
    if not (bundle / "main.py").is_file():
        raise ValueError(f"no bundle at {bundle}")
    deck = read_deck(bundle)
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
                    self.proc.wait(timeout=PROCESS_SHUTDOWN_SECONDS)
                    worker.join(PROCESS_SHUTDOWN_SECONDS)
                    raise RuntimeError(
                        f"agent callback exceeded {MAX_CALLBACK_SECONDS:.1f}s at "
                        f"step={obs.get('step')} turn={(obs.get('current') or {}).get('turn')}")
                if not outcome:
                    raise RuntimeError("agent callback ended without a result")
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
    try:
        output.put((True, _one_match(bundle, a_seat=a_seat)))
    except Exception as exc:  # noqa: BLE001 - cross-process failure must reach the gate
        output.put((False, f"{type(exc).__name__}: {exc}"))


def _terminate_process(process) -> None:
    if not process.is_alive():
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
    else:
        process.terminate()
    process.join(PROCESS_SHUTDOWN_SECONDS)
    if process.is_alive():
        process.kill()
        process.join()


def _one_match_with_deadline(bundle: Path, *, a_seat: int, timeout: float) -> dict:
    context = multiprocessing.get_context("spawn")
    output = context.Queue()
    process = context.Process(target=_match_process, args=(bundle, a_seat, output))
    process.start()
    try:
        process.join(timeout)
        if process.is_alive():
            _terminate_process(process)
            raise TimeoutError(f"mirror match exceeded {timeout:.1f}s and was terminated")
        try:
            succeeded, payload = output.get(timeout=RESULT_QUEUE_TIMEOUT_SECONDS)
        except queue.Empty as exc:
            raise RuntimeError(
                f"mirror worker exited {process.exitcode} without a result") from exc
        if not succeeded:
            raise RuntimeError(f"mirror worker failed: {payload}")
        return payload
    finally:
        _terminate_process(process)
        output.close()
        output.join_thread()


def _timed_archive_match(task: tuple[int, Path, int, float]) -> dict:
    """Extract and run one exact artifact in an isolated directory; never raise to the batch."""
    index, archive, a_seat, timeout = task
    started = monotonic()
    try:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            bundle = Path(tmp) / "bundle"
            with zipfile.ZipFile(archive) as zipped:
                zipped.extractall(bundle)
            result = _one_match_with_deadline(bundle, a_seat=a_seat, timeout=timeout)
        elapsed = monotonic() - started
        if result.get("crashed"):
            return {"index": index, "status": "failed", "seconds": elapsed,
                    "error": f"contestant seat(s) crashed: {result['crashed']}", "result": result}
        if elapsed > timeout:
            return {"index": index, "status": "timeout", "seconds": elapsed,
                    "error": f"match exceeded {timeout:.1f}s", "result": result}
        return {"index": index, "status": "passed", "seconds": elapsed,
                "error": None, "result": result}
    except TimeoutError as exc:
        return {"index": index, "status": "timeout", "seconds": monotonic() - started,
                "error": str(exc), "result": None}
    except Exception as exc:  # noqa: BLE001 - one failure must not suppress four reports
        return {"index": index, "status": "failed", "seconds": monotonic() - started,
                "error": f"{type(exc).__name__}: {exc}", "result": None}


def _failed_future(index: int, started: float, exc: BaseException) -> dict:
    return {"index": index, "status": "failed", "seconds": monotonic() - started,
            "error": f"worker process failed: {type(exc).__name__}: {exc}", "result": None}


def _print_report(report: dict) -> None:
    for outcome in report["results"]:
        detail = f" ({outcome['error']})" if outcome.get("error") else ""
        print(f"match {outcome['index']}: {outcome['status'].upper()} "
              f"{outcome['seconds']:.3f}s{detail}", flush=True)
    stats = report["match"]
    print(f"total: {stats['total']:.3f}s", flush=True)
    print(f"min: {stats['min']:.3f}s", flush=True)
    print(f"max: {stats['max']:.3f}s", flush=True)
    print(f"avg: {stats['avg']:.3f}s", flush=True)
    print(f"batch wall: {report['batch_wall']:.3f}s", flush=True)
    print(f"artifact sha256: {report['artifact_sha256']}", flush=True)


def run_mirror(agent: str, *, games: int = DEFAULT_FINAL_MATCHES,
               max_match_seconds: float = DEFAULT_MATCH_TIMEOUT_SECONDS,
               agents_root: Path | None = None, workers: int = DEFAULT_FINAL_WORKERS,
               artifact: Path | None = None, clock=monotonic) -> dict:
    """Run every exact-bundle match, print all outcomes, then enforce the aggregate gate."""
    if games <= 0:
        raise ValueError("games must be positive")
    if max_match_seconds <= 0:
        raise ValueError("max_match_seconds must be positive")
    if workers <= 0:
        raise ValueError("workers must be positive")

    from sim.battle import seat_plan
    from submit.package import package

    agents_root = Path(agents_root or REPO / "src" / "agents")
    with ExitStack() as stack:
        if artifact is None:
            agent_dir = agents_root / agent
            if not (agent_dir / "main.py").is_file():
                raise ValueError(f"no agent at {agent_dir}")
            work_dir = Path(stack.enter_context(
                tempfile.TemporaryDirectory(ignore_cleanup_errors=True)))
            archive = package(agent, work_dir / "dist", agents_root=agents_root)
        else:
            archive = Path(artifact).resolve()
        _validate_archive(archive)
        artifact_identity = _artifact_sha256(archive)
        tasks = tuple((index, archive, a_seat, max_match_seconds)
                      for index, a_seat in enumerate(seat_plan(games), start=1))
        batch_started = clock()
        outcomes = {}
        if workers == 1:
            for task in tasks:
                outcome = _timed_archive_match(task)
                outcomes[outcome["index"]] = outcome
        else:
            with ProcessPoolExecutor(max_workers=min(workers, games)) as executor:
                submitted = {executor.submit(_timed_archive_match, task): (task[0], clock())
                             for task in tasks}
                for future in as_completed(submitted):
                    index, started = submitted[future]
                    try:
                        outcome = future.result()
                    except BaseException as exc:  # noqa: BLE001 - preserve remaining futures
                        outcome = _failed_future(index, started, exc)
                    outcomes[index] = outcome
        batch_wall = clock() - batch_started

    ordered = tuple(outcomes[index] for index in range(1, games + 1))
    durations = [float(outcome["seconds"]) for outcome in ordered]
    callback_durations = [
        float(seconds)
        for outcome in ordered if outcome.get("result")
        for seconds in outcome["result"].get("callback_seconds", ())
    ]
    report = {
        "match": summarize(durations),
        "callback": summarize(callback_durations) if callback_durations else None,
        "batch_wall": batch_wall,
        "artifact_sha256": artifact_identity,
        "results": ordered,
    }
    _print_report(report)
    failures = [outcome for outcome in ordered if outcome["status"] != "passed"]
    if failures:
        labels = ", ".join(f"match {row['index']}={row['status']}" for row in failures)
        raise MirrorGateFailure(report, labels)
    try:
        assert_within_limit(durations, max_match_seconds)
    except RuntimeError as exc:
        raise MirrorGateFailure(report, str(exc)) from exc
    return report


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run a bounded exact-bundle native mirror gate")
    parser.add_argument("agent", help="source agent under src/agents/")
    parser.add_argument("--games", type=int, default=DEFAULT_FINAL_MATCHES)
    parser.add_argument("--max-match-seconds", type=float, default=DEFAULT_MATCH_TIMEOUT_SECONDS)
    parser.add_argument("--workers", type=int, default=DEFAULT_FINAL_WORKERS,
                        help="concurrent isolated matches (default: 5)")
    parser.add_argument("--artifact", type=Path,
                        help="exact prebuilt zip; omit to package source once")
    parser.add_argument("--agents-root", default=str(REPO / "src" / "agents"))
    args = parser.parse_args(argv)

    sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]
    try:
        report = run_mirror(
            args.agent, games=args.games, max_match_seconds=args.max_match_seconds,
            agents_root=Path(args.agents_root), workers=args.workers, artifact=args.artifact)
    except MirrorGateFailure as exc:
        print(f"MIRROR GATE FAILED: {exc}")
        return 1
    except (RuntimeError, ValueError) as exc:
        print(f"MIRROR GATE FAILED: {exc}")
        return 1
    callback = report["callback"]
    callback_text = ("" if callback is None else
                     f" callback_avg={callback['avg']:.3f}s "
                     f"callback_min={callback['min']:.3f}s callback_max={callback['max']:.3f}s")
    print(f"MIRROR GATE PASSED:{callback_text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
