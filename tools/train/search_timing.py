"""Single entry point for repeatable Ledger and PUCT performance experiments."""
from __future__ import annotations

import argparse
import cProfile
from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime
from functools import lru_cache
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import pstats
import shutil
import statistics
import subprocess
import sys
import tempfile
from time import perf_counter, sleep
import tracemalloc


REPO = Path(__file__).resolve().parents[2]
DEFAULT_RUNS = REPO / "data" / "search-timing-runs"
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from common.cards import card_store  # noqa: E402
from common.decision.turn import engine_backend  # noqa: E402
from common.puct import evaluation_profile  # noqa: E402
from common.runtime import (DecisionPilot, DecisionSearchConfiguration,
                            build_runtime)  # noqa: E402
from sim.run_identity import git_source_identity  # noqa: E402
from train.saved_moment import SavedEpisode, load_saved_episode  # noqa: E402
from train.search_timing_report import write_report  # noqa: E402


BACKENDS = ("native-cg", "cgpy")
ARTIFACTS = ("timing", "profile", "tree")


@dataclass(frozen=True, slots=True)
class MethodSpec:
    name: str
    pilot: DecisionPilot
    supports_tree: bool


METHOD_SPECS = {
    spec.name: spec for spec in (
        MethodSpec("ledger_one_ply", DecisionPilot.LEDGER, False),
        MethodSpec("puct_uniform", DecisionPilot.PUCT, True),
    )
}
METHODS = tuple(METHOD_SPECS)


@dataclass(frozen=True, slots=True)
class RootSpec:
    root_id: str
    agent: str
    frame_class: str
    description: str
    replay_path: Path
    step: int
    seat: int


@dataclass(frozen=True, slots=True)
class BenchmarkConfiguration:
    suite: str = "core9"
    title: str = "Ledger and PUCT search timing"
    methods: tuple[str, ...] = METHODS
    backends: tuple[str, ...] = BACKENDS
    artifacts: tuple[str, ...] = ("timing", "profile")
    roots: tuple[str, ...] = ()
    artifact_roots: tuple[str, ...] = ()
    repetitions: int = 3
    simulations: int = 128
    workers: int = 1
    batch_size: int = 1
    time_limit: float = 60.0
    chance_samples: int = 12
    transition_limit: int = 100_000
    evaluation_limit: int = 100_000
    chance_limit: int = 10_000
    state_limit: int = 50_000
    node_limit: int = 50_000
    cache_limit: int = 150_000
    outstanding_limit: int = 32
    ipc_message_bytes: int = 16 * 1024 * 1024

    def __post_init__(self):
        if self.suite != "core9":
            raise ValueError("unknown Search Timing Suite")
        for name, values, allowed in (
                ("methods", self.methods, METHODS),
                ("backends", self.backends, BACKENDS),
                ("artifacts", self.artifacts, ARTIFACTS)):
            unknown = set(values) - set(allowed)
            if not values or unknown:
                raise ValueError(f"unknown {name}: {', '.join(sorted(unknown))}")
        for name in ("repetitions", "simulations", "workers", "batch_size",
                     "chance_samples", "transition_limit", "evaluation_limit",
                     "chance_limit", "state_limit", "node_limit", "cache_limit",
                     "outstanding_limit", "ipc_message_bytes"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")
        if not math.isfinite(self.time_limit) or self.time_limit <= 0:
            raise ValueError("time_limit must be positive and finite")


def root_specs(suite: str = "core9") -> tuple[RootSpec, ...]:
    if suite != "core9":
        raise ValueError(f"unknown Search Timing Suite {suite!r}")
    fixtures = REPO / "tests" / "fixtures"
    return (
        RootSpec("dragapult-opening", "dragapult_ex", "opening",
                 "Early-turn native Main decision with four legal options.",
                 fixtures / "episode-85046764-replay.json.gz", 12, 0),
        RootSpec("dragapult-search", "dragapult_ex", "search",
                 "Mid-Episode native Main decision with eleven legal options.",
                 fixtures / "episode-85046764-replay.json.gz", 80, 0),
        RootSpec("dragapult-tactical", "dragapult_ex", "tactical",
                 "Late-Episode native Main decision with five legal options.",
                 fixtures / "episode-85046764-replay.json.gz", 153, 0),
        RootSpec("lucario-opening", "mega_lucario", "opening",
                 "Early-turn native Main decision with five legal options.",
                 fixtures / "episode-85605555-replay.json.gz", 6, 0),
        RootSpec("lucario-search", "mega_lucario", "search",
                 "Mid-Episode native Main decision with five legal options.",
                 fixtures / "episode-85605555-replay.json.gz", 97, 0),
        RootSpec("lucario-tactical", "mega_lucario", "tactical",
                 "Late-Episode native Main decision with four legal options.",
                 fixtures / "episode-85605555-replay.json.gz", 122, 0),
        RootSpec("starmie-opening", "mega_starmie", "opening",
                 "Early-turn native Main decision with four legal options.",
                 fixtures / "episode-85164605-replay.json.gz", 7, 1),
        RootSpec("starmie-search", "mega_starmie", "search",
                 "Mid-Episode native Main decision with five legal options.",
                 fixtures / "episode-85164605-replay.json.gz", 48, 1),
        RootSpec("starmie-tactical", "mega_starmie", "tactical",
                 "Late-Episode native Main decision with six legal options.",
                 fixtures / "episode-85164605-replay.json.gz", 145, 1),
    )


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def _identity(value) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)]


