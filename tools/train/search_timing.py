"""Capture and repeatedly time exact turn-search roots."""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import shutil
import statistics
import sys
import tempfile


REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from cgpy.experiment import (  # noqa: E402
    ExperimentParityManifest,
    ExperimentSnapshot,
    PairedSeedCase,
    TeacherBatchCase,
    TeacherBatchRunner,
    TeacherExecutionConfiguration,
    TeacherModelRecord,
    TeacherSearchConfiguration,
    WithinHorizonTeacher,
)
from common.ledger import LedgerValueEvaluator  # noqa: E402
from common.ledger.baseline import baseline_identities, load_baseline  # noqa: E402
from sim.run_identity import git_source_identity  # noqa: E402
from sim.scenario import BodySpec, deck, runtime, scenario  # noqa: E402


CORPUS_SCHEMA = "cgpy-search-timing-corpus"
CORPUS_SCHEMA_VERSION = 1
RUN_SCHEMA = "cgpy-search-timing-run"
RUN_SCHEMA_VERSION = 1
METHODS = ("ledger_one_ply", "teacher_exhaustive", "puct_uniform", "puct_ledger")
STRATA = ("opening", "search", "tactical")
AGENTS = ("dragapult_ex", "mega_lucario", "mega_starmie")
DEFAULT_CORPUS = REPO / "data" / "benchmarks" / "search_timing" / "v1"
DEFAULT_RUNS = REPO / "data" / "search-timing-runs"
DEFAULT_BASELINES = REPO / "data" / "ledger-baselines"
MAX_WORKERS = 8


@dataclass(frozen=True, slots=True)
class RootSpec:
    root_id: str
    agent: str
    stratum: str
    description: str
    scenario_kwargs: dict
    experiment_seed: int


def root_specs() -> tuple[RootSpec, ...]:
    B = BodySpec
    return (
        RootSpec("dragapult-opening", "dragapult_ex", "opening",
                 "A lone Dreepy can bench Budew or preserve the minimal board.", {
                     "me_active": B((119,)), "me_hand": (235,),
                     "them_active": B((119,)), "turn": 3,
                 }, 60901),
        RootSpec("dragapult-search", "dragapult_ex", "search",
                 "Recon Directive chooses between a known gust and search Item.", {
                     "me_active": B((119, 120, 121)),
                     "me_bench": (B((119, 120)),),
                     "me_top": (1182, 1121),
                     "me_deck_count": 8,
                     "them_active": B((119, 120, 121)), "turn": 9,
                 }, 60902),
        RootSpec("dragapult-tactical", "dragapult_ex", "tactical",
                 "Powered Dragapult and Munkidori face a damaged evolved attacker.", {
                     "me_active": B((119, 120, 121), (2, 5)),
                     "me_bench": (B((112,), (7,)),),
                     "me_hand": (1182, 1120, 7), "me_prizes": 2,
                     "them_active": B((119, 120, 121), (2, 5), hp=170),
                     "them_bench": (B((119,)),), "them_prizes": 2, "turn": 9,
                 }, 60903),
        RootSpec("lucario-opening", "mega_lucario", "opening",
                 "Riolu and Makuhita can develop with one Fighting Energy.", {
                     "me_active": B((677,)), "me_bench": (B((673,)),),
                     "me_hand": (678, 6), "them_active": B((677,)), "turn": 3,
                 }, 60904),
        RootSpec("lucario-search", "mega_lucario", "search",
                 "Ultra Ball can expose known Mega Lucario and Hariyama targets.", {
                     "me_active": B((677,)), "me_bench": (B((673,)),),
                     "me_hand": (1121, 6, 6), "me_top": (678, 674),
                     "me_deck_count": 8,
                     "them_active": B((677, 678)), "turn": 9,
                 }, 60905),
        RootSpec("lucario-tactical", "mega_lucario", "tactical",
                 "Powered Mega Lucario can gust before attacking or preserve Boss.", {
                     "me_active": B((677, 678), (6, 6)),
                     "me_bench": (B((673, 674)),),
                     "me_hand": (1182,), "me_prizes": 2,
                     "them_active": B((677, 678), (6,), hp=190),
                     "them_bench": (B((673,)),), "them_prizes": 2, "turn": 9,
                 }, 60906),
        RootSpec("starmie-opening", "mega_starmie", "opening",
                 "Two Staryu can develop with an evolution and Water Energy.", {
                     "me_active": B((1030,)), "me_bench": (B((1030,)),),
                     "me_hand": (1031, 3), "them_active": B((1030,)), "turn": 3,
                 }, 60907),
        RootSpec("starmie-search", "mega_starmie", "search",
                 "Ultra Ball can expose a known Mega Starmie deck top.", {
                     "me_active": B((1030,)), "me_bench": (B((1030,)),),
                     "me_hand": (1121, 3, 17), "me_top": (1031,),
                     "them_active": B((1030, 1031)), "turn": 5,
                 }, 60908),
        RootSpec("starmie-tactical", "mega_starmie", "tactical",
                 "Powered Mega Starmie has gust, disruption, and a damaged mirror target.", {
                     "me_active": B((1030, 1031), (3, 17)),
                     "me_bench": (B((1030,)),),
                     "me_hand": (1182, 1120, 3), "me_prizes": 2,
                     "them_active": B((1030, 1031), (3, 17), hp=180),
                     "them_bench": (B((1030,)),), "them_prizes": 2, "turn": 9,
                 }, 60909),
    )


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def _identity(value) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _default_baseline() -> Path:
    paths = tuple(sorted(DEFAULT_BASELINES.glob("*/manifest.json")))
    if len(paths) != 1:
        raise ValueError("select one frozen Ledger Baseline with --ledger-baseline")
    return paths[0]


