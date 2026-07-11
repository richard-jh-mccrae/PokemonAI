"""Retest ONE correction through the real (shipped) Pilot — the blunder-buster leaf's probe.

    python tools/train/retest_one.py <agent> <episode>-<frame>

Builds the agent's real Pilot exactly like tune._build_pilot (mirrors main.py, all kill-switches at
shipped defaults), loads the Correction from the per-build store, and prints:
  - the live `before` chosen vs the re-derived `after` chosen, `correct`, and `fixed`
  - lethal/planned layer verdicts before & after (non-null => that layer drove the pick)
  - every option with its after-score / tac / tier / fired rules, so you can see WHICH rule fired

Local + instant. This is a decision probe only — it does not re-drive Spans (use tune.py for that).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from train.blunder.store import load_corrections  # noqa: E402
from train.tuner.retest import retest  # noqa: E402
import importlib


def _build_pilot(agent: str):
    tune = importlib.import_module("train.tune")
    return tune._build_pilot(agent)


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("agent")
    ap.add_argument("key", help="<episode>-<frame>")
    ap.add_argument("--store", default=str(REPO / "data" / "corrections"))
    args = ap.parse_args(argv)

    ep_s, fr_s = args.key.split("-")
    ep, fr = int(ep_s), int(fr_s)

    corrs = [c for c in load_corrections(args.store)
             if c.agent == args.agent and c.episode_id == ep
             and (c.decision or {}).get("frame") == fr]
    if not corrs:
        print(f"NO correction found for {args.agent} {args.key}")
        return 1
    c = corrs[-1]
    pilot, seeds = _build_pilot(args.agent)
    r = retest(c, pilot)

    print(f"=== {args.agent} {args.key}  (category={c.category}, scope={c.scope}) ===")
    dec = c.decision or {}
    print(f"select_context={dec.get('select_context')} turn={dec.get('turn')}")
    print(f"rationale: {c.rationale}")
    print(f"chosen(before live) = {r['chosen_before']}  ({c.chosen_label})")
    print(f"chosen(after now)   = {r['chosen_after']}")
    print(f"correct             = {r['correct']}  ({c.correct_label})")
    print(f"FIXED = {r['fixed']}")
    print(f"lethal before={r['lethal_before']}  after={r['lethal_after']}")
    print(f"planned before={r['planned_before']}  after={r['planned_after']}")
    print(f"margin before={r['margin_before']}  after={r['margin_after']}")
    after = r.get("after") or {}
    opts = after.get("opts") or []
    print(f"\n--- after opts ({len(opts)}) [idx: label | score tac tier | fired] ---")
    labels = [o.get("label") for o in (dec.get("options") or [])]
    for i, o in enumerate(opts):
        lbl = o.get("label") or (labels[i] if i < len(labels) else "?")
        fired = o.get("fired")
        print(f"[{i}] {lbl} | score={o.get('score')} tac={o.get('tac')} tier={o.get('tier')} | {fired}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
