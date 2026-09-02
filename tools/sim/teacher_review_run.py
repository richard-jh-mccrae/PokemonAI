"""Run Teacher-controlled matches for manual search-blunder review."""
from __future__ import annotations

import argparse
import atexit
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import random
import runpy
import sys
from time import monotonic
from uuid import uuid4


REPO = Path(__file__).resolve().parents[2]
MAX_JOBS = 8
_WORKER_STATE = None


@dataclass(frozen=True, slots=True)
class TeacherReviewSlot:
    index: int
    episode_id: int
    focal: str
    opponent: str
    focal_seat: int
    engine_seed: int
    teacher_seed: int


@dataclass(frozen=True, slots=True)
class ReviewExecutionConfiguration:
    root_timeout_seconds: float
    opponent_timeout_seconds: float
    match_timeout_seconds: float
    max_bytes: int
    agents_root: Path

    def __post_init__(self):
        if self.root_timeout_seconds <= 0 or self.opponent_timeout_seconds <= 0 \
                or self.match_timeout_seconds <= 0:
            raise ValueError("Teacher Review timeouts must be positive")
        if self.max_bytes < 0:
            raise ValueError("Teacher Review storage cap cannot be negative")

    def to_manifest(self) -> dict:
        return {
            "root_timeout_seconds": float(self.root_timeout_seconds),
            "opponent_timeout_seconds": float(self.opponent_timeout_seconds),
            "match_timeout_seconds": float(self.match_timeout_seconds),
            "max_bytes": int(self.max_bytes),
            "agents_root": str(Path(self.agents_root)),
        }

    @classmethod
    def from_manifest(cls, value: dict) -> "ReviewExecutionConfiguration":
        return cls(
            float(value["root_timeout_seconds"]),
            float(value["opponent_timeout_seconds"]),
            float(value["match_timeout_seconds"]),
            int(value["max_bytes"]), Path(value["agents_root"]))


def default_jobs() -> int:
    return min(MAX_JOBS, max(1, (os.cpu_count() or 1) - 2))


def _episode_id(*, run_identity: str, focal: str, opponent: str,
                index: int, seed: int) -> int:
    payload = json.dumps(
        [run_identity, focal, opponent, index, seed], separators=(",", ":")).encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:7], "big")