def default_workers() -> int:
    return min(max(1, (os.cpu_count() or 1) - 2), MAX_WORKERS)


def _parity_document(parity: ExperimentParityManifest) -> dict:
    return {
        "coverage_identity": parity.coverage_identity,
        "deck_card_ids": list(parity.deck_card_ids),
        "chains": [list(item) for item in parity.chains],
        "identity": parity.identity,
    }


def _load_parity(document: dict) -> ExperimentParityManifest:
    parity = ExperimentParityManifest(
        str(document["coverage_identity"]),
        tuple(map(int, document["deck_card_ids"])),
        tuple((str(name), str(status)) for name, status in document["chains"]))
    if parity.identity != document.get("identity"):
        raise ValueError("Search Timing Corpus parity identity mismatch")
    return parity


def _relative_artifact(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    if root.resolve() not in candidate.parents:
        raise ValueError("Search Timing Corpus artifact escapes its directory")
    return candidate


def capture_corpus(out: Path, *, baseline_path: Path | None = None,
                   source_identity: dict | None = None) -> Path:
    out = Path(out).resolve()
    if out.exists():
        raise ValueError(f"immutable Search Timing Corpus already exists: {out}")
    baseline_path = (baseline_path or _default_baseline()).resolve()
    baseline = load_baseline(baseline_path)
    identities = baseline_identities(baseline)
    decks = {agent: deck(agent) for agent in AGENTS}
    parity = ExperimentParityManifest.capture(decks.values())
    for agent, cards in decks.items():
        model = runtime(agent, cards).ledger.ctx
        if LedgerValueEvaluator.identity != identities.evaluator:
            raise ValueError("current evaluator differs from the frozen Ledger Baseline")
        if model.identity not in identities.evaluation_models:
            raise ValueError(
                f"{agent} Evaluation Model is absent from the frozen Ledger Baseline")

    out.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{out.name}-", dir=out.parent))
    try:
        (stage / "snapshots").mkdir()
        (stage / "cases").mkdir()
        cases = []
        for spec in root_specs():
            engine, _agent_runtime = scenario(spec.agent, **spec.scenario_kwargs)
            snapshot = ExperimentSnapshot.capture(engine, seat=0, provenance={
                "root_id": spec.root_id, "agent": spec.agent,
                "stratum": spec.stratum, "selection": "declared-before-method-results",
            })
            snapshot_relative = f"snapshots/{spec.root_id}.snapshot.json.gz"
            snapshot_path = stage / snapshot_relative
            snapshot.save(snapshot_path)
            paired = PairedSeedCase.create(
                snapshot, experiment_seed=spec.experiment_seed,
                orientation="self-play-mirror", methods=METHODS,
                baseline_identity=identities.baseline, parity=parity)
            case_relative = f"cases/{spec.root_id}.paired-case.json"
            case_path = stage / case_relative
            case_path.write_text(paired.dumps() + "\n", encoding="utf-8")
            cases.append({
                "root_id": spec.root_id, "agent": spec.agent,
                "stratum": spec.stratum, "description": spec.description,
                "experiment_seed": spec.experiment_seed, "deck": decks[spec.agent],
                "snapshot_id": snapshot.snapshot_id,
                "paired_case_id": paired.case_id,
                "snapshot_path": snapshot_relative,
                "snapshot_sha256": _sha256(snapshot_path),
                "paired_case_path": case_relative,
                "paired_case_sha256": _sha256(case_path),
            })
        body = {
            "schema": CORPUS_SCHEMA, "schema_version": CORPUS_SCHEMA_VERSION,
            "methods": list(METHODS), "agents": list(AGENTS), "strata": list(STRATA),
            "selection": {
                "kind": "fixed-synthetic-first-main-roots",
                "rule": "three declared nontrivial strata per developed deck",
                "held_out_quality_evidence": False,
            },
            "baseline": {
                "baseline_id": identities.baseline,
                "manifest_path": baseline_path.relative_to(REPO).as_posix(),
                "manifest_sha256": _sha256(baseline_path),
                "evaluator_identity": identities.evaluator,
                "evaluation_model_identities": list(identities.evaluation_models),
            },
            "parity": _parity_document(parity),
            "source_identity": source_identity or git_source_identity(REPO, allow_dirty=False),
            "cases": cases,
        }
        manifest = {**body, "corpus_id": _identity(body)}
        (stage / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        stage.rename(out)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return out / "manifest.json"


def load_corpus(root: Path) -> tuple[dict, ExperimentParityManifest]:
    root = Path(root).resolve()
    manifest_path = root / "manifest.json" if root.is_dir() else root
    root = manifest_path.parent.resolve()
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    required = {
        "schema", "schema_version", "corpus_id", "methods", "agents", "strata",
        "selection", "baseline", "parity", "source_identity", "cases",
    }
    if set(document) != required or document.get("schema") != CORPUS_SCHEMA \
            or document.get("schema_version") != CORPUS_SCHEMA_VERSION:
        raise ValueError("unsupported Search Timing Corpus schema")
    body = {key: value for key, value in document.items() if key != "corpus_id"}
    if document["corpus_id"] != _identity(body):
        raise ValueError("Search Timing Corpus content digest mismatch")
    if tuple(document["methods"]) != METHODS or tuple(document["agents"]) != AGENTS \
            or tuple(document["strata"]) != STRATA:
        raise ValueError("Search Timing Corpus method or coverage inventory mismatch")
    cases = document["cases"]
    pairs = {(case.get("agent"), case.get("stratum")) for case in cases}
    if len(cases) != len(AGENTS) * len(STRATA) \
            or pairs != {(agent, stratum) for agent in AGENTS for stratum in STRATA} \
            or len({case.get("root_id") for case in cases}) != len(cases):
        raise ValueError("Search Timing Corpus must contain one root per deck and stratum")
    parity = _load_parity(document["parity"])
    baseline = document["baseline"]
    baseline_path = _relative_artifact(REPO, baseline["manifest_path"])
    if _sha256(baseline_path) != baseline["manifest_sha256"]:
        raise ValueError("Search Timing Corpus Ledger Baseline artifact changed")
    frozen = load_baseline(baseline_path)
    identities = baseline_identities(frozen)
    if identities.baseline != baseline["baseline_id"] \
            or identities.evaluator != baseline["evaluator_identity"] \
            or list(identities.evaluation_models) != baseline["evaluation_model_identities"]:
        raise ValueError("Search Timing Corpus Ledger Baseline identity mismatch")
    expected = {(spec.root_id, spec.agent, spec.stratum) for spec in root_specs()}
    if {(case.get("root_id"), case.get("agent"), case.get("stratum"))
            for case in cases} != expected:
        raise ValueError("Search Timing Corpus declared root inventory mismatch")
    for case in cases:
        snapshot_path = _relative_artifact(root, case["snapshot_path"])
        paired_path = _relative_artifact(root, case["paired_case_path"])
        if _sha256(snapshot_path) != case["snapshot_sha256"] \
                or _sha256(paired_path) != case["paired_case_sha256"]:
            raise ValueError(f"Search Timing Corpus artifact changed for {case['root_id']}")
        snapshot = ExperimentSnapshot.load(snapshot_path)
        paired = PairedSeedCase.loads(paired_path.read_text(encoding="utf-8"))
        if snapshot.snapshot_id != case["snapshot_id"] \
                or paired.case_id != case["paired_case_id"] \
                or paired.baseline_identity != baseline["baseline_id"] \
                or paired.experiment_seed != case["experiment_seed"] \
                or paired.methods != METHODS \
                or len(case["deck"]) != 60 \
                or _identity(case["deck"]) != snapshot.deck_identities[0]:
            raise ValueError(f"Search Timing Corpus identity mismatch for {case['root_id']}")
        paired.fork_roots(snapshot, parity=parity)
    return document, parity


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    return sorted(values)[max(0, math.ceil(fraction * len(values)) - 1)]


def _reference_target(result) -> dict | None:
    if result.coverage.value != "complete":
        return None
    document = result.document()
    target = {key: document[key] for key in (
        "root_state_key", "preferred_action", "selected_policy", "leaves",
        "best_full_sequence",
    )}
    return {**target, "target_id": _identity(target)}


def _summaries(rows: list[dict], elapsed_seconds: float) -> dict:
    timings = [row["elapsed_seconds"] for row in rows
               if row["elapsed_seconds"] is not None]
    per_root = []
    for root_id in sorted({row["root_id"] for row in rows}):
        values = [row["elapsed_seconds"] for row in rows
                  if row["root_id"] == root_id and row["elapsed_seconds"] is not None]
        targets = [row["reference_target"]["target_id"] for row in rows
                   if row["root_id"] == root_id and row["reference_target"] is not None]
        target_ids = sorted(set(targets))
        per_root.append({
            "root_id": root_id, "samples": len(values),
            "median_seconds": None if not values else statistics.median(values),
            "p95_seconds": _percentile(values, 0.95),
            "maximum_seconds": None if not values else max(values),
            "reference_target_id": target_ids[0] if len(target_ids) == 1 else None,
            "reference_target_stable": (
                len(targets) == sum(row["root_id"] == root_id for row in rows)
                and len(target_ids) == 1),
        })
    return {
        "requested_roots": len(rows),
        "completed_workers": sum(row["worker_status"] == "completed" for row in rows),
        "complete_searches": sum(row["coverage"] == "complete" for row in rows),
        "batch_elapsed_seconds": elapsed_seconds,
        "throughput_roots_per_second": (
            None if elapsed_seconds <= 0 else len(rows) / elapsed_seconds),
        "median_seconds": None if not timings else statistics.median(timings),
        "p95_seconds": _percentile(timings, 0.95),
        "maximum_seconds": None if not timings else max(timings),
        "per_root": per_root,
    }


def run_teacher(root: Path, *, output: Path, workers: int, repetitions: int,
                roots=(), search_configuration: TeacherSearchConfiguration,
                root_timeout_seconds: float,
                runner: TeacherBatchRunner | None = None) -> Path:
    if not 1 <= workers <= MAX_WORKERS:
        raise ValueError(f"workers must be between 1 and {MAX_WORKERS}")
    if repetitions <= 0:
        raise ValueError("repetitions must be positive")
    corpus, parity = load_corpus(root)
    selected = set(roots)
    cases = [case for case in corpus["cases"]
             if not selected or case["root_id"] in selected]
    missing = selected - {case["root_id"] for case in cases}
    if missing:
        raise ValueError(f"unknown Search Timing root(s): {', '.join(sorted(missing))}")
    corpus_root = (Path(root) if Path(root).is_dir() else Path(root).parent).resolve()
    baseline = corpus["baseline"]
    if LedgerValueEvaluator.identity != baseline["evaluator_identity"]:
        raise ValueError("Teacher evaluator differs from the frozen Ledger Baseline")
    models = {}
    paired_cases = {}
    for case in cases:
        model = runtime(case["agent"], case["deck"]).ledger.ctx
        if model.identity not in baseline["evaluation_model_identities"]:
            raise ValueError(
                f"{case['agent']} Evaluation Model is absent from the frozen Ledger Baseline")
        models[case["root_id"]] = TeacherModelRecord.from_model(model)
        paired_cases[case["root_id"]] = PairedSeedCase.loads(
            _relative_artifact(corpus_root, case["paired_case_path"]).read_text(
                encoding="utf-8"))
    batch_cases = []
    metadata = {}
    for repetition in range(repetitions):
        for case in cases:
            paired = paired_cases[case["root_id"]]
            batch_id = f"{case['root_id']}:{repetition + 1}"
            batch_cases.append(TeacherBatchCase(
                batch_id,
                str(_relative_artifact(corpus_root, case["snapshot_path"])),
                paired.experiment_seed, models[case["root_id"]],
                search_configuration, baseline["baseline_id"], parity))
            metadata[batch_id] = (case, repetition + 1)
    execution = TeacherExecutionConfiguration(
        workers=workers, root_timeout_seconds=root_timeout_seconds)
    batch = (runner or TeacherBatchRunner()).run(batch_cases, execution)
    rows = []
    for item in batch.items:
        case, repetition = metadata[item.case_id]
        result = item.result
        target = None if result is None else _reference_target(result)
        certified = bool(
            target is not None
            and result.evaluator_identity == baseline["evaluator_identity"]
            and result.evaluation_model_identity in baseline["evaluation_model_identities"]
            and result.baseline_identity == baseline["baseline_id"])
        result_document = None if result is None else result.document()
        rows.append({
            "root_id": case["root_id"], "agent": case["agent"],
            "stratum": case["stratum"], "repetition": repetition,
            "worker_status": item.status.value,
            "coverage": None if result is None else result.coverage.value,
            "stop_reason": item.stop_reason.value,
            "failure": item.failure if result is None else result.failure,
            "elapsed_seconds": None if result is None else result.statistics.elapsed_seconds,
            "statistics": None if result is None else asdict(result.statistics),
            "preferred_action": None if result is None else result_document["preferred_action"],
            "best_full_sequence": (
                None if result is None else result_document["best_full_sequence"]),
            "teacher_semantic_identity": (
                None if result is None else result.semantic_identity),
            "reference_target": target,
            "reference_ready": certified,
        })
    generated_at = datetime.now(timezone.utc).isoformat()
    body = {
        "schema": RUN_SCHEMA, "schema_version": RUN_SCHEMA_VERSION,
        "generated_at": generated_at, "corpus_id": corpus["corpus_id"],
        "method": "teacher_exhaustive",
        "method_identity": WithinHorizonTeacher.identity,
        "search_configuration": asdict(search_configuration),
        "search_configuration_identity": search_configuration.identity,
        "execution": asdict(execution),
        "source_identity": git_source_identity(REPO, allow_dirty=True),
        "host": {
            "system": platform.system(), "machine": platform.machine(),
            "processor": platform.processor(), "python": platform.python_version(),
            "logical_cores": os.cpu_count(),
        },
        "results": rows, "summary": _summaries(rows, batch.elapsed_seconds),
    }
    document = {**body, "run_id": _identity(body)}
    output = Path(output)
    if output.suffix.lower() != ".json":
        stamp = generated_at.replace(":", "").replace("+", "_")
        output = output / f"{stamp}_{document['run_id'][:12]}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise ValueError(f"Search Timing Run already exists: {output}")
    output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Capture, verify, and run search timing roots")
    subparsers = parser.add_subparsers(dest="command", required=True)
    capture = subparsers.add_parser("capture", help="publish the immutable nine-root corpus")
    capture.add_argument("--out", type=Path, default=DEFAULT_CORPUS)
    capture.add_argument("--ledger-baseline", type=Path)
    capture.add_argument("--allow-dirty", action="store_true")
    verify = subparsers.add_parser("verify", help="verify corpus identities and artifacts")
    verify.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    run = subparsers.add_parser("run", help="time one implemented search method")
    run.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    run.add_argument("--method", choices=("teacher_exhaustive",),
                     default="teacher_exhaustive")
    run.add_argument("--root", action="append", default=[])
    run.add_argument("--jobs", type=int, default=default_workers())
    run.add_argument("--repetitions", type=int, default=1)
    run.add_argument("--time-cap", type=float, default=600.0)
    run.add_argument("--root-timeout", type=float, default=660.0)
    run.add_argument("--node-cap", type=int, default=100_000)
    run.add_argument("--path-node-cap", type=int, default=512)
    run.add_argument("--chance-branch-cap", type=int, default=100_000)
    run.add_argument("--exact-outcome-limit", type=int, default=16)
    run.add_argument("--chance-samples", type=int, default=12)
    run.add_argument("--noise-tolerance", type=float, default=1e-9)
    run.add_argument("--tie-seed", type=int, default=1178)
    run.add_argument("--out", type=Path, default=DEFAULT_RUNS)
    return parser


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "capture":
        source = git_source_identity(
            REPO, allow_dirty=args.allow_dirty, exclude_paths=(args.out,))
        print(capture_corpus(
            args.out, baseline_path=args.ledger_baseline,
            source_identity=source))
        return 0
    if args.command == "verify":
        document, _parity = load_corpus(args.corpus)
        print(f"verified {document['corpus_id']} ({len(document['cases'])} roots)")
        return 0
    configuration = TeacherSearchConfiguration(
        node_cap=args.node_cap, path_node_cap=args.path_node_cap,
        chance_branch_cap=args.chance_branch_cap,
        exact_outcome_limit=args.exact_outcome_limit,
        chance_sample_count=args.chance_samples,
        time_cap_seconds=args.time_cap,
        noise_tolerance=args.noise_tolerance, tie_seed=args.tie_seed)
    output = run_teacher(
        args.corpus, output=args.out, workers=args.jobs,
        repetitions=args.repetitions, roots=args.root,
        search_configuration=configuration,
        root_timeout_seconds=args.root_timeout)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
