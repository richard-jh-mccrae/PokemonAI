"""Generate manifested focal-agent Episodes for human Ledger correction."""
from __future__ import annotations

import argparse
import atexit
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import runpy
import shutil
import subprocess
import sys
from time import monotonic
from uuid import uuid4


REPO = Path(__file__).resolve().parents[2]
_WORKER_STATE = None


@dataclass(frozen=True)
class EpisodeSlot:
    index: int
    episode_id: int
    focal: str
    opponent: str
    focal_seat: int
    partition: str
    engine_seed: int


@dataclass(frozen=True)
class ExecutionConfig:
    decision_timeout: float | None
    episode_timeout: float | None
    max_bytes: int
    agents_root: Path

    def to_manifest(self) -> dict:
        return {
            "decision_timeout": self.decision_timeout,
            "episode_timeout": self.episode_timeout,
            "max_bytes": int(self.max_bytes),
            "agents_root": str(Path(self.agents_root)),
        }

    @classmethod
    def from_manifest(cls, value: dict, fallback: "ExecutionConfig") -> "ExecutionConfig":
        return cls(
            value.get("decision_timeout", fallback.decision_timeout),
            value.get("episode_timeout", fallback.episode_timeout),
            int(value.get("max_bytes", fallback.max_bytes)),
            Path(value.get("agents_root") or fallback.agents_root),
        )


def _episode_id(*, run_identity: str, focal: str, opponent: str,
                index: int, seed: int) -> int:
    payload = json.dumps(
        [run_identity, focal, opponent, index, seed], separators=(",", ":")).encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:7], "big")


def plan_correction_run(*, focal: str, opponents: tuple[str, ...], episodes: int,
                        seed: int, run_identity: str,
                        heldout: int = 0) -> tuple[EpisodeSlot, ...]:
    """Build the complete randomized schedule before any Episode is played."""
    if episodes <= 0:
        raise ValueError("episodes must be positive")
    if not opponents:
        raise ValueError("opponent pool is empty")
    if len(set(opponents)) != len(opponents):
        raise ValueError("opponent pool contains duplicates")
    if heldout < 0 or heldout > episodes:
        raise ValueError("heldout must be between zero and episodes")

    rng = random.Random(int(seed))
    scheduled_opponents = [opponents[index % len(opponents)] for index in range(episodes)]
    rng.shuffle(scheduled_opponents)
    focal_seats = [index % 2 for index in range(episodes)]
    rng.shuffle(focal_seats)
    heldout_indices = set(rng.sample(range(episodes), heldout))

    return tuple(EpisodeSlot(
        index=index,
        episode_id=_episode_id(
            run_identity=run_identity, focal=focal, opponent=opponent,
            index=index, seed=seed),
        focal=focal,
        opponent=opponent,
        focal_seat=focal_seats[index],
        partition="heldout" if index in heldout_indices else "tuning",
        engine_seed=rng.getrandbits(63),
    ) for index, opponent in enumerate(scheduled_opponents))