def plan_teacher_review_run(*, focal: str, opponents: tuple[str, ...], matches: int,
                            seed: int, run_identity: str) -> tuple[TeacherReviewSlot, ...]:
    if matches <= 0:
        raise ValueError("matches must be positive")
    if not opponents:
        raise ValueError("opponent pool is empty")
    if len(set(opponents)) != len(opponents):
        raise ValueError("opponent pool contains duplicates")
    rng = random.Random(int(seed))
    scheduled = []
    while len(scheduled) < matches:
        cycle = list(opponents)
        rng.shuffle(cycle)
        scheduled.extend(cycle[:matches - len(scheduled)])
    seats = [index % 2 for index in range(matches)]
    rng.shuffle(seats)
    return tuple(TeacherReviewSlot(
        index=index,
        episode_id=_episode_id(
            run_identity=run_identity, focal=focal, opponent=opponent,
            index=index, seed=seed),
        focal=focal, opponent=opponent, focal_seat=seats[index],
        engine_seed=rng.getrandbits(63), teacher_seed=rng.getrandbits(63),
    ) for index, opponent in enumerate(scheduled))


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def create_teacher_review_run(*, output_root: Path, run_id: str, created_at: str,
                              focal: str, opponents: tuple[str, ...], matches: int,
                              seed: int, jobs: int, source_identity: dict,
                              contestant_identities: dict, baseline: dict,
                              teacher: dict, search, execution: ReviewExecutionConfiguration) -> Path:
    if not 1 <= int(jobs) <= MAX_JOBS:
        raise ValueError(f"jobs must be between 1 and {MAX_JOBS}")
    if set(contestant_identities) != {focal, *opponents}:
        raise ValueError("contestant identities must cover the focal and opponent pool")
    if execution.root_timeout_seconds <= search.time_cap_seconds:
        raise ValueError("Teacher root timeout must exceed its search time cap")
    run_identity = hashlib.sha256(json.dumps({
        "run_id": run_id, "source_identity": source_identity,
        "contestants": contestant_identities, "baseline": baseline,
        "teacher": teacher, "search": asdict(search),
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    slots = plan_teacher_review_run(
        focal=focal, opponents=opponents, matches=matches, seed=seed,
        run_identity=run_identity)
    run_dir = Path(output_root) / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    manifest = {
        "schema": "teacher.review-run", "schema_version": 1,
        "run_id": run_id, "run_identity": run_identity, "created_at": created_at,
        "status": "planned", "focal": focal, "opponents": list(opponents),
        "seed": int(seed),
        "jobs": {
            "requested": int(jobs), "effective": int(jobs),
            "maximum": MAX_JOBS, "scope": "root_actions",
        },
        "engine": {"kind": "cgpy", "seeded": True},
        "baseline": dict(baseline),
        "teacher": {
            **teacher, "configuration_identity": search.identity,
            "search": asdict(search),
        },
        "source_identity": source_identity, "contestants": contestant_identities,
        "execution": execution.to_manifest(),
        "slots": [{**asdict(slot), "status": "planned"} for slot in slots],
        "totals": {"planned": len(slots), "complete": 0, "failed": 0, "bytes": 0},
    }
    _write_json(run_dir / "manifest.json", manifest)
    return run_dir


def _result_path(run_dir: Path, index: int) -> Path:
    return run_dir / "results" / f"{index:06d}.json"


def _tree_bytes(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _write_gzip_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    with temporary.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as target:
            target.write(payload)
    temporary.replace(path)


def _validated_result(slot: dict, result: dict, run_dir: Path) -> dict:
    immutable = {field for field in TeacherReviewSlot.__dataclass_fields__ if field != "index"}
    if immutable.intersection(result):
        raise ValueError("Teacher Review result overwrites its match plan")
    if int(result.get("index", -1)) != int(slot["index"]):
        raise ValueError("Teacher Review result index does not match its slot")
    if result.get("status") not in {"complete", "failed"}:
        raise ValueError("Teacher Review result status is invalid")
    if result["status"] == "complete":
        from meta_tracker.parse import load_replay

        expected = Path("episodes") / str(slot["episode_id"])
        replay_path = expected / "replay.json.gz"
        if result.get("replay_path") != replay_path.as_posix():
            raise ValueError("Teacher Review replay path does not match its slot")
        episode = (run_dir / expected).resolve()
        if run_dir.resolve() not in episode.parents or not episode.is_dir():
            raise ValueError("Teacher Review episode is missing")
        replay = load_replay(episode / "replay.json.gz")
        if str((replay.get("info") or {}).get("EpisodeId")) != str(slot["episode_id"]):
            raise ValueError("Teacher Review replay identity does not match its slot")
        searches = tuple((episode / "searches").glob("*.json.gz"))
        if int(result.get("search_count", -1)) != len(searches):
            raise ValueError("Teacher Review search sidecar count is stale")
        if int(result.get("bytes", -1)) != _tree_bytes(episode):
            raise ValueError("Teacher Review episode byte count is stale")
    else:
        relative = result.get("quarantine_path")
        if relative:
            quarantine = (run_dir / relative).resolve()
            if run_dir.resolve() not in quarantine.parents \
                    or quarantine.parent.name != "quarantine" or not quarantine.is_dir():
                raise ValueError("Teacher Review quarantine path is invalid")
            if int(result.get("bytes", -1)) != _tree_bytes(quarantine):
                raise ValueError("Teacher Review quarantine byte count is stale")
        elif int(result.get("bytes", 0)) != 0:
            raise ValueError("Teacher Review failed result has unowned bytes")
    return result


def _reconcile(manifest: dict, run_dir: Path, *, validate_artifacts: bool) -> dict:
    results = {}
    for path in sorted((run_dir / "results").glob("*.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        if path.stem != f"{int(result.get('index', -1)):06d}":
            raise ValueError("Teacher Review result filename does not match its slot")
        results[int(result["index"])] = result
    slots = []
    for slot in manifest["slots"]:
        result = results.get(int(slot["index"]))
        if result is not None and validate_artifacts:
            result = _validated_result(slot, result, run_dir)
        elif result is not None and result.get("status") not in {"complete", "failed"}:
            raise ValueError("Teacher Review result status is invalid")
        slots.append({**slot, **({} if result is None else result)})
    manifest["slots"] = slots
    complete = sum(slot["status"] == "complete" for slot in slots)
    failed = sum(slot["status"] == "failed" for slot in slots)
    stored_bytes = (sum(
        path.stat().st_size for root in (run_dir / "episodes", run_dir / "quarantine")
        if root.is_dir() for path in root.rglob("*") if path.is_file())
        if validate_artifacts else sum(int(slot.get("bytes") or 0) for slot in slots))
    manifest["totals"] = {
        "planned": len(slots), "complete": complete,
        "failed": failed, "bytes": stored_bytes,
    }
    return manifest


def execute_teacher_review_run(*, run_dir: Path, verify_inputs: bool = True,
                               slot_worker=None, log=None) -> dict:
    run_dir = Path(run_dir)
    manifest_path = run_dir / "manifest.json"
    validate_artifacts = slot_worker is None
    manifest = _reconcile(
        json.loads(manifest_path.read_text(encoding="utf-8")), run_dir,
        validate_artifacts=validate_artifacts)
    pending = [slot for slot in manifest["slots"] if slot["status"] != "complete"]
    if not pending:
        manifest["status"] = "complete"
        _write_json(manifest_path, manifest)
        return manifest
    execution = ReviewExecutionConfiguration.from_manifest(manifest["execution"])
    if verify_inputs:
        verify_teacher_review_inputs(manifest, exclude_paths=(run_dir.parent,))
    if execution.max_bytes and manifest["totals"]["bytes"] >= execution.max_bytes:
        manifest["status"] = "capped"
        _write_json(manifest_path, manifest)
        return manifest
    manifest["status"] = "running"
    _write_json(manifest_path, manifest)
    if slot_worker is not None:
        for slot in pending:
            if execution.max_bytes and manifest["totals"]["bytes"] >= execution.max_bytes:
                manifest["status"] = "capped"
                break
            result = _safe_result(slot_worker, slot)
            _write_json(_result_path(run_dir, int(slot["index"])), result)
            manifest = _reconcile(
                manifest, run_dir, validate_artifacts=validate_artifacts)
            _write_json(manifest_path, manifest)
    else:
        worker_config = {
            "run_dir": str(run_dir), "manifest": manifest,
            "execution": execution.to_manifest(),
        }
        started = monotonic()
        with ProcessPoolExecutor(
                max_workers=1, initializer=_initialize_worker,
                initargs=(worker_config,)) as pool:
            _log(log, started, 1, manifest)
            for slot in pending:
                try:
                    result = pool.submit(_run_review_slot, slot).result()
                except Exception as error:
                    result = _failed_result(slot, error)
                _write_json(_result_path(run_dir, int(slot["index"])), result)
                manifest = _reconcile(manifest, run_dir, validate_artifacts=True)
                _write_json(manifest_path, manifest)
                _log(log, started, 0, manifest, slot=slot, result=result)
                if execution.max_bytes and manifest["totals"]["bytes"] >= execution.max_bytes:
                    manifest["status"] = "capped"
                    break
    if manifest["status"] == "running":
        manifest["status"] = (
            "complete" if manifest["totals"]["complete"] == len(manifest["slots"])
            else "failed")
    _write_json(manifest_path, manifest)
    return manifest


def _safe_result(worker, slot: dict) -> dict:
    try:
        return worker(slot)
    except Exception as error:
        return _failed_result(slot, error)


def _failed_result(slot: dict, error: Exception, **extra) -> dict:
    return {
        "index": slot["index"], "status": "failed", "bytes": 0,
        "error": {"type": type(error).__name__, "message": str(error)}, **extra,
    }


def _log(log, started: float, running: int, manifest: dict, *, slot=None, result=None) -> None:
    if log is None:
        return
    elapsed = int(monotonic() - started)
    detail = ""
    if slot is not None and result is not None:
        outcome = result.get("focal_result", "failed")
        detail = f" | match {int(slot['index']) + 1} vs {slot['opponent']}: {outcome}"
    log(f"[{elapsed // 60:02d}:{elapsed % 60:02d}] running {running} | "
        f"complete {manifest['totals']['complete']}/{manifest['totals']['planned']}{detail}")


def _initialize_worker(config: dict) -> None:
    global _WORKER_STATE
    os.environ["CG_ENGINE"] = "py"
    from cgpy.alias import install

    install()
    _WORKER_STATE = {**config, "opponents": {}}
    atexit.register(_close_worker)


def _close_worker() -> None:
    global _WORKER_STATE
    if _WORKER_STATE is None:
        return
    for server in _WORKER_STATE["opponents"].values():
        server.close()
    _WORKER_STATE = None


def _load_runtime(agent_dir: Path):
    from common.runtime import build_runtime, track_own_cards
    from sim.battle import read_deck

    strategy = runpy.run_path(str(agent_dir / "strategy.py")).get("STRATEGY")
    if strategy is None:
        raise ValueError(f"agent {agent_dir.name!r} has no declared Strategy")
    deck = read_deck(agent_dir)
    return track_own_cards(build_runtime(strategy, deck)), deck


def _opponent(name: str):
    from sim.battle import AgentServer, read_deck

    state = _WORKER_STATE
    server = state["opponents"].get(name)
    execution = ReviewExecutionConfiguration.from_manifest(state["execution"])
    manifest = state["manifest"]
    if server is None or not server.alive():
        if server is not None:
            server.close()
        directory = execution.agents_root / name
        server = AgentServer(
            directory, [REPO / "src"], capture_telemetry=False,
            emit_telemetry=False, decision_seconds=execution.opponent_timeout_seconds,
            strict=True, compute_profile="correction",
            provenance={
                "agent": name,
                "artifact": f"teacher-review-run/{manifest['run_id']}/opponent",
                "code": manifest["source_identity"]["commit"],
                "data": {"teacher_review_run": manifest["run_id"],
                         "role": "one-ply-opponent"},
            })
        state["opponents"][name] = server
    return server, read_deck(execution.agents_root / name)


def _quarantine(staging: Path, run_dir: Path, index: int) -> Path | None:
    if not staging.exists():
        return None
    target = run_dir / "quarantine" / f"{index:06d}-{uuid4().hex[:8]}"
    target.parent.mkdir(parents=True, exist_ok=True)
    staging.replace(target)
    return target


def _focal_timing(metrics: list[dict], seat: int) -> dict:
    values = [float(row["round_trip_seconds"]) for row in metrics
              if row.get("engine_seat") == seat and row.get("round_trip_seconds") is not None]
    return {
        "count": len(values), "total": sum(values),
        "average": None if not values else sum(values) / len(values),
        "minimum": None if not values else min(values),
        "maximum": None if not values else max(values),
    }


def _run_review_slot(slot: dict) -> dict:
    from cgpy.experiment import TeacherModelRecord, TeacherSearchConfiguration
    from sim.battle import play_match
    from sim.record import MatchRecorder
    from sim.teacher_agent import IsolatedTeacherSearcher, TeacherMatchAgent

    state = _WORKER_STATE
    manifest = state["manifest"]
    execution = ReviewExecutionConfiguration.from_manifest(state["execution"])
    run_dir = Path(state["run_dir"])
    staging = run_dir / ".staging" / f"{os.getpid()}-{slot['index']:06d}-{uuid4().hex[:8]}"
    staging.mkdir(parents=True, exist_ok=False)
    started = monotonic()
    actor = None
    try:
        os.environ["CGPY_SEED"] = str(slot["engine_seed"])
        focal_dir = execution.agents_root / slot["focal"]
        runtime, focal_deck = _load_runtime(focal_dir)
        expected_model = manifest["teacher"]["evaluation_model_identity"]
        if runtime.ledger.ctx.identity != expected_model:
            raise ValueError("live focal Evaluation Model differs from the Teacher Review manifest")
        search_configuration = TeacherSearchConfiguration(**manifest["teacher"]["search"])
        searcher = IsolatedTeacherSearcher(
            model=TeacherModelRecord.from_model(runtime.ledger.ctx),
            search_configuration=search_configuration,
            baseline_identity=manifest["baseline"]["baseline_id"],
            root_timeout_seconds=execution.root_timeout_seconds,
            workers=int(manifest["jobs"]["requested"]))

        def save_search(index, result):
            _write_gzip_json(staging / "searches" / f"{index:04d}.json.gz", result.document())

        actor = TeacherMatchAgent(
            runtime=runtime, perspective_seat=int(slot["focal_seat"]),
            base_seed=int(slot["teacher_seed"]), searcher=searcher,
            result_sink=save_search)
        opponent, opponent_deck = _opponent(slot["opponent"])
        if int(slot["focal_seat"]) == 0:
            servers, decks = (actor, opponent), (focal_deck, opponent_deck)
            team_names = [slot["focal"], slot["opponent"]]
            timeouts = (execution.root_timeout_seconds, execution.opponent_timeout_seconds)
        else:
            servers, decks = (opponent, actor), (opponent_deck, focal_deck)
            team_names = [slot["opponent"], slot["focal"]]
            timeouts = (execution.opponent_timeout_seconds, execution.root_timeout_seconds)
        recorder, metrics = MatchRecorder(), []
        result = play_match(
            *servers, *decks, recorder=recorder, decision_timeout=timeouts,
            match_timeout=execution.match_timeout_seconds, metrics=metrics,
            episode_key=str(slot["episode_id"]),
            external_episode_id=str(slot["episode_id"]))
        replay = recorder.replay(
            episode_id=slot["episode_id"], team_names=team_names,
            decklists=decks, require_visualizer=True)
        _write_gzip_json(staging / "replay.json.gz", replay)
        _write_json(staging / "result.json", {
            "winner": result.winner, "crashed": result.crashed,
            "timed_out": result.timed_out,
            "match_deadline_hit": result.match_deadline_hit,
            "failure": result.failure,
        })
        if result.crashed or result.timed_out or result.match_deadline_hit or result.failure:
            raise RuntimeError(result.failure or "Teacher Review match did not complete safely")
        episode = run_dir / "episodes" / str(slot["episode_id"])
        episode.parent.mkdir(parents=True, exist_ok=True)
        if episode.exists():
            raise ValueError("Teacher Review episode already exists")
        staging.replace(episode)
        size = _tree_bytes(episode)
        focal_seat = int(slot["focal_seat"])
        return {
            "index": slot["index"], "status": "complete", "bytes": size,
            "replay_path": (episode / "replay.json.gz").relative_to(run_dir).as_posix(),
            "search_count": actor.search_count, "winner": result.winner,
            "match_seconds": monotonic() - started,
            "focal_decision_seconds": _focal_timing(metrics, focal_seat),
            "focal_result": ("draw" if result.winner is None else
                             "win" if result.winner == focal_seat else "loss"),
        }
    except Exception as error:
        quarantine = _quarantine(staging, run_dir, int(slot["index"]))
        return _failed_result(
            slot, error, match_seconds=monotonic() - started,
            search_count=0 if actor is None else actor.search_count,
            bytes=0 if quarantine is None else _tree_bytes(quarantine),
            quarantine_path=(None if quarantine is None else
                             quarantine.relative_to(run_dir).as_posix()))


def require_teacher_identities(identities, *, evaluator: str,
                               evaluation_model: str) -> None:
    if evaluator != identities.evaluator:
        raise ValueError("Teacher evaluator differs from the frozen Ledger Baseline")
    if evaluation_model not in identities.evaluation_models:
        raise ValueError("Teacher Evaluation Model is absent from the frozen Ledger Baseline")


def _baseline_path(path: Path | None) -> Path:
    if path is not None:
        return Path(path).resolve()
    manifests = tuple(sorted((REPO / "data" / "ledger-baselines").glob("*/manifest.json")))
    if len(manifests) != 1:
        raise ValueError("select one frozen Ledger Baseline with --ledger-baseline")
    return manifests[0].resolve()


def _current_teacher(agent_dir: Path):
    from cgpy.experiment import WithinHorizonTeacher
    from common.ledger import LedgerValueEvaluator

    runtime, _deck = _load_runtime(agent_dir)
    return runtime, {
        "identity": WithinHorizonTeacher.identity,
        "evaluator_identity": LedgerValueEvaluator.identity,
        "evaluation_model_identity": runtime.ledger.ctx.identity,
    }


def verify_teacher_review_inputs(manifest: dict, *, exclude_paths=()) -> None:
    from common.ledger import require_baseline
    from common.ledger.baseline import baseline_identities
    from sim.run_identity import agent_identity, git_source_identity

    current_source = git_source_identity(
        REPO, allow_dirty=True, exclude_paths=exclude_paths)
    if current_source != manifest.get("source_identity"):
        raise ValueError("source identity mismatch; create a new Teacher Review Run")
    agents_root = Path(manifest["execution"]["agents_root"])
    contestants = {
        name: agent_identity(agents_root, name)
        for name in manifest.get("contestants") or {}}
    if contestants != manifest.get("contestants"):
        raise ValueError("contestant identity mismatch; create a new Teacher Review Run")
    baseline = require_baseline(
        manifest["baseline"]["baseline_id"], manifest["baseline"]["path"])
    runtime, teacher = _current_teacher(agents_root / manifest["focal"])
    require_teacher_identities(
        baseline_identities(baseline), evaluator=teacher["evaluator_identity"],
        evaluation_model=runtime.ledger.ctx.identity)
    expected = {key: teacher[key] for key in (
        "identity", "evaluator_identity", "evaluation_model_identity")}
    actual = {key: manifest["teacher"].get(key) for key in expected}
    if actual != expected:
        raise ValueError("Teacher identity mismatch; create a new Teacher Review Run")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Teacher focal matches against one-ply Ledger opponents")
    parser.add_argument("focal")
    parser.add_argument("-n", "--matches", type=int, default=1)
    parser.add_argument(
        "--jobs", type=int, default=default_jobs(),
        help="maximum parallel root-action branches; matches run sequentially")
    parser.add_argument("--opponents", nargs="*")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--teacher-time-cap", type=float, default=600.0)
    parser.add_argument("--teacher-root-timeout", type=float, default=660.0)
    parser.add_argument("--teacher-node-cap", type=int, default=100_000)
    parser.add_argument("--teacher-path-node-cap", type=int, default=512)
    parser.add_argument("--teacher-chance-branch-cap", type=int, default=100_000)
    parser.add_argument("--teacher-exact-outcome-limit", type=int, default=16)
    parser.add_argument("--teacher-chance-samples", type=int, default=12)
    parser.add_argument("--teacher-noise-tolerance", type=float, default=1e-9)
    parser.add_argument("--teacher-tie-seed", type=int, default=1178)
    parser.add_argument("--opponent-decision-timeout", type=float, default=120.0)
    parser.add_argument("--match-timeout", type=float, default=7200.0)
    parser.add_argument("--max-gb", type=float, default=8.0)
    parser.add_argument("--ledger-baseline", type=Path)
    parser.add_argument("--agents-root", type=Path, default=REPO / "src" / "agents")
    parser.add_argument("--out", type=Path, default=REPO / "data" / "teacher-review-runs")
    parser.add_argument("--resume")
    parser.add_argument("--allow-dirty", action="store_true")
    return parser


def main(argv=None) -> int:
    from cgpy.experiment import TeacherSearchConfiguration, teacher_action_policy_for_agent
    from common.ledger import load_baseline
    from common.ledger.baseline import baseline_identities
    from sim.run_identity import (
        agent_identity, discover_agents, discover_opponents, git_source_identity,
    )

    parser = _parser()
    args = parser.parse_args(argv)
    if not 1 <= args.jobs <= MAX_JOBS:
        parser.error(f"jobs must be between 1 and {MAX_JOBS}")
    if args.matches < 1:
        parser.error("matches must be at least 1")
    if args.max_gb < 0:
        parser.error("max-gb cannot be negative")
    if args.resume:
        run_dir = args.out / args.resume
    else:
        opponents = (tuple(args.opponents) if args.opponents
                     else discover_opponents(args.agents_root, args.focal))
        known = set(discover_agents(args.agents_root))
        unknown = {args.focal, *opponents} - known
        if unknown:
            parser.error(f"unknown local agents: {', '.join(sorted(unknown))}")
        if args.focal in opponents:
            parser.error("Teacher focal cannot also be an opponent")
        try:
            search = TeacherSearchConfiguration(
                node_cap=args.teacher_node_cap,
                path_node_cap=args.teacher_path_node_cap,
                chance_branch_cap=args.teacher_chance_branch_cap,
                exact_outcome_limit=args.teacher_exact_outcome_limit,
                chance_sample_count=args.teacher_chance_samples,
                time_cap_seconds=args.teacher_time_cap,
                noise_tolerance=args.teacher_noise_tolerance,
                tie_seed=args.teacher_tie_seed,
                action_policy=teacher_action_policy_for_agent(args.focal))
            execution = ReviewExecutionConfiguration(
                root_timeout_seconds=args.teacher_root_timeout,
                opponent_timeout_seconds=args.opponent_decision_timeout,
                match_timeout_seconds=args.match_timeout,
                max_bytes=int(args.max_gb * 1024 ** 3),
                agents_root=args.agents_root.resolve())
            if execution.root_timeout_seconds <= search.time_cap_seconds:
                raise ValueError("Teacher root timeout must exceed its search time cap")
            baseline_path = _baseline_path(args.ledger_baseline)
            baseline_manifest = load_baseline(baseline_path)
            runtime, teacher = _current_teacher(args.agents_root / args.focal)
            require_teacher_identities(
                baseline_identities(baseline_manifest),
                evaluator=teacher["evaluator_identity"],
                evaluation_model=runtime.ledger.ctx.identity)
            source = git_source_identity(
                REPO, allow_dirty=args.allow_dirty, exclude_paths=(args.out,))
        except ValueError as exc:
            print(f"warning: Teacher Review Run not started: {exc}", file=sys.stderr)
            return 2
        contestants = {
            name: agent_identity(args.agents_root, name)
            for name in sorted({args.focal, *opponents})}
        created = datetime.now(timezone.utc)
        run_id = f"{created:%Y%m%d-%H%M%S}_{source['commit'][:8]}_{args.focal}"
        run_dir = create_teacher_review_run(
            output_root=args.out, run_id=run_id, created_at=created.isoformat(),
            focal=args.focal, opponents=opponents, matches=args.matches,
            seed=(args.seed if args.seed is not None
                  else random.SystemRandom().getrandbits(63)),
            jobs=args.jobs, source_identity=source,
            contestant_identities=contestants,
            baseline={"path": str(baseline_path),
                      "baseline_id": baseline_manifest["baseline_id"]},
            teacher=teacher, search=search, execution=execution)
    try:
        manifest = execute_teacher_review_run(run_dir=run_dir, log=print)
    except (OSError, ValueError) as exc:
        print(f"warning: Teacher Review Run not started: {exc}", file=sys.stderr)
        return 2
    totals = manifest["totals"]
    print(f"{manifest['status']}: {totals['complete']}/{totals['planned']} complete, "
          f"{totals['failed']} failed -> {run_dir}")
    return 0 if manifest["status"] == "complete" else 1


if __name__ == "__main__":
    sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]
    raise SystemExit(main())
