"""Paired unrestricted and Strategy-focused replay mirror."""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from statistics import median
import sys
import time

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO), str(REPO / "tools"), str(REPO / "src")]

from common.deck_tracker import OwnCardModel  # noqa: E402
from common.engine import CgpyTransitionProvider  # noqa: E402
from deprecated.bellman import PilotProfile  # noqa: E402
from deprecated.bellman import build_teacher_runtime  # noqa: E402
from meta_tracker.parse import load_replay  # noqa: E402
from train.blunder.decisions import iter_decisions  # noqa: E402


def _runtime(focused: bool, *, reuse=True, planning_seconds=None):
    agent = REPO / "src" / "agents" / "mega_starmie"
    spec = importlib.util.spec_from_file_location("_strategy_lab_strategy", agent / "strategy.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    deck = tuple(int(value) for value in (agent / "deck.csv").read_text().split())
    runtime = build_teacher_runtime(
        module.STRATEGY, deck, provider_factory=CgpyTransitionProvider)
    values = {"strategy.focus_enabled": float(focused),
              "plan_reuse.enabled": float(reuse)}
    if planning_seconds is not None:
        # No `terminal.max_seconds` here: it is capped at its 1.2s ceiling by the profile, and the
        # 64-node budget binds first, so the prover's stop no longer varies with machine load.
        values.update({"clock.adaptive_enabled": 0.0,
                       "clock.remaining_200_seconds": float(planning_seconds)})
    runtime.pilot_profile = PilotProfile.resolve(
        global_values=values,
        authored_deck_overrides=getattr(module.STRATEGY, "pilot_overrides", {}),
        provenance="strategy-lab")
    return runtime, OwnCardModel(deck)


def _percentile(values, quantile):
    if not values:
        return 0.0
    rows = sorted(values)
    return rows[min(len(rows) - 1, int((len(rows) - 1) * quantile))]


def _summary(rows):
    times = [row["milliseconds"] for row in rows if row.get("error") is None]
    nodes = [row["nodes"] for row in rows if row.get("error") is None]
    unknown = [event for row in rows for event in row.get("unknown_evidence", ())]
    invalidations = {}
    for row in rows:
        reason = row.get("suffix_invalidation")
        if reason not in (None, "empty"):
            invalidations[reason] = invalidations.get(reason, 0) + 1
    return {
        "decisions": len(rows), "errors": sum(row.get("error") is not None for row in rows),
        "error_evidence": [{"episode": row["episode"], "frame": row["frame"],
                            "error": row.get("error")}
                           for row in rows if row.get("error") is not None],
        "recorded_agreement": sum(row.get("recorded") == row.get("chosen") for row in rows),
        "suffix_hits": sum(row.get("suffix_hit", False) for row in rows),
        "unknown_actions": sum(row.get("unknown", 0) for row in rows),
        "unknown_evidence": unknown,
        "median_ms": median(times) if times else 0.0,
        "total_ms": sum(times),
        "p95_ms": _percentile(times, 0.95), "max_ms": max(times, default=0.0),
        "median_nodes": median(nodes) if nodes else 0.0,
        "total_nodes": sum(nodes),
        "decisions_narrowed": sum(row.get("deferred", 0) > 0 for row in rows),
        "total_deferred": sum(row.get("deferred", 0) for row in rows),
        "minimum_clock_scale": min(
            (row.get("clock_scale", 1.0) for row in rows), default=1.0),
        "plans_with_cached_steps": sum(row.get("cached_steps", 0) > 0 for row in rows),
        "cached_steps": sum(row.get("cached_steps", 0) for row in rows),
        "suffix_invalidations": invalidations,
        "suffix_events": [{
            "episode": row["episode"], "frame": row["frame"],
            "cached_steps": row.get("cached_steps", 0),
            "invalidation": row.get("suffix_invalidation"),
        } for row in rows if row.get("cached_steps", 0)
        or row.get("suffix_invalidation") not in (None, "empty")],
    }


def run(replay_dir: Path, *, limit=None, episode=None, frame=None,
        shard_index=0, shard_count=1, include_baseline=True, include_focused=True,
        planning_seconds=None):
    names = tuple(name for name in ("baseline", "shadow", "focused")
                  if (name != "baseline" or include_baseline)
                  and (name != "focused" or include_focused))
    modes = {name: [] for name in names}
    remaining = limit
    replay_paths = sorted(replay_dir.glob("*-replay.json*"))[shard_index::shard_count]
    for replay_path in replay_paths:
        replay = load_replay(replay_path)
        log_paths = tuple(replay_dir.glob(replay_path.name.split("-replay")[0] + "-agent-*-logs.json"))
        if not log_paths:
            continue
        seat = int(log_paths[0].stem.split("-agent-")[1].split("-")[0])
        decisions = [row for row in iter_decisions(replay) if row.seat == seat and row.obs]
        if episode is not None:
            decisions = [row for row in decisions if row.episode_id == episode]
        if frame is not None:
            decisions = [row for row in decisions if row.frame == frame]
        if remaining is not None:
            decisions = decisions[:remaining]
        runtimes = {name: _runtime(
            name == "focused", reuse=name != "baseline", planning_seconds=planning_seconds)
            for name in modes}
        for decision in decisions:
            for name, (runtime, tracker) in runtimes.items():
                observation = copy.deepcopy(decision.obs)
                tracker.observe(observation)
                observation["own_prizes"] = tracker.prize_export()
                observation["known_top"] = tracker.known_top_export()
                started = time.perf_counter()
                try:
                    result = runtime.decide(observation)
                    elapsed = (time.perf_counter() - started) * 1000.0
                    production = result.diagnostics.get("production") or {}
                    suffix = result.diagnostics.get("plan_suffix") or {}
                    beam = result.diagnostics.get("strategy_beam")
                    modes[name].append({
                        "episode": decision.episode_id, "frame": decision.frame,
                        "recorded": decision.chosen, "chosen": list(result.chosen),
                        "chosen_kind": result.action.kind,
                        "chosen_action_key": hashlib.sha256(
                            repr(result.action).encode("utf-8")).hexdigest()[:20],
                        "milliseconds": elapsed,
                        "nodes": sum(production.get("root_branch_nodes") or ()),
                        "deferred": production.get("strategy_later_wave", 0),
                        "clock_scale": production.get("strategy_clock_scale", 1.0),
                        "suffix_hit": result.diagnostics.get("backend") == "plan-suffix",
                        "cached_steps": suffix.get("cached_steps", 0),
                        "suffix_invalidation": suffix.get("invalidation"),
                        "unknown": len(beam.unknown) if beam is not None else 0,
                        "focused_action_keys": ([row.action_key for row in beam.focused]
                                                if beam is not None else []),
                        "safety_action_keys": ([row.action_key for row in beam.safety]
                                               if beam is not None else []),
                        "unknown_evidence": ([{
                            "episode": decision.episode_id, "frame": decision.frame,
                            "action_key": row.action_key, "card_id": row.card_id,
                            "context": row.context, "reason": row.reason,
                        } for row in beam.unknown] if beam is not None else []),
                        "error": None,
                    })
                except Exception as exc:
                    modes[name].append({
                        "episode": decision.episode_id, "frame": decision.frame,
                        "recorded": decision.chosen, "chosen": None, "milliseconds": 0.0,
                        "nodes": 0, "suffix_hit": False, "unknown": 0,
                        "unknown_evidence": [],
                        "error": f"{type(exc).__name__}: {exc}",
                    })
        if remaining is not None:
            remaining -= len(decisions)
            if remaining <= 0:
                break
    paired = zip(modes["shadow"], modes.get("focused", ()))
    changes = [
        {"episode": left["episode"], "frame": left["frame"],
         "recorded": left["recorded"],
         "shadow": left["chosen"], "shadow_kind": left.get("chosen_kind"),
         "shadow_action_key": left.get("chosen_action_key"),
         "focused": right["chosen"], "focused_kind": right.get("chosen_kind"),
         "focused_action_key": right.get("chosen_action_key"),
         "focused_keys": right.get("focused_action_keys"),
         "safety_keys": right.get("safety_action_keys"),
         "deferred": right.get("deferred"), "clock_scale": right.get("clock_scale")}
        for left, right in paired if left.get("chosen") != right.get("chosen")]
    reuse_pairs = [(left, right)
                   for left, right in zip(modes.get("baseline", ()), modes["shadow"])
                   if right.get("suffix_hit")]
    reuse_changes = [
        {"episode": left["episode"], "frame": left["frame"],
         "baseline": left["chosen"], "reused": right["chosen"]}
        for left, right in reuse_pairs
        if left.get("chosen") != right.get("chosen")]
    result = {name: _summary(rows) for name, rows in modes.items()}
    result.update({
        "reuse": {
            "hits": len(reuse_pairs),
            "baseline_ms": sum(left.get("milliseconds", 0.0) for left, _right in reuse_pairs),
            "reused_ms": sum(right.get("milliseconds", 0.0) for _left, right in reuse_pairs),
        },
        "reuse_decision_changes": reuse_changes, "decision_changes": changes,
    })
    return result


def gate_failures(result, *, zero_focus=False, zero_reuse=False,
                  zero_unknown=False, no_errors=False):
    failures = []
    if zero_focus and result.get("decision_changes"):
        failures.append("focused decision changes")
    if zero_reuse and result.get("reuse_decision_changes"):
        failures.append("plan-reuse decision changes")
    if zero_unknown and any(
            summary.get("unknown_actions", 0) for name, summary in result.items()
            if name in {"baseline", "shadow", "focused"}):
        failures.append("unknown actions")
    if no_errors and any(
            summary.get("errors", 0) for name, summary in result.items()
            if name in {"baseline", "shadow", "focused"}):
        failures.append("mirror errors")
    return tuple(failures)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("replay_dir", type=Path)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--episode", type=int)
    parser.add_argument("--frame", type=int)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--skip-baseline", action="store_true")
    parser.add_argument("--skip-focused", action="store_true")
    parser.add_argument("--planning-seconds", type=float)
    parser.add_argument("--require-zero-focus-changes", action="store_true")
    parser.add_argument("--require-zero-reuse-changes", action="store_true")
    parser.add_argument("--require-zero-unknown", action="store_true")
    parser.add_argument("--require-no-errors", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = run(
        args.replay_dir, limit=args.limit, episode=args.episode, frame=args.frame,
        shard_index=args.shard_index, shard_count=args.shard_count,
        include_baseline=not args.skip_baseline, include_focused=not args.skip_focused,
        planning_seconds=args.planning_seconds)
    payload = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    failures = gate_failures(
        result, zero_focus=args.require_zero_focus_changes,
        zero_reuse=args.require_zero_reuse_changes,
        zero_unknown=args.require_zero_unknown, no_errors=args.require_no_errors)
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
