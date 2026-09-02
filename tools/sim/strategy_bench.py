"""Run timed local matches, save decision CSV telemetry, and report search timing.

`--no-emit` runs the contestants with telemetry off. Search timing then has no source, but
`round_trip_seconds` — the harness clock around one ask/answer — is measured either way, so
the same run with and without the flag prices the whole telemetry path.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path
from statistics import mean
from time import monotonic

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]
from sim.artifacts import lethal_proof_seconds  # noqa: E402
from common.ledger.baseline import require_baseline  # noqa: E402


def default_jobs() -> int:
    return max(1, (os.cpu_count() or 2) - 2)


def pin_ledger_baseline(config: dict) -> dict:
    from sim.correction_run import _ledger_identity
    from sim.run_identity import agent_identity

    path = config.get("ledger_baseline_path")
    expected = config.get("ledger_baseline_id")
    if not path or not expected:
        raise ValueError("benchmark requires a Ledger Baseline path and identity")
    baseline = require_baseline(str(expected), Path(path))
    if _ledger_identity() != baseline["ledger"]:
        raise ValueError("benchmark Ledger runtime differs from the frozen baseline")
    agents_root = Path(config["agents_root"])
    for name in set(config["agents"]):
        frozen = baseline["contestants"].get(name)
        if frozen is None:
            raise ValueError(f"benchmark agent {name!r} is absent from the frozen baseline")
        current = agent_identity(agents_root, name)
        for field in ("deck_sha256", "ledger_overlay_sha256"):
            if current.get(field) != frozen.get(field):
                raise ValueError(
                    f"benchmark agent {name!r} {field} differs from the frozen baseline")
    return {**config, "ledger_baseline": {
        "path": str(Path(path)), "baseline_id": baseline["baseline_id"],
    }}


def _agent_decision_seconds(decision_timeout: float) -> float:
    seconds = float(decision_timeout)
    fallback_tail = min(5.0, max(1.0, seconds * 0.05))
    return max(0.1, seconds - fallback_tail)


def _percentile(values, fraction):
    values = sorted(float(value) for value in values)
    if not values:
        return 0.0
    return values[min(len(values) - 1, round((len(values) - 1) * fraction))]


def summarize_decisions(records) -> dict:
    timed = [row for row in records if row.get("decision_seconds") is not None]
    found = [row for row in timed if row.get("first_found_seconds") is not None]
    stabilized = [row for row in timed if row.get("stabilized_seconds") is not None]
    recoverable = [row["first_recoverable_seconds"] for row in timed
                   if row.get("first_recoverable_seconds") is not None]
    full = [row["first_full_seconds"] for row in timed
            if row.get("first_full_seconds") is not None]
    totals = [row["decision_seconds"] for row in timed]
    first = [row["first_found_seconds"] for row in found]
    stable = [row["stabilized_seconds"] for row in stabilized]
    lethal = [row["lethal_proof_seconds"] for row in records
              if row.get("lethal_proof_seconds") is not None]
    trips = [row["round_trip_seconds"] for row in records
             if row.get("round_trip_seconds") is not None]
    waves = {name: sum(row.get("strategy_wave") == name for row in stabilized)
             for name in ("first", "widening")}
    return {
        "decisions": len(records),
        "timed_decisions": len(timed),
        "stabilized_decisions": len(stabilized),
        "deadline_hits": sum(bool(row.get("deadline_hit")) for row in records),
        "round_trip_seconds": {
            "samples": len(trips),
            "avg": mean(trips) if trips else 0.0,
            "p95": _percentile(trips, 0.95),
            "max": max(trips, default=0.0),
        },
        "decision_seconds": {
            "avg": mean(totals) if totals else 0.0,
            "p95": _percentile(totals, 0.95),
            "max": max(totals, default=0.0),
        },
        "first_found_seconds": {
            "avg": mean(first) if first else 0.0,
            "p95": _percentile(first, 0.95),
            "max": max(first, default=0.0),
        },
        "first_recoverable_seconds": {
            "avg": mean(recoverable) if recoverable else 0.0,
            "p95": _percentile(recoverable, 0.95),
            "max": max(recoverable, default=0.0),
        },
        "first_full_seconds": {
            "avg": mean(full) if full else 0.0,
            "p95": _percentile(full, 0.95),
            "max": max(full, default=0.0),
        },
        "stabilized_seconds": {
            "avg": mean(stable) if stable else 0.0,
            "p95": _percentile(stable, 0.95),
            "max": max(stable, default=0.0),
        },
        "lethal_proof_seconds": {
            "samples": len(lethal),
            "avg": mean(lethal) if lethal else 0.0,
            "min": min(lethal, default=0.0),
            "max": max(lethal, default=0.0),
        },
        "strategy_waves": waves,
    }


def summarize_matches(matches) -> dict:
    durations = [row["seconds"] for row in matches if row.get("seconds") is not None]
    return {
        "samples": len(durations),
        "avg": mean(durations) if durations else 0.0,
        "min": min(durations, default=0.0),
        "max": max(durations, default=0.0),
    }


def paired_telemetry_overhead(emitting, baseline) -> dict:
    emitting = tuple(float(value) for value in emitting)
    baseline = tuple(float(value) for value in baseline)
    if not emitting or len(emitting) != len(baseline) or any(value <= 0 for value in baseline):
        raise ValueError("paired telemetry benchmark requires equal positive match samples")
    overhead = (sum(emitting) - sum(baseline)) / sum(baseline)
    return {"overhead": overhead}


def decision_metrics(records, *, match_index, contestants) -> list[dict]:
    rows = []
    for record in records:
        if record.get("record_type") == "outcome":
            continue
        ledger = record.get("schema") == "ledger.telemetry"
        production = ((record.get("diagnostics") or {}).get("production") or {})
        incumbent = production.get("final_incumbent") or {}
        snapshot = (record.get("diagnostics") or {}).get("strategy_snapshot") or {}
        fallback = (record.get("diagnostics") or {}).get("fallback") or {}
        decision = record.get("decision") or {}
        timing = record.get("timing") or {}
        seat = int(record.get("engine_seat", decision.get("seat", record.get("seat", 0))))
        chosen_id = decision.get("chosen_action_id")
        chosen_action = next((action for action in record.get("actions") or ()
                              if action.get("id") == chosen_id), None)
        chosen_candidate = next((candidate for candidate in record.get("candidates") or ()
                                 if candidate.get("action_id") == chosen_id), None)
        delta = None if chosen_candidate is None else chosen_candidate.get("delta")
        decision_seconds = (timing.get("decision_seconds") if ledger
                            else record.get("decision_seconds"))
        rows.append({
            "match": match_index,
            "decision": int(record.get("decision_index", decision.get("index", len(rows)))),
            "turn": decision.get("turn") if ledger else snapshot.get("turn"),
            "seat": seat,
            "agent": contestants[seat],
            "action": (chosen_action or {}).get("identity") if ledger else record.get("action"),
            "value": (delta or {}).get("total") if ledger else record.get("value"),
            "complete": record.get("completeness") == "complete" if ledger
                        else record.get("complete"),
            "round_trip_seconds": record.get("round_trip_seconds"),
            "decision_seconds": decision_seconds,
            "decision_limit_seconds": (timing.get("decision_limit_seconds") if ledger
                                       else record.get("decision_limit_seconds")),
            "deadline_hit": (timing.get("deadline_hit") if ledger
                             else record.get("deadline_hit")),
            "lethal_proof_seconds": lethal_proof_seconds(record),
            "total_search_seconds": incumbent.get("search_seconds", decision_seconds),
            "first_found_seconds": incumbent.get("first_found_seconds"),
            "first_recoverable_seconds": incumbent.get("first_recoverable_seconds"),
            "first_full_seconds": incumbent.get("first_full_seconds"),
            "stabilized_seconds": incumbent.get("stabilized_seconds"),
            "remaining_search_seconds": (
                max(0.0, float(incumbent.get("search_seconds", decision_seconds))
                    - float(incumbent["stabilized_seconds"]))
                if incumbent.get("stabilized_seconds") is not None
                and incumbent.get("search_seconds", decision_seconds) is not None
                else None),
            "strategy_wave": incumbent.get("strategy_wave"),
            "strategy_focus_position": incumbent.get("strategy_focus_position"),
            "strategy_focus_count": incumbent.get("strategy_focus_count"),
            "incumbent_timeline": production.get("incumbent_timeline") or [],
            "execution_tier": production.get("execution_tier"),
            "fallback_cause": fallback.get("cause"),
            "fallback_choice": fallback.get("chosen"),
            "phase_budgets": production.get("phase_budgets") or {},
            "protected_bundles": production.get("protected_bundles") or {},
            "challengers": production.get("challengers") or {},
        })
    return rows


_CSV_FIELDS = (
    "match", "decision", "turn", "seat", "agent", "action", "value", "complete",
    "round_trip_seconds",
    "decision_seconds", "decision_limit_seconds", "deadline_hit", "lethal_proof_seconds",
    "total_search_seconds", "first_found_seconds", "first_recoverable_seconds",
    "first_full_seconds", "stabilized_seconds", "execution_tier", "fallback_cause",
    "remaining_search_seconds", "strategy_wave", "strategy_focus_position",
    "strategy_focus_count",
)


def write_decisions_csv(run_dir, decisions) -> Path:
    path = Path(run_dir) / "decisions.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for decision in decisions:
            row = dict(decision)
            if isinstance(row.get("action"), (dict, list, tuple)):
                row["action"] = json.dumps(row["action"], separators=(",", ":"))
            writer.writerow(row)
    return path


def _focus(row) -> str:
    position = row.get("strategy_focus_position")
    count = row.get("strategy_focus_count")
    return f"{position} of {count}" if position is not None else "not focused"


def format_report(payload: dict, hotspot_count=10) -> str:
    config, summary = payload["config"], payload["summary"]
    decision = summary["decision_seconds"]
    trip = summary["round_trip_seconds"]
    matches = payload["matches"]
    match_time = summary.get("match_seconds", summarize_matches(matches))
    emit = bool(config.get("emit", True))
    wins = [sum(row["winner_seat"] == seat for row in matches) for seat in (0, 1)]
    lines = [
        f"Strategy Bench -- {config['mode']} -- {len(payload['matches'])} matches -- "
        f"{config.get('jobs', 1)} jobs",
        f"Decision timeout {config['decision_timeout']}s | agent budget "
        f"{_agent_decision_seconds(config['decision_timeout']):g}s | "
        f"match timeout {config['match_timeout']}s",
        f"Seat wins {wins[0]}-{wins[1]} | draws {sum(row['winner_seat'] is None for row in matches)} | "
        f"decision timeouts {sum(bool(row['timed_out']) for row in matches)} | "
        f"agent crashes {sum(bool(row.get('crashed')) for row in matches)} | "
        f"match timeouts {sum(row['match_deadline_hit'] for row in matches)}",
        f"Match time avg {match_time['avg']:.2f}s | min {match_time['min']:.2f}s | "
        f"max {match_time['max']:.2f}s",
        f"Decisions {summary['decisions']} | measured Bellman searches "
        f"{summary['stabilized_decisions']} | deadline hits {summary['deadline_hits']}",
        f"Telemetry emission {'on' if emit else 'off'} | round trip avg {trip['avg']:.2f}s | "
        f"p95 {trip['p95']:.2f}s | max {trip['max']:.2f}s",
        "",
        "Match time per match:",
        *(f"Match {row['match']}: {row['seconds']:.3f}s"
          for row in matches if row.get("seconds") is not None),
    ]
    if not summary["timed_decisions"]:
        lines.append(
            "Search timing needs telemetry; compare the round trip against an emitting run.")
        return "\n".join(lines)
    first = summary["first_found_seconds"]
    stable = summary["stabilized_seconds"]
    recoverable = summary["first_recoverable_seconds"]
    full = summary["first_full_seconds"]
    lethal = summary["lethal_proof_seconds"]
    lines += [
        f"Decision time avg {decision['avg']:.2f}s | p95 {decision['p95']:.2f}s | max {decision['max']:.2f}s",
        f"Final incumbent first found avg {first['avg']:.2f}s | p95 {first['p95']:.2f}s | max {first['max']:.2f}s",
        f"First recoverable avg {recoverable['avg']:.2f}s | p95 {recoverable['p95']:.2f}s | max {recoverable['max']:.2f}s",
        f"First fully planned avg {full['avg']:.2f}s | p95 {full['p95']:.2f}s | max {full['max']:.2f}s",
        f"Final incumbent stabilized avg {stable['avg']:.2f}s | p95 {stable['p95']:.2f}s | max {stable['max']:.2f}s",
        f"Lethal solver avg {lethal['avg']:.3f}s | min {lethal['min']:.3f}s | max {lethal['max']:.3f}s",
        f"Final Strategy wave: first {summary['strategy_waves']['first']} | "
        f"widening {summary['strategy_waves']['widening']}",
        "",
        "Hotspots by final-incumbent stabilization time:",
    ]
    hotspots = sorted(
        (row for row in payload["decisions"] if row.get("stabilized_seconds") is not None),
        key=lambda row: row["stabilized_seconds"], reverse=True)[:hotspot_count]
    for index, row in enumerate(hotspots, 1):
        lines.extend((
            f"{index}. match {row['match']} | turn {row['turn']} | decision {row['decision']} | {row['agent']}",
            f"   stabilized {row['stabilized_seconds']:.2f}s of "
            f"{float(row.get('decision_seconds') or 0.0):.2f}s",
            f"   Strategy wave: {row.get('strategy_wave') or 'unavailable'}",
            f"   Strategy focus position: {_focus(row)}",
        ))
    failures = [row for row in matches if row.get("failure")]
    if failures:
        lines.extend(("", "Match failures:", *(
            f"Match {row['match']}: {row['failure']}" for row in failures)))
    return "\n".join(lines)


def _pairings(mode, agents, matches, seed):
    if mode == "mirror":
        return [(agents[0], agents[0]) for _ in range(matches)]
    if mode == "versus":
        return [(agents[index % 2], agents[1 - index % 2]) for index in range(matches)]
    rng = random.Random(seed)
    return [tuple(rng.sample(agents, 2)) for _ in range(matches)]


def save_match_artifacts(run_dir, episode_id, replay, records) -> Path:
    from sim.artifacts import save_legacy_telemetry

    path = Path(run_dir) / f"episode-{episode_id}-replay.json"
    path.write_text(json.dumps(replay, ensure_ascii=False), encoding="utf-8")
    save_legacy_telemetry(Path(run_dir), episode_id, records)
    return path


def _run_match_job(task: dict) -> dict:
    from sim.battle import AgentServer, play_match, read_deck
    from sim.record import MatchRecorder

    config = task["config"]
    index = task["match"]
    names = tuple(task["contestants"])
    agents_root = Path(config["agents_root"])
    run_dir = Path(config["output"])
    dirs = tuple(agents_root / name for name in names)
    for name, directory in zip(names, dirs):
        if not (directory / "main.py").exists():
            raise ValueError(f"unknown working-tree agent {name!r}")
    servers = tuple(AgentServer(
        directory, [REPO / "src"], capture_telemetry=bool(config.get("emit", True)),
        decision_seconds=config["decision_timeout"]) for directory in dirs)
    recorder = MatchRecorder()
    captured = []
    telemetry = []
    started = monotonic()
    try:
        result = play_match(
            servers[0], servers[1], read_deck(dirs[0]), read_deck(dirs[1]),
            recorder=recorder, decision_timeout=config["decision_timeout"],
            match_timeout=config["match_timeout"], metrics=captured,
            telemetry=telemetry, episode_key=str(task["episode_id"]),
            external_episode_id=str(task["episode_id"]))
    finally:
        for server in servers:
            server.close()
    elapsed = monotonic() - started
    replay = recorder.replay(episode_id=task["episode_id"], team_names=list(names))
    replay_path = save_match_artifacts(run_dir, task["episode_id"], replay, telemetry)
    return {
        "match": {
            "match": index, "contestants": names, "winner_seat": result.winner,
            "crashed": result.crashed, "timed_out": result.timed_out,
            "match_deadline_hit": result.match_deadline_hit, "seconds": elapsed,
            "failure": result.failure,
            "replay": replay_path.name,
        },
        "decisions": decision_metrics(captured, match_index=index, contestants=names),
    }


def _run_jobs(tasks, *, jobs, worker=None) -> list[dict]:
    worker = worker or _run_match_job
    if jobs <= 1 or len(tasks) <= 1:
        return [worker(task) for task in tasks]
    with ProcessPoolExecutor(max_workers=min(jobs, len(tasks))) as pool:
        return list(pool.map(worker, tasks))


def run(config: dict) -> dict:
    config = pin_ledger_baseline(config)
    pairings = _pairings(config["mode"], config["agents"], config["matches"], config["seed"])
    run_dir = Path(config["output"])
    run_dir.mkdir(parents=True, exist_ok=True)
    episode_base = int(datetime.now().timestamp() * 1_000_000)
    tasks = [{
        "match": index, "contestants": names, "episode_id": episode_base + index,
        "config": config,
    } for index, names in enumerate(pairings, 1)]
    results = _run_jobs(tasks, jobs=int(config.get("jobs", 1)))
    matches = [result["match"] for result in results]
    decisions = [decision for result in results for decision in result["decisions"]]
    payload = {"config": config, "matches": matches, "decisions": decisions}
    payload["summary"] = {
        **summarize_decisions(decisions),
        "match_seconds": summarize_matches(matches),
    }
    payload["decision_csv"] = write_decisions_csv(run_dir, decisions).name
    (run_dir / "report.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    mirror = sub.add_parser("mirror", help="one working-tree agent plays itself")
    mirror.add_argument("agent")
    versus = sub.add_parser("versus", help="two named agents alternate engine seats")
    versus.add_argument("agent_a")
    versus.add_argument("agent_b")
    gauntlet = sub.add_parser("gauntlet", help="random distinct pairings from named agents")
    gauntlet.add_argument("agents", nargs="+")
    for command in (mirror, versus, gauntlet):
        command.add_argument("-n", "--matches", type=int, default=10)
        command.add_argument("--decision-timeout", type=float, required=True)
        command.add_argument("--match-timeout", type=float, required=True)
        command.add_argument("--seed", type=int, default=1)
        command.add_argument("--jobs", type=int, default=default_jobs(),
                             help="parallel matches (default: logical CPUs minus two)")
        command.add_argument("--agents-root", default=str(REPO / "src" / "agents"))
        command.add_argument("--ledger-baseline", type=Path, required=True)
        command.add_argument("--ledger-baseline-id", required=True)
        command.add_argument("--output")
        command.add_argument("--no-emit", action="store_true",
                             help="run the contestants with AGENT_NO_TELEMETRY=1: no record is "
                                  "built, serialised, or shipped, so the round-trip clock shows "
                                  "what telemetry costs")
    args = parser.parse_args(argv)
    agents = ([args.agent] if args.mode == "mirror" else
              [args.agent_a, args.agent_b] if args.mode == "versus" else args.agents)
    if args.mode == "gauntlet" and len(set(agents)) < 2:
        parser.error("gauntlet requires at least two distinct agents")
    if args.matches < 1:
        parser.error("matches must be at least 1")
    if args.decision_timeout < 2:
        parser.error("decision timeout must be at least 2 seconds")
    if args.match_timeout <= 0:
        parser.error("match timeout must be positive")
    if args.jobs < 1:
        parser.error("jobs must be at least 1")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output = args.output or str(REPO / "data" / "reports" / "strategy-bench" / stamp)
    config = {
        "mode": args.mode, "agents": agents, "matches": args.matches,
        "decision_timeout": args.decision_timeout, "match_timeout": args.match_timeout,
        "seed": args.seed, "jobs": args.jobs, "agents_root": args.agents_root, "output": output,
        "emit": not args.no_emit, "ledger_baseline_path": str(args.ledger_baseline),
        "ledger_baseline_id": args.ledger_baseline_id,
    }
    payload = run(config)
    print(format_report(payload))
    print(f"\nCSV + JSON + replays: {output}")
    return 0


if __name__ == "__main__":
    sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]
    raise SystemExit(main())