def _registered_backend(name: str):
    if name == "cgpy":
        from cgpy.puct import register_backend

        register_backend()
    return engine_backend(name)


def _puct_configuration(agent: str, config: BenchmarkConfiguration):
    return evaluation_profile(
        agent, reuse_tree=False, simulation_limit=config.simulations,
        worker_count=config.workers, batch_size=config.batch_size,
        time_limit_seconds=config.time_limit, chance_samples=config.chance_samples,
        transition_limit=config.transition_limit, evaluation_limit=config.evaluation_limit,
        chance_limit=config.chance_limit, state_limit=config.state_limit,
        node_limit=config.node_limit, cache_limit=config.cache_limit,
        outstanding_limit=config.outstanding_limit,
        ipc_message_bytes=config.ipc_message_bytes)


@lru_cache(maxsize=None)
def _agent_definition(agent: str):
    agent_dir = REPO / "src" / "agents" / agent
    module_spec = importlib.util.spec_from_file_location(
        f"_{agent}_search_timing", agent_dir / "strategy.py")
    if module_spec is None or module_spec.loader is None:
        raise ImportError(f"cannot load strategy for {agent}")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    cards = tuple(int(value) for value in (
        agent_dir / "deck.csv").read_text(encoding="utf-8").split()[:60])
    return module.STRATEGY, cards


def _agent_runtime(agent: str, cards: tuple[int, ...], method: str, backend_name: str,
                   config: BenchmarkConfiguration, *, capture_tree=False):
    backend = _registered_backend(backend_name)
    method_spec = METHOD_SPECS[method]
    if method_spec.pilot is DecisionPilot.PUCT:
        decision = DecisionSearchConfiguration(
            DecisionPilot.PUCT, backend,
            _puct_configuration(agent, config))
    else:
        decision = DecisionSearchConfiguration(method_spec.pilot, backend)
    strategy, _current_cards = _agent_definition(agent)
    return build_runtime(
        strategy, cards, provider_factory=None,
        decision_configuration=decision, puct_capture_tree=capture_tree)


@contextmanager
def _prepared_runtime(spec: RootSpec, raw: dict, cards: tuple[int, ...],
                      method: str, backend: str,
                      config: BenchmarkConfiguration, *, capture_tree=False):
    agent_runtime = _agent_runtime(
        spec.agent, cards, method, backend, config, capture_tree=capture_tree)
    try:
        yield agent_runtime, deepcopy(raw)
    finally:
        _close_runtime(agent_runtime)


def _action(identity) -> dict | None:
    return None if identity is None else {
        "kind": identity.kind, "parts": list(identity.parts)}


def _signature(decision) -> dict:
    result = decision.decision_result
    candidates = []
    for candidate in result.roster.candidates:
        candidates.append({
            "action": _action(candidate.action.identity),
            "selection": list(candidate.action.selection),
            "status": candidate.status.value,
            "search_value": (None if candidate.search_value is None
                              else candidate.search_value.total),
            "delta": None if candidate.delta is None else candidate.delta.total,
        })
    return {
        "chosen": list(decision.chosen), "action": _action(decision.action),
        "candidates": candidates,
    }


