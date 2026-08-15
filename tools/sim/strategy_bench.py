"""Run timed local matches, save decision CSV telemetry, and report search timing."""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from datetime import datetime
from pathlib import Path
from statistics import mean
from time import monotonic

REPO = Path(__file__).resolve().parents[2]


def _percentile(values, fraction):
    values = sorted(float(value) for value in values)
    if not values:
        return 0.0
    return values[min(len(values) - 1, round((len(values) - 1) * fraction))]


def summarize_decisions(records) -> dict:
    timed = [row for row in records if row.get("decision_seconds") is not None]
    found = [row for row in timed if row.get("first_found_seconds") is not None]
    stabilized = [row for row in timed if row.get("stabilized_seconds") is not None]
    totals = [row["decision_seconds"] for row in timed]
    first = [row["first_found_seconds"] for row in found]
    stable = [row["stabilized_seconds"] for row in stabilized]
    lethal = [row["lethal_proof_seconds"] for row in records
              if row.get("lethal_proof_seconds") is not None]
    waves = {name: sum(row.get("strategy_wave") == name for row in stabilized)
             for name in ("first", "widening")}
    return {
        "decisions": len(records),
        "timed_decisions": len(timed),
        "stabilized_decisions": len(stabilized),
        "deadline_hits": sum(bool(row.get("deadline_hit")) for row in records),
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


def decision_metrics(records, *, match_index, contestants) -> list[dict]:
    from common.telemetry import lethal_proof_seconds

    rows = []
    for record in records:
        production = ((record.get("diagnostics") or {}).get("production") or {})
        incumbent = production.get("final_incumbent") or {}
        snapshot = (record.get("diagnostics") or {}).get("strategy_snapshot") or {}
        seat = int(record.get("engine_seat", record.get("seat", 0)))
        rows.append({
            "match": match_index,
            "decision": int(record.get("decision_index", len(rows))),
            "turn": snapshot.get("turn"),
            "seat": seat,
            "agent": contestants[seat],
            "action": record.get("action"),
            "value": record.get("value"),
            "complete": record.get("complete"),
            "decision_seconds": record.get("decision_seconds"),
            "decision_limit_seconds": record.get("decision_limit_seconds"),
            "deadline_hit": record.get("deadline_hit"),
            "lethal_proof_seconds": lethal_proof_seconds(record),
            "total_search_seconds": incumbent.get("search_seconds", record.get("decision_seconds")),
            "first_found_seconds": incumbent.get("first_found_seconds"),
            "stabilized_seconds": incumbent.get("stabilized_seconds"),
            "remaining_search_seconds": (
                max(0.0, float(incumbent.get("search_seconds", record.get("decision_seconds")))
                    - float(incumbent["stabilized_seconds"]))
                if incumbent.get("stabilized_seconds") is not None
                and incumbent.get("search_seconds", record.get("decision_seconds")) is not None
                else None),
            "strategy_wave": incumbent.get("strategy_wave"),
            "strategy_focus_position": incumbent.get("strategy_focus_position"),
            "strategy_focus_count": incumbent.get("strategy_focus_count"),
            "incumbent_timeline": production.get("incumbent_timeline") or [],
        })
    return rows


_CSV_FIELDS = (
    "match", "decision", "turn", "seat", "agent", "action", "value", "complete",
    "decision_seconds", "decision_limit_seconds", "deadline_hit", "lethal_proof_seconds",
    "total_search_seconds", "first_found_seconds", "stabilized_seconds",
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
    first = summary["first_found_seconds"]
    stable = summary["stabilized_seconds"]
    lethal = summary["lethal_proof_seconds"]
    matches = payload["matches"]
    lethal_by_match = [
        (match, summarize_decisions(
            [row for row in payload["decisions"] if row["match"] == match]
        )["lethal_proof_seconds"])
        for match in sorted({row["match"] for row in payload["decisions"]})
    ]
    wins = [sum(row["winner_seat"] == seat for row in matches) for seat in (0, 1)]
    lines = [
        f"Strategy Bench -- {config['mode']} -- {len(payload['matches'])} matches",
        f"Decision timeout {config['decision_timeout']}s | match timeout {config['match_timeout']}s",
        f"Seat wins {wins[0]}-{wins[1]} | draws {sum(row['winner_seat'] is None for row in matches)} | "
        f"decision timeouts {sum(bool(row['timed_out']) for row in matches)} | "
        f"match timeouts {sum(row['match_deadline_hit'] for row in matches)}",
        f"Decisions {summary['decisions']} | measured Bellman searches "
        f"{summary['stabilized_decisions']} | deadline hits {summary['deadline_hits']}",
        f"Decision time avg {decision['avg']:.2f}s | p95 {decision['p95']:.2f}s | max {decision['max']:.2f}s",
        f"Final incumbent first found avg {first['avg']:.2f}s | p95 {first['p95']:.2f}s | max {first['max']:.2f}s",
        f"Final incumbent stabilized avg {stable['avg']:.2f}s | p95 {stable['p95']:.2f}s | max {stable['max']:.2f}s",
        f"Lethal solver avg {lethal['avg']:.3f}s | min {lethal['min']:.3f}s | max {lethal['max']:.3f}s",
        f"Final Strategy wave: first {summary['strategy_waves']['first']} | "
        f"widening {summary['strategy_waves']['widening']}",
        "",
        "Lethal solver per match:",
        *(f"Match {match}: avg {sample['avg']:.3f}s | min {sample['min']:.3f}s | "
          f"max {sample['max']:.3f}s"
          for match, sample in lethal_by_match),
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
    return "\n".join(lines)


def _pairings(mode, agents, matches, seed):
    if mode == "mirror":
        return [(agents[0], agents[0]) for _ in range(matches)]
    if mode == "versus":
        return [(agents[index % 2], agents[1 - index % 2]) for index in range(matches)]
    rng = random.Random(seed)
    return [tuple(rng.sample(agents, 2)) for _ in range(matches)]


def save_match_artifacts(run_dir, episode_id, replay, records) -> Path:
    from sim.selfplay import _save_telemetry

    path = Path(run_dir) / f"episode-{episode_id}-replay.json"
    path.write_text(json.dumps(replay, ensure_ascii=False), encoding="utf-8")
    _save_telemetry(Path(run_dir), episode_id, records)
    return path


def run(config: dict) -> dict:
    from sim.battle import AgentServer, play_match, read_deck
    from sim.record import MatchRecorder

    agents_root = Path(config["agents_root"])
    pairings = _pairings(config["mode"], config["agents"], config["matches"], config["seed"])
    run_dir = Path(config["output"])
    run_dir.mkdir(parents=True, exist_ok=True)
    matches, decisions = [], []
    for index, names in enumerate(pairings, 1):
        dirs = tuple(agents_root / name for name in names)
        for name, directory in zip(names, dirs):
            if not (directory / "main.py").exists():
                raise ValueError(f"unknown working-tree agent {name!r}")
        servers = tuple(AgentServer(
            directory, [REPO / "src"], capture_telemetry=True,
            decision_seconds=config["decision_timeout"]) for directory in dirs)
        recorder = MatchRecorder()
        captured = []
        started = monotonic()
        try:
            result = play_match(
                servers[0], servers[1], read_deck(dirs[0]), read_deck(dirs[1]),
                recorder=recorder, decision_timeout=config["decision_timeout"],
                match_timeout=config["match_timeout"], metrics=captured)
        finally:
            for server in servers:
                server.close()
        elapsed = monotonic() - started
        decisions.extend(decision_metrics(captured, match_index=index, contestants=names))
        eid = int(datetime.now().timestamp() * 1_000_000) + index
        replay = recorder.replay(episode_id=eid, team_names=list(names))
        replay_path = save_match_artifacts(run_dir, eid, replay, captured)
        match = {
            "match": index, "contestants": names, "winner_seat": result.winner,
            "crashed": result.crashed, "timed_out": result.timed_out,
            "match_deadline_hit": result.match_deadline_hit, "seconds": elapsed,
            "replay": replay_path.name,
        }
        matches.append(match)
    payload = {"config": config, "matches": matches, "decisions": decisions}
    payload["summary"] = summarize_decisions(decisions)
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
        command.add_argument("--agents-root", default=str(REPO / "src" / "agents"))
        command.add_argument("--output")
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
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output = args.output or str(REPO / "data" / "reports" / "strategy-bench" / stamp)
    config = {
        "mode": args.mode, "agents": agents, "matches": args.matches,
        "decision_timeout": args.decision_timeout, "match_timeout": args.match_timeout,
        "seed": args.seed, "agents_root": args.agents_root, "output": output,
    }
    payload = run(config)
    print(format_report(payload))
    print(f"\nCSV + JSON + replays: {output}")
    return 0


if __name__ == "__main__":
    sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]
    raise SystemExit(main())