def _write_manifest(path: Path, manifest: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def create_correction_run(*, output_root: Path, run_id: str, created_at: str,
                          focal: str, opponents: tuple[str, ...], episodes: int,
                          seed: int, heldout: int, jobs: int, engine: str,
                          source_identity: dict, contestant_identities: dict,
                          execution: ExecutionConfig | None = None) -> Path:
    """Create a Correction Run and persist its complete plan before execution."""
    if engine not in {"native", "cgpy"}:
        raise ValueError("engine must be native or cgpy")
    if jobs <= 0:
        raise ValueError("jobs must be positive")
    expected_contestants = {focal, *opponents}
    if set(contestant_identities) != expected_contestants:
        raise ValueError("contestant identities must cover the focal agent and opponent pool")
    run_identity = hashlib.sha256(json.dumps({
        "run_id": run_id, "source_identity": source_identity,
        "contestants": contestant_identities,
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    slots = plan_correction_run(
        focal=focal, opponents=opponents, episodes=episodes, seed=seed,
        run_identity=run_identity, heldout=heldout)
    run_dir = Path(output_root) / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    manifest = {
        "schema": "ledger.correction-run",
        "schema_version": 1,
        "run_id": run_id,
        "run_identity": run_identity,
        "created_at": created_at,
        "status": "planned",
        "focal": focal,
        "opponents": list(opponents),
        "seed": int(seed),
        "jobs": int(jobs),
        "engine": {"kind": engine, "seeded": engine == "cgpy"},
        "ledger": _ledger_identity(),
        "source_identity": source_identity,
        "contestants": contestant_identities,
        "execution": (execution or ExecutionConfig(None, None, 0, Path("."))).to_manifest(),
        "slots": [{**asdict(slot), "status": "planned"} for slot in slots],
        "totals": {"planned": len(slots), "complete": 0, "failed": 0, "bytes": 0},
    }
    _write_manifest(run_dir / "manifest.json", manifest)
    return run_dir


def audit_correction_records(records: list[dict], *, replay: dict | None = None) -> dict:
    """Reject evidence that cannot enter a strict Correction Run."""
    from train.corpus.evidence import audit_correction_records as audit

    return audit(records, replay=replay)


def _result_path(run_dir: Path, index: int) -> Path:
    return run_dir / "results" / f"{index:06d}.json"


def _save_result(run_dir: Path, result: dict) -> None:
    path = _result_path(run_dir, int(result["index"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_manifest(path, result)


def _validated_result(slot: dict, result: dict, run_dir: Path) -> dict:
    immutable = {field for field in EpisodeSlot.__dataclass_fields__ if field != "index"}
    if immutable.intersection(result):
        raise ValueError("Correction Run result overwrites its Episode plan")
    if int(result.get("index", -1)) != int(slot["index"]):
        raise ValueError("Correction Run result index does not match its Episode slot")
    if result.get("status") not in {"complete", "failed"}:
        raise ValueError("Correction Run result status is invalid")
    if result["status"] == "complete":
        from train.corpus import load_episode_bundle

        expected = Path("bundles") / slot["partition"] / str(result.get("bundle_id"))
        if result.get("bundle_path") != expected.as_posix():
            raise ValueError("Correction Run result bundle path does not match its Episode slot")
        bundle = (run_dir / expected).resolve()
        if run_dir.resolve() not in bundle.parents or not bundle.is_dir():
            raise ValueError("Correction Run result bundle is missing")
        bundle_manifest, decisions, _receipt, _outcome, replay = load_episode_bundle(bundle)
        if bundle_manifest["bundle_id"] != result.get("bundle_id") \
                or str(bundle_manifest["episode_key"]) != str(slot["episode_id"]) \
                or str((replay.get("info") or {}).get("EpisodeId")) != str(slot["episode_id"]):
            raise ValueError("Correction Run result bundle identity does not match its Episode slot")
        audit = audit_correction_records(decisions, replay=replay)
        if audit != result.get("audit"):
            raise ValueError("Correction Run result audit disagrees with its Episode bundle")
        if int(result.get("bytes", -1)) != _tree_bytes(bundle):
            raise ValueError("Correction Run result bundle byte count is stale")
    else:
        quarantine_path = result.get("quarantine_path")
        if quarantine_path:
            quarantine = (run_dir / quarantine_path).resolve()
            if run_dir.resolve() not in quarantine.parents or not quarantine.is_dir() \
                    or quarantine.parent.name != "quarantine":
                raise ValueError("Correction Run quarantine path is invalid")
            if int(result.get("bytes", -1)) != _tree_bytes(quarantine):
                raise ValueError("Correction Run quarantine byte count is stale")
        elif int(result.get("bytes", 0)) != 0:
            raise ValueError("Correction Run failed result has unowned bytes")
    return result


def _reconcile(manifest: dict, run_dir: Path, *, validate_artifacts: bool = True) -> dict:
    results = {}
    for path in sorted((run_dir / "results").glob("*.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        if path.stem != f"{int(result.get('index', -1)):06d}":
            raise ValueError("Correction Run result filename does not match its Episode slot")
        results[int(result["index"])] = result
    slots = []
    for slot in manifest["slots"]:
        result = results.get(int(slot["index"]))
        if result is not None and validate_artifacts:
            result = _validated_result(slot, result, run_dir)
        slots.append({**slot, **({} if result is None else result)})
    manifest["slots"] = slots
    complete = sum(slot["status"] == "complete" for slot in slots)
    failed = sum(slot["status"] == "failed" for slot in slots)
    stored_bytes = sum(
        _tree_bytes(run_dir / name) for name in ("bundles", "quarantine")
        if (run_dir / name).is_dir()
    ) if validate_artifacts else sum(int(slot.get("bytes") or 0) for slot in slots)
    manifest["totals"] = {
        "planned": len(slots),
        "complete": complete,
        "failed": failed,
        "bytes": stored_bytes,
    }
    return manifest


def execute_correction_run(*, run_dir: Path, agents_root: Path, extra_syspath,
                           decision_timeout: float | None, episode_timeout: float | None,
                           max_bytes: int, slot_worker=None, verify_inputs: bool = True,
                           log=None, progress_interval: float = 5.0) -> dict:
    """Execute unfinished slots and reconcile the manifest from per-slot result files."""
    run_dir = Path(run_dir)
    manifest_path = run_dir / "manifest.json"
    validate_artifacts = slot_worker is None
    manifest = _reconcile(
        json.loads(manifest_path.read_text(encoding="utf-8")), run_dir,
        validate_artifacts=validate_artifacts)
    execution = ExecutionConfig.from_manifest(
        manifest.get("execution") or {},
        ExecutionConfig(decision_timeout, episode_timeout, max_bytes, agents_root))
    if verify_inputs:
        verify_correction_run_inputs(
            manifest, execution.agents_root,
            exclude_paths=(run_dir.parent,))
    pending = [slot for slot in manifest["slots"] if slot["status"] != "complete"]
    if not pending:
        manifest["status"] = "complete"
        _write_manifest(manifest_path, manifest)
        return manifest
    if execution.max_bytes and manifest["totals"]["bytes"] >= execution.max_bytes:
        manifest["status"] = "capped"
        manifest["cap"] = _cap_summary(manifest, execution.max_bytes, 0)
        _write_manifest(manifest_path, manifest)
        return manifest
    manifest["status"] = "running"
    _write_manifest(manifest_path, manifest)
    if slot_worker is not None:
        results = (_safe_slot_result(slot_worker, slot) for slot in pending)
        for result in results:
            if execution.max_bytes and manifest["totals"]["bytes"] >= execution.max_bytes:
                manifest["status"] = "capped"
                manifest["cap"] = _cap_summary(manifest, execution.max_bytes, 0)
                break
            _save_result(run_dir, result)
            manifest = _reconcile(
                manifest, run_dir, validate_artifacts=validate_artifacts)
            _write_manifest(manifest_path, manifest)
    else:
        worker_config = {
            "run_dir": str(run_dir), "agents_root": str(execution.agents_root),
            "extra_syspath": [str(Path(path)) for path in extra_syspath],
            "decision_timeout": execution.decision_timeout,
            "episode_timeout": execution.episode_timeout,
            "engine": manifest["engine"]["kind"],
            "run_id": manifest["run_id"], "source_identity": manifest["source_identity"],
            "contestants": manifest["contestants"],
        }
        jobs = min(int(manifest["jobs"]), len(pending))
        started = monotonic()
        next_progress = 0.0
        with ProcessPoolExecutor(
                max_workers=jobs, initializer=_initialize_worker,
                initargs=(worker_config,)) as pool:
            remaining = iter(pending)
            active = {}
            for _ in range(jobs):
                slot = next(remaining, None)
                if slot is not None:
                    active[pool.submit(_run_episode_slot, slot)] = slot
            _log_progress(log, started, len(active), manifest["totals"]["complete"],
                          len(manifest["slots"]))
            next_progress = float(progress_interval)
            capped = False
            while active:
                done, _ = wait(active, timeout=1.0, return_when=FIRST_COMPLETED)
                elapsed = monotonic() - started
                if not done:
                    if elapsed >= next_progress:
                        _log_progress(log, started, len(active), manifest["totals"]["complete"],
                                      len(manifest["slots"]))
                        next_progress = elapsed + float(progress_interval)
                    continue
                for future in done:
                    slot = active.pop(future)
                    try:
                        result = future.result()
                    except Exception as error:
                        result = _failed_result(slot, error)
                    _save_result(run_dir, result)
                    manifest = _reconcile(
                        manifest, run_dir, validate_artifacts=validate_artifacts)
                    _write_manifest(manifest_path, manifest)
                    if (execution.max_bytes
                            and manifest["totals"]["bytes"] >= execution.max_bytes):
                        capped = True
                        continue
                    next_slot = next(remaining, None)
                    if next_slot is not None:
                        active[pool.submit(_run_episode_slot, next_slot)] = next_slot
                    _log_completion(log, started, slot, result, len(active),
                                    manifest["totals"]["complete"], len(manifest["slots"]))
            if capped:
                manifest["status"] = "capped"
                manifest["cap"] = _cap_summary(manifest, execution.max_bytes, jobs)
    if manifest["status"] == "running":
        manifest["status"] = (
            "complete" if manifest["totals"]["complete"] == len(manifest["slots"])
            else "failed")
    _write_manifest(manifest_path, manifest)
    return manifest


def _cap_summary(manifest: dict, limit: int, max_in_flight: int) -> dict:
    observed = int(manifest["totals"]["bytes"])
    return {
        "limit_bytes": int(limit), "observed_bytes": observed,
        "overrun_bytes": max(0, observed - int(limit)),
        "max_in_flight_episodes": int(max_in_flight),
    }


def _clock(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 60:02d}:{total % 60:02d}"


def _log_progress(log, started: float, running: int, finished: int, planned: int) -> None:
    if log is not None:
        log(f"[{_clock(monotonic() - started)}] running {running} | finished {finished}/{planned}")


def _log_completion(log, started: float, slot: dict, result: dict, running: int,
                    finished: int, planned: int) -> None:
    if log is None:
        return
    match = f"match {int(slot['index']) + 1} vs {slot['opponent']}"
    if result["status"] != "complete":
        detail = f"{match}: failed ({result['error']['type']})"
    else:
        timing = result["focal_decision_seconds"]
        decision_text = "decision n=0" if not timing["count"] else (
            f"decision avg/min/max {timing['avg']:.3f}/{timing['min']:.3f}/{timing['max']:.3f}s "
            f"(n={timing['count']})")
        detail = (
            f"{match}: focal {result['focal_result']}, {result['match_seconds']:.2f}s; "
            f"{decision_text}")
    log(f"[{_clock(monotonic() - started)}] running {running} | finished {finished}/{planned} | "
        f"{detail}")


def _safe_slot_result(worker, slot: dict) -> dict:
    try:
        return worker(slot)
    except Exception as error:
        return _failed_result(slot, error)


def _failed_result(slot: dict, error: Exception, **extra) -> dict:
    return {
        "index": slot["index"], "status": "failed", "bytes": 0,
        "error": {"type": type(error).__name__, "message": str(error)}, **extra,
    }


def _initialize_worker(config: dict) -> None:
    global _WORKER_STATE
    engine = config["engine"]
    if engine == "cgpy":
        os.environ["CG_ENGINE"] = "py"
        from cgpy.alias import install
        install()
    else:
        os.environ.pop("CG_ENGINE", None)
        os.environ.pop("CGPY_SEED", None)
    _WORKER_STATE = {"config": config, "servers": {}, "decks": {}}
    atexit.register(_close_worker)


def _close_worker() -> None:
    global _WORKER_STATE
    if _WORKER_STATE is None:
        return
    for server in _WORKER_STATE["servers"].values():
        server.close()
    _WORKER_STATE = None


def _worker_agent(role: str, name: str):
    from sim.battle import AgentServer, read_deck

    state = _WORKER_STATE
    key = f"{role}:{name}"
    server = state["servers"].get(key)
    if server is None or not server.alive():
        if server is not None:
            server.close()
        directory = Path(state["config"]["agents_root"]) / name
        source = state["config"]["source_identity"]
        contestant = state["config"]["contestants"][name]
        code = source["commit"] + (
            f"+dirty:{source['dirty_sha256']}" if source.get("dirty") else "")
        provenance = {
            "agent": name,
            "artifact": f"correction-run/{state['config']['run_id']}/{role}",
            "code": code,
            "data": {"correction_run": state["config"]["run_id"], "role": role,
                     **contestant},
        }
        server = AgentServer(
            directory, state["config"]["extra_syspath"], capture_telemetry=True,
            emit_telemetry=True, strict=True, provenance=provenance)
        state["servers"][key] = server
        state["decks"][name] = read_deck(directory)
    return server, state["decks"][name]


def _write_staging(path: Path, replay: dict, records: list[dict]) -> tuple[Path, Path]:
    from common.telemetry import frame_record

    path.mkdir(parents=True, exist_ok=False)
    replay_path = path / "replay.json"
    telemetry_path = path / "telemetry.jsonl"
    replay_path.write_text(json.dumps(replay, ensure_ascii=False), encoding="utf-8")
    lines = [line for record in records for line in frame_record(record)]
    telemetry_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return replay_path, telemetry_path


def _quarantine(staging: Path, run_dir: Path, index: int) -> Path | None:
    if not staging.exists():
        return None
    target = run_dir / "quarantine" / f"{index:06d}-{uuid4().hex[:8]}"
    target.parent.mkdir(parents=True, exist_ok=True)
    staging.replace(target)
    return target


def _tree_bytes(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _focal_decision_timing(metrics: list[dict], focal_seat: int) -> dict:
    values = [float(record["round_trip_seconds"])
              for record in metrics
              if record.get("record_type") == "decision"
              and record.get("engine_seat") == focal_seat
              and record.get("round_trip_seconds") is not None]
    return {
        "count": len(values),
        "avg": None if not values else sum(values) / len(values),
        "min": None if not values else min(values),
        "max": None if not values else max(values),
    }


def _run_episode_slot(slot: dict) -> dict:
    from sim.battle import play_match
    from sim.record import MatchRecorder
    from train.corpus import stage_episode_bundle

    state = _WORKER_STATE
    config = state["config"]
    run_dir = Path(config["run_dir"])
    staging = run_dir / ".staging" / f"{os.getpid()}-{int(slot['index']):06d}"
    started = monotonic()
    try:
        if config["engine"] == "cgpy":
            os.environ["CGPY_SEED"] = str(slot["engine_seed"])
        focal, focal_deck = _worker_agent("focal", slot["focal"])
        opponent, opponent_deck = _worker_agent("opponent", slot["opponent"])
        recorder, telemetry, metrics = MatchRecorder(), [], []
        if int(slot["focal_seat"]) == 0:
            servers, decks = (focal, opponent), (focal_deck, opponent_deck)
            team_names = [slot["focal"], slot["opponent"]]
        else:
            servers, decks = (opponent, focal), (opponent_deck, focal_deck)
            team_names = [slot["opponent"], slot["focal"]]
        result = play_match(
            *servers, *decks, recorder=recorder,
            decision_timeout=config["decision_timeout"], match_timeout=config["episode_timeout"],
            telemetry=telemetry, episode_key=str(slot["episode_id"]),
            external_episode_id=str(slot["episode_id"]), metrics=metrics)
        replay = recorder.replay(episode_id=slot["episode_id"], team_names=team_names)
        replay_path, telemetry_path = _write_staging(staging, replay, telemetry)
        if result.crashed or result.timed_out or result.match_deadline_hit or result.failure:
            raise RuntimeError(result.failure or "Episode did not complete safely")
        audit = audit_correction_records(telemetry, replay=replay)
        bundle = stage_episode_bundle(
            replay_path=replay_path, telemetry_path=telemetry_path,
            output_root=run_dir / "bundles" / slot["partition"])
        size = _tree_bytes(bundle)
        shutil.rmtree(staging)
        return {
            "index": slot["index"], "status": "complete", "bytes": size,
            "bundle_id": bundle.name, "bundle_path": bundle.relative_to(run_dir).as_posix(),
            "winner": result.winner,
            "match_seconds": monotonic() - started,
            "focal_decision_seconds": _focal_decision_timing(
                metrics, int(slot["focal_seat"])),
            "focal_result": ("draw" if result.winner is None else
                             "win" if result.winner == slot["focal_seat"] else "loss"),
            "audit": audit,
        }
    except Exception as error:
        quarantine = _quarantine(staging, run_dir, int(slot["index"]))
        return _failed_result(
            slot, error,
            match_seconds=monotonic() - started,
            bytes=0 if quarantine is None else _tree_bytes(quarantine),
            quarantine_path=(None if quarantine is None
                             else quarantine.relative_to(run_dir).as_posix()))


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _agent_identity(agents_root: Path, name: str) -> dict:
    directory = Path(agents_root) / name
    files = sorted(path for path in directory.rglob("*") if path.is_file()
                   and "__pycache__" not in path.parts and path.suffix != ".pyc")
    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(directory).as_posix().encode()
        body = path.read_bytes()
        digest.update(len(relative).to_bytes(4, "big") + relative)
        digest.update(len(body).to_bytes(8, "big") + body)
    strategy = directory / "strategy.py"
    overlay_sha256 = None
    if strategy.is_file():
        declared = runpy.run_path(str(strategy)).get("STRATEGY")
        if declared is not None:
            overlay = dict(declared.ledger_overlay)
            overlay_sha256 = hashlib.sha256(json.dumps(
                overlay, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {
        "deck_sha256": _sha256(directory / "deck.csv"),
        "strategy_sha256": _sha256(strategy) if strategy.is_file() else None,
        "ledger_overlay_sha256": overlay_sha256,
        "agent_tree_sha256": digest.hexdigest(),
    }


def _ledger_identity() -> dict:
    from common.ledger import FEATURE_CATALOG, LedgerValueEvaluator, ValuationConfiguration

    configuration = ValuationConfiguration.general()
    payload = {"schema_version": configuration.schema_version,
               "values": configuration.values}
    source = hashlib.sha256()
    ledger_root = REPO / "src" / "common" / "ledger"
    for path in sorted(item for item in ledger_root.rglob("*.py") if item.is_file()):
        relative = path.relative_to(ledger_root).as_posix().encode()
        body = path.read_bytes()
        source.update(len(relative).to_bytes(4, "big") + relative)
        source.update(len(body).to_bytes(8, "big") + body)
    return {
        "evaluator": LedgerValueEvaluator.identity,
        "feature_schema_version": FEATURE_CATALOG.schema_version,
        "global_configuration_sha256": hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "ledger_source_sha256": source.hexdigest(),
    }


def _git_source_identity(repo: Path, *, allow_dirty: bool, exclude_paths=()) -> dict:
    repo = Path(repo).resolve()
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    excluded = []
    for value in map(Path, exclude_paths):
        try:
            relative = value.resolve().relative_to(repo)
        except ValueError:
            continue
        if relative == Path("."):
            raise ValueError("artifact exclusion cannot cover the repository")
        if value.resolve().is_dir():
            tracked = subprocess.check_output(
                ["git", "ls-files", "--", relative.as_posix()], cwd=repo, text=True)
            if tracked.strip():
                raise ValueError("artifact exclusion directory contains tracked source")
        excluded.append(relative.as_posix())
    diff_args = ["git", "diff", "--binary", "HEAD", "--", "."]
    diff_args.extend(f":(exclude){value}" for value in excluded)
    diff = subprocess.check_output(diff_args, cwd=repo)
    untracked_raw = subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"], cwd=repo)
    untracked = []
    for raw in sorted(value for value in untracked_raw.split(b"\0") if value):
        relative = Path(os.fsdecode(raw))
        if any(relative == Path(root) or Path(root) in relative.parents for root in excluded):
            continue
        untracked.append((raw, repo / relative))
    dirty = bool(diff or untracked)
    if dirty and not allow_dirty:
        raise ValueError("working tree is dirty; commit changes or pass --allow-dirty")
    identity = {"commit": commit, "dirty": dirty}
    if dirty:
        digest = hashlib.sha256(diff)
        for raw, path in untracked:
            body = path.read_bytes()
            digest.update(len(raw).to_bytes(4, "big") + raw)
            digest.update(len(body).to_bytes(8, "big") + body)
        identity["dirty_sha256"] = digest.hexdigest()
    return identity


def verify_correction_run_inputs(manifest: dict, agents_root: Path, *, repo: Path = REPO,
                                 exclude_paths=(), source_reader=None) -> None:
    current_source = (source_reader or (lambda: _git_source_identity(
        repo, allow_dirty=True, exclude_paths=exclude_paths)))()
    if current_source != manifest.get("source_identity"):
        raise ValueError("source identity mismatch; create a new Correction Run")
    current_contestants = {
        name: _agent_identity(agents_root, name)
        for name in manifest.get("contestants") or {}
    }
    if current_contestants != manifest.get("contestants"):
        raise ValueError("contestant identity mismatch; create a new Correction Run")


def _default_jobs() -> int:
    return max(1, (os.cpu_count() or 1) - 2)


def _discover_agents(root: Path) -> tuple[str, ...]:
    return tuple(sorted(path.name for path in Path(root).iterdir()
                        if (path / "main.py").is_file() and (path / "deck.csv").is_file()))


def main(argv=None) -> int:
    sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]
    parser = argparse.ArgumentParser(description="Run one focal agent for Ledger correction")
    parser.add_argument("focal")
    parser.add_argument("-n", "--episodes", type=int, default=20)
    parser.add_argument("--jobs", type=int, default=_default_jobs())
    parser.add_argument("--opponents", nargs="*")
    parser.add_argument("--heldout", type=int, default=0)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--engine", choices=("native", "cgpy"), default="native")
    parser.add_argument("--decision-timeout", type=float, default=120.0)
    parser.add_argument("--episode-timeout", type=float, default=1800.0)
    parser.add_argument("--max-gb", type=float, default=8.0)
    parser.add_argument("--agents-root", type=Path, default=REPO / "src" / "agents")
    parser.add_argument("--out", type=Path, default=REPO / "data" / "correction-runs")
    parser.add_argument("--resume")
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args(argv)

    if args.resume:
        run_dir = args.out / args.resume
    else:
        opponents = tuple(args.opponents or _discover_agents(args.agents_root))
        known = set(_discover_agents(args.agents_root))
        unknown = {args.focal, *opponents} - known
        if unknown:
            parser.error(f"unknown local agents: {', '.join(sorted(unknown))}")
        source = _git_source_identity(
            REPO, allow_dirty=args.allow_dirty, exclude_paths=(args.out,))
        contestants = {
            name: _agent_identity(args.agents_root, name)
            for name in sorted({args.focal, *opponents})
        }
        created = datetime.now(timezone.utc)
        run_id = f"{created:%Y%m%d-%H%M%S}_{source['commit'][:8]}_{args.focal}"
        run_dir = create_correction_run(
            output_root=args.out, run_id=run_id, created_at=created.isoformat(),
            focal=args.focal, opponents=opponents, episodes=args.episodes, seed=args.seed,
            heldout=args.heldout, jobs=args.jobs, engine=args.engine,
            source_identity=source, contestant_identities=contestants,
            execution=ExecutionConfig(
                args.decision_timeout, args.episode_timeout,
                int(args.max_gb * 1024 ** 3), args.agents_root))
    manifest = execute_correction_run(
        run_dir=run_dir, agents_root=args.agents_root, extra_syspath=(REPO / "src",),
        decision_timeout=args.decision_timeout, episode_timeout=args.episode_timeout,
        max_bytes=int(args.max_gb * 1024 ** 3), log=print)
    totals = manifest["totals"]
    print(f"{manifest['status']}: {totals['complete']}/{totals['planned']} complete, "
          f"{totals['failed']} failed -> {run_dir}")
    return 0 if manifest["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