def _decision_signature(signature: dict) -> dict:
    return {
        "chosen": signature["chosen"], "action": signature["action"],
        "candidates": [{key: candidate[key] for key in
                        ("action", "selection", "status")}
                       for candidate in signature["candidates"]],
    }


def _metrics(decision) -> dict:
    result = decision.decision_result
    evidence = result.search.puct
    if evidence is None:
        diagnostics = decision.diagnostics.get("search", {})
        return {
            "simulations": None,
            "work": {
                "transitions": diagnostics.get("nodes_visited"),
                "evaluations": None, "chances": None,
            },
            "timing": None, "transport": None,
            "tree_nodes": diagnostics.get("nodes_visited"),
            "cache_entries": None,
            "portfolio_memo": diagnostics.get("portfolio_memo"),
            "stop_reason": result.search.stop_reason,
        }
    return {
        "simulations": evidence.simulations,
        "work": asdict(evidence.work),
        "timing": None if evidence.timing is None else asdict(evidence.timing),
        "transport": asdict(evidence.transport),
        "batches": evidence.batches,
        "resources": [asdict(resource) for resource in evidence.resources],
        "tree_nodes": evidence.tree_nodes,
        "cache_entries": evidence.cache_entries,
        "cache_capacity_charged": evidence.cache_capacity_charged,
        "chance_nodes": len(evidence.chance_nodes),
        "peak_pending": evidence.peak_pending,
        "retained_engine_states": evidence.retained_engine_states,
        "peak_retained_engine_states": evidence.peak_retained_engine_states,
        "stop_reason": result.search.stop_reason,
        "outcome": evidence.outcome.value,
    }


def _close_runtime(agent_runtime) -> None:
    if agent_runtime.puct is not None:
        agent_runtime.puct.close()


def _timed_sample(spec: RootSpec, raw: dict, cards: tuple[int, ...],
                  method: str, backend: str,
                  config: BenchmarkConfiguration) -> dict:
    started = perf_counter()
    try:
        with _prepared_runtime(
                spec, raw, cards, method, backend, config
        ) as (agent_runtime, payload):
            started = perf_counter()
            decision = agent_runtime.decide(payload)
            elapsed = perf_counter() - started
        signature = _signature(decision)
        return {
            "elapsed_seconds": elapsed,
            "signature_id": _identity(signature),
            "decision_signature_id": _identity(_decision_signature(signature)),
            "signature": signature,
            "metrics": _metrics(decision),
            "failure": None,
        }
    except Exception as exc:
        return {
            "elapsed_seconds": perf_counter() - started,
            "signature_id": None, "decision_signature_id": None,
            "signature": None, "metrics": None,
            "failure": {"type": type(exc).__name__, "message": str(exc)[:2000]},
        }


def _tree_sample(spec: RootSpec, raw: dict, cards: tuple[int, ...],
                 method: str, backend: str,
                 config: BenchmarkConfiguration) -> dict:
    if not METHOD_SPECS[method].supports_tree:
        raise ValueError(f"{method} does not support tree capture")
    try:
        with _prepared_runtime(
                spec, raw, cards, method, backend, config, capture_tree=True
        ) as (agent_runtime, payload):
            decision = agent_runtime.decide(payload)
            evidence = decision.decision_result.search.puct
            if evidence is None or evidence.inspection is None:
                raise RuntimeError("PUCT tree inspection was not captured")
            signature = _signature(decision)
            return {
                "tree": asdict(evidence.inspection),
                "signature_id": _identity(signature),
                "decision_signature_id": _identity(_decision_signature(signature)),
                "metrics": _metrics(decision), "failure": None,
            }
    except Exception as exc:
        return {
            "tree": None, "signature_id": None, "decision_signature_id": None,
            "metrics": None,
            "failure": {"type": type(exc).__name__, "message": str(exc)[:2000]},
        }


def _top_functions(stats: pstats.Stats | None, limit: int = 30) -> list[dict]:
    if stats is None:
        return []
    rows = []
    for (filename, line, function), (_primitive, calls, total, cumulative, _callers) in getattr(stats, "stats").items():
        rows.append({
            "file": filename, "line": line, "function": function,
            "calls": calls, "total_seconds": total,
            "cumulative_seconds": cumulative,
        })
    rows.sort(key=lambda row: (
        -row["cumulative_seconds"], row["file"], row["line"], row["function"]))
    return rows[:limit]


