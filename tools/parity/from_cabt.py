"""Convert kaggle/arena/selfplay cabt replays (`env.toJSON()`) into parity traces (M4).

A cabt replay carries per-step agent observations and the kaggle +1 action offset (an
agent's action at step k+1 answers ITS observation at step k; step-1 actions are the deck
submissions). The converted trace has NO god frames — replaying it exercises the
replayer's pure reveal-oracle path: draws/coins bind from the mover's own log windows,
prize identities bind AT TAKE TIME (the owner's PRIZE→HAND move carries the serial), and
deck order adopts from revealed select listings (multiset-checked).

    python tools/parity/from_cabt.py episode.json --out data/parity/cabt
    python tools/parity/from_cabt.py tests/fixtures/match-replay.json --replay
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from cgpy.verify.trace import Trace, strip_obs  # noqa: E402


def convert(replay: dict) -> Trace:
    """cabt `env.toJSON()` dict → a parity-trace/1 Trace (god-free)."""
    steps = replay["steps"]
    if len(steps) < 2:
        raise ValueError("replay has no played steps")
    decks = [list(map(int, steps[1][i]["action"] or [])) for i in (0, 1)]
    if not all(len(d) == 60 for d in decks):
        raise ValueError("step-1 actions are not two 60-card deck submissions")

    frames: list[dict] = []
    # From step 1 on: the ACTIVE agent's observation is the posed select; its answer is
    # that agent's action at the NEXT step (kaggle +1 offset).
    for k in range(1, len(steps)):
        movers = [i for i in (0, 1) if steps[k][i].get("status") == "ACTIVE"]
        if not movers:                              # terminal step: both DONE
            break
        i = movers[0]
        obs = steps[k][i].get("observation") or {}
        choice = None
        if k + 1 < len(steps):
            act = steps[k + 1][i].get("action")
            choice = [int(x) for x in act] if act is not None else None
        frames.append({"obs": strip_obs(obs), "choice": choice, "god": None})
    # Terminal frame: the last step's view of either agent (result is set for both).
    last = steps[-1]
    term = next((last[i].get("observation") for i in (0, 1)
                 if (last[i].get("observation") or {}).get("current")), None)
    if term is not None and (term.get("current") or {}).get("result", -1) != -1:
        frames.append({"obs": strip_obs(term), "choice": None, "god": None})

    winner = -1
    for fr in reversed(frames):
        r = (fr["obs"].get("current") or {}).get("result", -1)
        if r is not None and r != -1:
            winner = r
            break
    meta = {"engine_sha": "cabt", "decks": decks,
            "policy": f"cabt:{replay.get('id', '?')}",
            "purpose": "converted cabt episode (god-free, reveal-oracle replay)",
            "result": {"winner": winner, "steps": len(frames)}}
    return Trace(meta=meta, frames=frames)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="cabt replay → parity trace (M4).")
    ap.add_argument("replay", type=Path, help="env.toJSON() episode file")
    ap.add_argument("--out", type=Path, default=REPO / "data" / "parity" / "cabt")
    ap.add_argument("--replay", dest="run_replay", action="store_true",
                    help="replay the converted trace through cgpy immediately")
    args = ap.parse_args(argv)

    replay = json.loads(args.replay.read_text(encoding="utf-8"))
    tr = convert(replay)
    name = f"cabt_{replay.get('id', args.replay.stem)[:13]}.trace.json.gz"
    path = tr.save(args.out / name)
    print(f"wrote {path}  frames={tr.meta['result']['steps']} "
          f"winner={tr.meta['result']['winner']}")
    if args.run_replay:
        from cgpy.verify.replayer import replay as run
        rep = run(tr)
        print(str(rep))
        return 0 if rep.clean else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
