"""Commensurability probe (Issue #175, ADR-0074 decision 5) — is the TUNED score on the same scale as the
planner's `_leaf_value`, in the POSITIONAL band below one prize?

The dominance floor decision 5 rules replaces `_commit_best`'s constant `best_val < KO_SCORE` with a
comparison against what the planner would otherwise defer to (the tuned/greedy pick). That is only
sound if the two numbers are comparable *below* KO_SCORE — they share the KO_SCORE unit (the pool's
own gate already compares `t.tactical >= KO_SCORE`), but the positional bands were never proven
commensurate, and a p-weighted line lives exactly there.

Wraps `_ko_for_prizes_lines`, which already receives the tuned `traces`, so both numbers are read
from the same frame with no re-derivation. Reports their joint distribution.

Usage: python rung_scale.py <agent> [-n GAMES]
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "tools" / "train" / "probes"))

from anchor_rate import deck_ids, load_agent  # noqa: E402
from common.strategy.context import KO_SCORE  # noqa: E402
from common.strategy.planner import PlannerMixin  # noqa: E402

SAMPLES: list = []


def _instrument():
    """Record (tuned top score, tuned top TACTICAL, pool best value, #lines) per firing frame."""
    original = PlannerMixin._ko_for_prizes_lines

    def wrapped(self, obs, select, board, options, traces):
        lines = original(self, obs, select, board, options, traces)
        if lines:
            scores = [getattr(t, "score", 0.0) or 0.0 for t in (traces or ())]
            tacs = [getattr(t, "tactical", 0.0) or 0.0 for t in (traces or ())]
            SAMPLES.append({
                "tuned_top": max(scores) if scores else 0.0,
                "tuned_tac": max(tacs) if tacs else 0.0,
                "pool_best": max(ln.value for ln in lines),
                "pool_n": len(lines),
            })
        return lines

    PlannerMixin._ko_for_prizes_lines = wrapped


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("agent")
    ap.add_argument("-n", "--games", type=int, default=6)
    args = ap.parse_args()

    agent_dir = (REPO / "src" / "agents" / args.agent).resolve()
    deck = deck_ids(agent_dir)
    _instrument()
    cwd = os.getcwd()
    os.chdir(agent_dir)
    sys.path.insert(0, str(agent_dir))
    from cg.game import battle_finish, battle_select, battle_start  # noqa: E402

    for g in range(args.games):
        seats = [load_agent(agent_dir, f"_s{g}_{i}") for i in range(2)]
        obs, start = battle_start(deck, list(deck))
        if start.errorPlayer >= 0:
            battle_finish()
            continue
        try:
            for _ in range(4000):
                cur = obs.get("current") or {}
                if cur.get("result") not in (None, -1) or obs.get("select") is None:
                    break
                obs = battle_select(seats[cur.get("yourIndex", 0)](obs))
        except Exception:                                  # noqa: BLE001
            pass
        finally:
            battle_finish()
    os.chdir(cwd)

    n = len(SAMPLES)
    out = [f"\n=== RUNG SCALE ({args.agent}, {args.games} games) ===",
           f"frames where the ko_for_prizes pool fired: {n}"]
    if not n:
        out.append("no firings — nothing to compare")
        sys.stdout.write("\n".join(out) + "\n")
        return 0

    below = [s for s in SAMPLES if s["pool_best"] < KO_SCORE]
    out.append(f"KO_SCORE = {KO_SCORE}")
    out.append(f"pool best BELOW one prize (the band the floor lives in): {len(below)}/{n}")
    buckets: Counter = Counter()
    for s in SAMPLES:
        ratio = s["pool_best"] / KO_SCORE
        buckets[f"{int(ratio)}x prize" if ratio >= 1 else "sub-prize"] += 1
    out.append("pool_best magnitude: " + ", ".join(f"{k}={v}" for k, v in buckets.most_common()))
    tt = sorted(s["tuned_top"] for s in SAMPLES)
    pb = sorted(s["pool_best"] for s in SAMPLES)
    out.append(f"tuned_top : min {tt[0]:.1f} | median {tt[n//2]:.1f} | max {tt[-1]:.1f}")
    out.append(f"pool_best : min {pb[0]:.1f} | median {pb[n//2]:.1f} | max {pb[-1]:.1f}")
    dominated = sum(1 for s in SAMPLES if s["pool_best"] <= s["tuned_top"])
    out.append(f"frames where pool_best <= tuned_top (dominance floor WOULD veto): "
               f"{dominated}/{n} ({100*dominated/n:.1f}%)")
    vetoed_now = sum(1 for s in SAMPLES if s["pool_best"] < KO_SCORE)
    out.append(f"frames the CURRENT constant floor vetoes (pool_best < KO_SCORE): "
               f"{vetoed_now}/{n} ({100*vetoed_now/n:.1f}%)")
    tuned_ko = sum(1 for s in SAMPLES if s["tuned_tac"] >= KO_SCORE)
    out.append(f"frames whose tuned tactical is already KO-class: {tuned_ko}/{n} "
               f"(pool is layer-on-top, so this should be 0)")
    sys.stdout.write("\n".join(out) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