def _profile_sample(spec: RootSpec, raw: dict, cards: tuple[int, ...],
                    method: str, backend: str,
                    config: BenchmarkConfiguration, profile_dir: Path,
                    relative_dir: Path) -> dict:
    profile_dir.mkdir(parents=True, exist_ok=True)
    parent_path = profile_dir / "parent.pstats"
    worker_dir = profile_dir / "workers"
    worker_dir.mkdir()
    previous_worker_profile = os.environ.get("PUCT_WORKER_PROFILE_DIR")
    if METHOD_SPECS[method].pilot is DecisionPilot.PUCT:
        os.environ["PUCT_WORKER_PROFILE_DIR"] = str(worker_dir)
    else:
        os.environ.pop("PUCT_WORKER_PROFILE_DIR", None)
    profiler = cProfile.Profile()
    decision = None
    failure = None
    peak_bytes = 0
    allocations = []
    started = None
    elapsed = None
    try:
        with _prepared_runtime(spec, raw, cards, method, backend, config) as (
                agent_runtime, payload):
            tracemalloc.start()
            started = perf_counter()
            profiler.enable()
            try:
                decision = agent_runtime.decide(payload)
            finally:
                profiler.disable()
            elapsed = perf_counter() - started
            snapshot = tracemalloc.take_snapshot()
            _current_bytes, peak_bytes = tracemalloc.get_traced_memory()
            for allocation in snapshot.statistics("lineno")[:30]:
                frame = allocation.traceback[0]
                allocations.append({
                    "file": frame.filename, "line": frame.lineno,
                    "size_bytes": allocation.size, "count": allocation.count,
                })
    except Exception as exc:
        failure = {"type": type(exc).__name__, "message": str(exc)[:2000]}
    finally:
        profiler.disable()
        if tracemalloc.is_tracing():
            tracemalloc.stop()
        if previous_worker_profile is None:
            os.environ.pop("PUCT_WORKER_PROFILE_DIR", None)
        else:
            os.environ["PUCT_WORKER_PROFILE_DIR"] = previous_worker_profile
    profiler.dump_stats(parent_path)
    worker_paths = sorted(worker_dir.glob("*.pstats"))
    parent_stats = pstats.Stats(str(parent_path))
    worker_stats = (None if not worker_paths
                    else pstats.Stats(*(str(path) for path in worker_paths)))
    relative_parent = (relative_dir / "parent.pstats").as_posix()
    relative_workers = [
        (relative_dir / "workers" / path.name).as_posix()
        for path in worker_paths]
    signature = None if decision is None else _signature(decision)
    return {
        "elapsed_seconds": elapsed,
        "failure": failure,
        "signature_id": None if signature is None else _identity(signature),
        "decision_signature_id": (
            None if signature is None else _identity(_decision_signature(signature))),
        "metrics": None if decision is None else _metrics(decision),
        "parent": {
            "pstats": relative_parent,
            "top_functions": _top_functions(parent_stats),
        },
        "workers": {
            "pstats": relative_workers,
            "top_functions": _top_functions(worker_stats),
        },
        "memory": {
            "peak_bytes": peak_bytes,
            "top_allocations": allocations,
        },
    }


def _timing(samples: list[dict]) -> dict:
    completed = [sample for sample in samples if sample["failure"] is None]
    values = [sample["elapsed_seconds"] for sample in completed]
    simulations = [sample["metrics"]["simulations"] for sample in completed
                   if sample["metrics"]["simulations"] is not None]
    median_seconds = None if not values else statistics.median(values)
    return {
        "attempts": len(samples),
        "completed": len(completed),
        "failed": len(samples) - len(completed),
        "median_seconds": median_seconds,
        "p95_seconds": _percentile(values, 0.95),
        "maximum_seconds": None if not values else max(values),
        "first_seconds": None if not values else values[0],
        "repeat_median_seconds": None if not values else statistics.median(values[1:] or values),
        "simulations_per_second": (
            None if not simulations or median_seconds is None or median_seconds <= 0
            else statistics.median(simulations) / median_seconds),
    }


