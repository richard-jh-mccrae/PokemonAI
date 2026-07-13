"""Capture native-engine matches as parity traces (ADR-0050, needs the DLL).

Plays N matches on the native engine under a seeded chaos policy (uniform legal choices with a
bias toward engaging optional effects) and writes each as a `parity-trace/1` file: per select the
mover's verbatim observation, the choice, and the aligned god-view frame.

    python tools/parity/capture_match.py --decks mega_starmie mega_starmie -n 2 \
        --out tests/fixtures/parity --prefix ms_mirror

The god frames come from `visualize_data()` at match end; visualize's `selected` rides one frame
behind (+1 offset, `tools/sim/record.py` convention), which capture realigns and asserts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from cgpy.verify.trace import Trace, strip_obs  # noqa: E402

_MAX_STEPS = 5000


def chaos_choice(sel: dict, rng: random.Random) -> list[int]:
    """A seeded legal choice biased to exercise effects: prefer non-END on MAIN sometimes,
    prefer YES on yes/no, spread multi-select counts."""
    opts = sel["option"]
    if not opts:
        return []
    lo, hi = sel["minCount"], sel["maxCount"]
    if sel["type"] == 9 and len(opts) == 2:            # YesNo: lean YES to engage effects
        return [0 if rng.random() < 0.7 else 1]
    k = rng.randint(lo, hi) if hi >= lo else lo
    if k == 0 and hi >= 1 and rng.random() < 0.5:      # optional picks: engage half the time
        k = 1
    if sel["context"] == 0:                            # MAIN: de-emphasize instant END
        plays = [i for i, o in enumerate(opts) if o.get("type") == 7]
        if plays and rng.random() < 0.5:               # bench eagerly: exercises promotion
            return [rng.choice(plays)]
        retreats = [i for i, o in enumerate(opts) if o.get("type") == 12]
        if retreats and rng.random() < 0.15:           # occasional retreat
            return retreats[:1]
        non_end = [i for i, o in enumerate(opts) if o.get("type") != 14]
        if non_end and rng.random() < 0.8:
            return [rng.choice(non_end)]
    return rng.sample(range(len(opts)), min(k, len(opts))) if k else []


def deck_ids(name_or_path: str) -> list[int]:
    p = Path(name_or_path)
    if not p.exists():
        p = REPO / "src" / "agents" / name_or_path / "deck.csv"
    return [int(x) for x in p.read_text(encoding="utf-8").split()[:60]]


def capture_one(deck0: list[int], deck1: list[int], seed: int, *, policy: str) -> Trace:
    from cg.game import battle_finish, battle_select, battle_start, visualize_data

    rng = random.Random(seed)
    frames: list[dict] = []
    obs, start = battle_start(list(deck0), list(deck1))
    if start.errorPlayer >= 0:
        raise ValueError(f"illegal deck for seat {start.errorPlayer} (errorType {start.errorType})")
    try:
        winner = -1
        for _ in range(_MAX_STEPS):
            cur = obs.get("current") or {}
            res = cur.get("result", -1)
            if res is not None and res != -1:
                frames.append({"obs": strip_obs(obs), "choice": None, "god": None})
                winner = res
                break
            sel = obs.get("select")
            if sel is None:
                frames.append({"obs": strip_obs(obs), "choice": None, "god": None})
                break
            choice = chaos_choice(sel, rng)
            frames.append({"obs": strip_obs(obs), "choice": [int(i) for i in choice], "god": None})
            obs = battle_select([int(i) for i in choice])
        viz = json.loads(visualize_data())
    finally:
        battle_finish()

    # Align god frames: viz frame k's `selected` answers viz frame k-1's select; our frames
    # store the answer on the SAME index. Assert the alignment before adopting.
    n = min(len(frames), len(viz))
    for k in range(n):
        frames[k]["god"] = viz[k]["current"]
        sel_next = viz[k + 1].get("selected") if k + 1 < len(viz) else None
        if frames[k]["choice"] is not None and sel_next is not None:
            assert frames[k]["choice"] == sel_next, (
                f"visualize selected misalignment at frame {k}: "
                f"{frames[k]['choice']} vs {sel_next}")
        frames[k]["god_logs"] = viz[k].get("logs") or []

    meta = {
        "engine_sha": hashlib.sha256((REPO / "src" / "cg" / "libcg.so").read_bytes()).hexdigest()[:16],
        "decks": [list(deck0), list(deck1)],
        "policy": policy,
        "result": {"winner": winner, "steps": len(frames)},
    }
    return Trace(meta=meta, frames=frames)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Capture native matches as parity traces.")
    ap.add_argument("--decks", nargs=2, default=["mega_starmie", "mega_starmie"],
                    help="two agent names or deck.csv paths")
    ap.add_argument("-n", "--games", type=int, default=1)
    ap.add_argument("--seed", type=int, default=1000, help="base seed (game i uses seed+i)")
    ap.add_argument("--out", default=str(REPO / "data" / "parity"), help="output dir")
    ap.add_argument("--prefix", default="match")
    args = ap.parse_args(argv)

    d0, d1 = deck_ids(args.decks[0]), deck_ids(args.decks[1])
    out = Path(args.out)
    for i in range(args.games):
        seed = args.seed + i
        tr = capture_one(d0, d1, seed, policy=f"chaos:seed={seed}")
        path = out / f"{args.prefix}_{seed}.trace.json.gz"
        tr.save(path)
        r = tr.meta["result"]
        print(f"wrote {path}  frames={r['steps']} winner={r['winner']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