def _source_identity(output_root: Path) -> dict:
    source = git_source_identity(REPO, allow_dirty=True, exclude_paths=(output_root,))
    branch = subprocess.run(
        ["git", "branch", "--show-current"], cwd=REPO, text=True,
        check=True, capture_output=True).stdout.strip()
    return {"branch": branch or None, **source}


def _publish_stage(stage: Path, target: Path) -> None:
    for attempt in range(5):
        try:
            stage.rename(target)
            return
        except PermissionError:
            if attempt == 4:
                raise
            sleep(0.05 * (2 ** attempt))


def _card_names(results: list[dict]) -> dict[str, str]:
    card_ids = set()

    def collect(value):
        if isinstance(value, dict):
            if value.get("$type") == "Card":
                card_ids.add(int(value["fields"]["card_id"]))
            for child in value.values():
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    for result in results:
        for node in (result.get("tree") or {}).get("nodes", ()):
            collect(json.loads(node["observation"]))
    store = card_store()
    return {str(card_id): getattr(store.get(card_id), "name", f"Card {card_id}")
            for card_id in sorted(card_ids)}


def _root_observation(spec: RootSpec, episode: SavedEpisode) -> tuple[dict, dict]:
    try:
        raw = episode.agent_observation(spec.step, spec.seat)
    except LookupError as exc:
        raise ValueError(f"invalid Search Timing root {spec.root_id!r}") from exc
    if not raw.get("search_begin_input"):
        raise ValueError(f"Search Timing root {spec.root_id!r} is not native search input")
    select = raw.get("select") or {}
    if select.get("context") != 0 or (raw.get("current") or {}).get("yourIndex") != spec.seat:
        raise ValueError(f"Search Timing root {spec.root_id!r} is not a Main decision")
    _strategy, current_cards = _agent_definition(spec.agent)
    current_deck = Counter(current_cards)
    replay_deck = Counter(episode.decks[spec.seat])
    return raw, {
        "replay": str(spec.replay_path.relative_to(REPO)).replace("\\", "/"),
        "episode_id": episode.episode_id,
        "replay_sha256": episode.source_sha256,
        "step": spec.step, "seat": spec.seat,
        "observation_sha256": _identity(raw),
        "observation_bytes": len(_canonical(raw)),
        "deck_matches_current": replay_deck == current_deck,
        "deck_overlap_cards": sum((replay_deck & current_deck).values()),
        "runtime_deck": "recorded_episode",
        "runtime_deck_sha256": _identity(list(episode.decks[spec.seat])),
    }


def _artifact_timing_gate(artifact: dict | None, samples: list[dict]) -> str:
    if artifact is None:
        return "not_measured"
    if artifact.get("failure") is not None:
        return "failed"
    completed = [sample for sample in samples if sample.get("failure") is None]
    if not completed:
        return "not_measured"
    if artifact.get("signature_id") in {sample["signature_id"] for sample in completed}:
        return "matching"
    if artifact.get("decision_signature_id") in {
            sample["decision_signature_id"] for sample in completed}:
        return "value_diverged"
    return "diverged"


def _semantic_gates(results: list[dict]) -> None:
    for result in results:
        peers = [row for row in results if row["root_id"] == result["root_id"]
                 and row["method"] == result["method"]]
        decision_ids = [sample["decision_signature_id"]
                        for row in peers for sample in row["samples"]]
        value_ids = [sample["signature_id"] for row in peers for sample in row["samples"]]
        backend_count = len({row["backend"] for row in peers})
        if not decision_ids:
            decision_gate = "not_measured"
        elif any(value is None for value in decision_ids):
            decision_gate = "failed"
        elif len(set(decision_ids)) != 1:
            decision_gate = "diverged"
        else:
            decision_gate = "matching"
        value_gate = (
            "not_measured" if not value_ids
            else "failed" if any(value is None for value in value_ids)
            else "matching" if len(set(value_ids)) == 1 else "diverged")
        result["decision_gate"] = decision_gate
        result["value_gate"] = value_gate
        result["semantic_gate"] = (
            "not_measured" if decision_gate == "not_measured"
            else "failed" if "failed" in (decision_gate, value_gate)
            else "single_backend" if backend_count == 1
            else "comparable" if (decision_gate, value_gate) == ("matching", "matching")
            else "not_comparable")


def _collect_results(config: BenchmarkConfiguration, prepared: list[tuple],
                     scratch: Path) -> tuple[list[dict], float]:
    batch_started = perf_counter()
    results = []
    rows = {}
    arms = []
    for root_index, (spec, raw, cards, root_source) in enumerate(prepared):
        for method_index, method in enumerate(config.methods):
            for backend in config.backends:
                row = {
                    "root_id": spec.root_id, "agent": spec.agent,
                    "frame_class": spec.frame_class, "description": spec.description,
                    "root_source": root_source,
                    "method": method, "backend": backend,
                    "semantic_gate": None, "decision_gate": None, "value_gate": None,
                    "timing": None, "metrics": None, "samples": [],
                    "profile": None, "tree": None, "tree_evidence": None,
                }
                results.append(row)
                rows[(spec.root_id, method, backend)] = row
            arms.append((spec, raw, cards, method, root_index + method_index))

    execution_order = 0
    for spec, raw, cards, method, order_index in arms:
        if "timing" in config.artifacts:
            for repetition in range(config.repetitions):
                backends = (config.backends
                            if (order_index + repetition) % 2 == 0
                            else tuple(reversed(config.backends)))
                for order_in_repetition, backend in enumerate(backends):
                    sample = _timed_sample(
                        spec, raw, cards, method, backend, config)
                    sample.update({
                        "repetition": repetition,
                        "order_in_repetition": order_in_repetition,
                        "execution_order": execution_order,
                    })
                    rows[(spec.root_id, method, backend)]["samples"].append(sample)
                    execution_order += 1
        for backend in config.backends:
            row = rows[(spec.root_id, method, backend)]
            samples = row["samples"]
            completed = [sample for sample in samples if sample["metrics"] is not None]
            row["timing"] = _timing(samples) if samples else None
            row["metrics"] = None if not completed else completed[-1]["metrics"]

    for spec, raw, cards, method, order_index in arms:
        if "profile" not in config.artifacts:
            continue
        if config.artifact_roots and spec.root_id not in config.artifact_roots:
            continue
        backends = (config.backends if order_index % 2 == 0
                    else tuple(reversed(config.backends)))
        for backend in backends:
            row = rows[(spec.root_id, method, backend)]
            relative = Path("profiles") / spec.root_id / method / backend
            profile = _profile_sample(
                spec, raw, cards, method, backend, config,
                scratch / relative, relative)
            profile["timing_gate"] = _artifact_timing_gate(profile, row["samples"])
            row["profile"] = profile

    for spec, raw, cards, method, order_index in arms:
        if "tree" not in config.artifacts or not METHOD_SPECS[method].supports_tree:
            continue
        if config.artifact_roots and spec.root_id not in config.artifact_roots:
            continue
        backends = (config.backends if order_index % 2 == 0
                    else tuple(reversed(config.backends)))
        for backend in backends:
            row = rows[(spec.root_id, method, backend)]
            evidence = _tree_sample(spec, raw, cards, method, backend, config)
            row["tree"] = evidence.pop("tree")
            evidence["timing_gate"] = _artifact_timing_gate(evidence, row["samples"])
            row["tree_evidence"] = evidence
    return results, perf_counter() - batch_started


def run_benchmark(config: BenchmarkConfiguration, output_root: Path) -> Path:
    specs = root_specs(config.suite)
    selected = set(config.roots)
    cases = [spec for spec in specs if not selected or spec.root_id in selected]
    missing = selected - {spec.root_id for spec in cases}
    if missing:
        raise ValueError(f"unknown Search Timing root(s): {', '.join(sorted(missing))}")
    if config.artifact_roots:
        unknown = set(config.artifact_roots) - {spec.root_id for spec in cases}
        if unknown:
            raise ValueError(f"unknown artifact root(s): {', '.join(sorted(unknown))}")
    output_root = Path(output_root).resolve()
    replay_cache = {}
    prepared = []
    for spec in cases:
        if spec.replay_path not in replay_cache:
            replay_cache[spec.replay_path] = load_saved_episode(spec.replay_path)
        episode = replay_cache[spec.replay_path]
        raw, source = _root_observation(spec, episode)
        prepared.append((spec, raw, episode.decks[spec.seat], source))
    output_root.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix=".search-timing-profiles-", dir=output_root))
    try:
        results, batch_seconds = _collect_results(config, prepared, scratch)
        _semantic_gates(results)
        generated = datetime.now().astimezone()
        body = {
            "schema": "search-timing-run", "schema_version": 1,
            "title": config.title, "generated_at": generated.isoformat(),
            "timezone": generated.tzname() or "local",
            "source": _source_identity(output_root),
            "host": {
                "python": sys.version.split()[0], "platform": sys.platform,
            },
            "suite": {"name": config.suite, "roots": len(cases)},
            "configuration": asdict(config),
            "cards": _card_names(results),
            "batch_seconds": batch_seconds, "results": results,
        }
        run_id = _identity(body)
        document = {**body, "run_id": run_id}
        stamp = generated.strftime("%Y%m%dT%H%M%S%z")
        target = output_root / f"{stamp}_{run_id[:12]}"
        if target.exists():
            raise ValueError(f"Search Timing Run already exists: {target}")
        stage = Path(tempfile.mkdtemp(prefix=f".{target.name}-", dir=output_root))
        try:
            profiles = scratch / "profiles"
            if profiles.exists():
                shutil.copytree(profiles, stage / "profiles")
            run_path = stage / "run.json"
            run_path.write_text(
                json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                encoding="utf-8", newline="\n")
            write_report(run_path)
            _publish_stage(stage, target)
        except Exception:
            shutil.rmtree(stage, ignore_errors=True)
            raise
        return target / "run.json"
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Ledger/PUCT timing, profiling, and tree-inspection passes",
        epilog=(
            "Artifacts are isolated passes: profiling and tree capture never affect timing samples. "
            "Use --artifact-root to confine expensive diagnostics while timing every selected root."))
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="run one benchmark suite")
    run.add_argument("--suite", choices=("core9",), default="core9")
    run.add_argument("--methods", default="ledger_one_ply,puct_uniform")
    run.add_argument("--backends", default="native-cg,cgpy")
    run.add_argument(
        "--artifacts", default="timing,profile",
        help="comma-separated isolated passes: timing, profile, tree")
    run.add_argument("--root", action="append", default=[])
    run.add_argument(
        "--artifact-root", action="append", default=[],
        help="root receiving profile/tree passes; repeat as needed (default: every selected root)")
    run.add_argument("--repetitions", type=int, default=3)
    run.add_argument("--simulations", type=int, default=128)
    run.add_argument("--workers", type=int, default=1)
    run.add_argument("--batch-size", type=int, default=1)
    run.add_argument("--time-limit", type=float, default=60.0)
    run.add_argument("--chance-samples", type=int, default=12)
    run.add_argument("--transition-limit", type=int, default=100_000)
    run.add_argument("--evaluation-limit", type=int, default=100_000)
    run.add_argument("--chance-limit", type=int, default=10_000)
    run.add_argument("--state-limit", type=int, default=50_000)
    run.add_argument("--node-limit", type=int, default=50_000)
    run.add_argument("--cache-limit", type=int, default=150_000)
    run.add_argument("--outstanding-limit", type=int, default=32)
    run.add_argument("--ipc-message-bytes", type=int, default=16 * 1024 * 1024)
    run.add_argument("--title", default="Ledger and PUCT search timing")
    run.add_argument("--out", type=Path, default=DEFAULT_RUNS)
    render = commands.add_parser("render", help="regenerate HTML from an existing run.json")
    render.add_argument("run", type=Path)
    render.add_argument("--out", type=Path)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "render":
        from train.search_timing_report import write_report

        print(write_report(args.run, args.out))
        return 0
    parse = lambda value: tuple(item.strip() for item in value.split(",") if item.strip())
    config = BenchmarkConfiguration(
        suite=args.suite, title=args.title, methods=parse(args.methods),
        backends=parse(args.backends), artifacts=parse(args.artifacts),
        roots=tuple(args.root), artifact_roots=tuple(args.artifact_root),
        repetitions=args.repetitions, simulations=args.simulations,
        workers=args.workers, batch_size=args.batch_size,
        time_limit=args.time_limit, chance_samples=args.chance_samples,
        transition_limit=args.transition_limit, evaluation_limit=args.evaluation_limit,
        chance_limit=args.chance_limit, state_limit=args.state_limit,
        node_limit=args.node_limit, cache_limit=args.cache_limit,
        outstanding_limit=args.outstanding_limit,
        ipc_message_bytes=args.ipc_message_bytes)
    print(run_benchmark(config, args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
