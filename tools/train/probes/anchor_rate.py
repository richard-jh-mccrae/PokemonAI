"""Measure the deck-tracker ANCHOR rate across real self-play matches (Issue #175 follow-up).

Drives the native engine directly (`cg.game`) with the real agent policy in BOTH seats, and records
whether the prizes were anchored at each own-seat decision frame. Reports the UN-anchored share by
turn — the only frames Issue #175's probability weighting can change anything on — plus DE-ANCHOR events.

Usage: python anchor_rate.py <agent> [-n GAMES]
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "tools"))

from common.deck_tracker import OwnCardModel  # noqa: E402

PRIZE, HAND = 6, 2
_MAX_STEPS = 4000


def deck_ids(agent_dir: Path) -> list:
    """The agent's 60-card decklist: `deck.csv` is bare card ids, one per line (CRLF)."""
    out = []
    for line in (agent_dir / "deck.csv").read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(int(line))
            except ValueError:
                pass
    return out


def load_agent(agent_dir: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, agent_dir / "main.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.agent


def run_game(agent_dir: Path, deck: list, stats: dict) -> None:
    """Play one mirror match, feeding every own-seat obs to a fresh OwnCardModel."""
    import os
    from cg.game import battle_finish, battle_start, battle_select

    cwd = os.getcwd()
    os.chdir(agent_dir)                      # agent resolves deck.csv relative to cwd, as on grader
    sys.path.insert(0, str(agent_dir))
    try:
        seats = [load_agent(agent_dir, f"_seat{i}") for i in range(2)]
        obs, start = battle_start(deck, list(deck))
        if start.errorPlayer >= 0:
            battle_finish()
            return
        models = {0: OwnCardModel(deck), 1: OwnCardModel(deck)}
        baseline = {0: OwnCardModel(deck), 1: OwnCardModel(deck)}   # logs-stripped control
        prev_anchored = {0: False, 1: False}
        prize_take_since = {0: False, 1: False}
        watch = 0                            # measure seat 0 only (one sample per game)
        try:
            for _ in range(_MAX_STEPS):
                cur = obs.get("current") or {}
                res = cur.get("result")
                if res is not None and res != -1:
                    break
                if obs.get("select") is None:
                    break
                seat = cur.get("yourIndex", 0)
                turn = cur.get("turn")
                for e in (obs.get("logs") or []):
                    if (e.get("fromArea") == PRIZE and e.get("toArea") == HAND
                            and e.get("playerIndex") == seat):
                        prize_take_since[seat] = True
                if seat == watch:
                    try:
                        models[seat].observe(obs)
                        anchored = models[seat].prize_export() is not None
                    except Exception:
                        anchored = prev_anchored[seat]
                    # PAIRED control: the pre-#175 tracker is behaviourally identical to the fixed
                    # one fed an obs with `logs` stripped, so the same frames grade both arms.
                    try:
                        baseline[seat].observe({**obs, "logs": []})
                        if baseline[seat].prize_export() is None:
                            stats["base_unanchored"] += 1
                    except Exception:
                        pass
                    stats["frames"] += 1
                    stats["by_turn"][turn] += 1
                    if anchored:
                        stats["anchored"] += 1
                        if stats["first_anchor_turn"] is None:
                            stats["first_anchor_turn"] = turn
                    else:
                        stats["unanchored"] += 1
                        stats["by_turn_un"][turn] += 1
                    if prev_anchored[seat] and not anchored:
                        stats["deanchors"] += 1
                        if prize_take_since[seat]:
                            stats["deanchor_after_prize"] += 1
                        stats["deanchor_turns"].append(turn)
                        prize_take_since[seat] = False
                    prev_anchored[seat] = anchored
                choice = seats[seat](obs)
                if choice is None:
                    break
                try:
                    obs = battle_select(choice)
                except Exception:
                    break
        finally:
            battle_finish()
    finally:
        os.chdir(cwd)
        if str(agent_dir) in sys.path:
            sys.path.remove(str(agent_dir))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("agent")
    ap.add_argument("-n", "--games", type=int, default=6)
    args = ap.parse_args()

    agent_dir = REPO / "src" / "agents" / args.agent
    deck = deck_ids(agent_dir)
    print(f"agent={args.agent}  decklist={len(deck)} cards  games={args.games}", flush=True)

    stats = {"frames": 0, "anchored": 0, "unanchored": 0, "deanchors": 0,
             "base_unanchored": 0,
             "deanchor_after_prize": 0, "by_turn": Counter(), "by_turn_un": Counter(),
             "first_anchor_turn": None, "deanchor_turns": [], "first_anchor_turns": []}
    for g in range(args.games):
        stats["first_anchor_turn"] = None
        before = stats["frames"]
        try:
            run_game(agent_dir, deck, stats)
        except Exception as exc:                          # noqa: BLE001
            print(f"  game {g}: FAILED ({type(exc).__name__}: {exc})", flush=True)
            continue
        if stats["first_anchor_turn"] is not None:
            stats["first_anchor_turns"].append(stats["first_anchor_turn"])
        print(f"  game {g}: {stats['frames']-before} own-seat frames, "
              f"first anchor turn {stats['first_anchor_turn']}", flush=True)

    f = stats["frames"] or 1
    print("\n=== ANCHOR RATE (own seat) ===")
    print(f"decision frames         : {stats['frames']}")
    print(f"UN-anchored             : {stats['unanchored']}  ({100*stats['unanchored']/f:.1f}%)")
    print(f"anchored                : {stats['anchored']}  ({100*stats['anchored']/f:.1f}%)")
    b = stats["base_unanchored"]
    print(f"UN-anchored, PRE-FIX    : {b}  ({100*b/f:.1f}%)   [same frames, logs stripped]")
    print(f"frames RECOVERED by fix : {b - stats['unanchored']}  ({100*(b-stats['unanchored'])/f:.1f} pp)")
    print(f"de-anchor events        : {stats['deanchors']}")
    print(f"  ...after our prize take: {stats['deanchor_after_prize']}")
    if stats["deanchor_turns"]:
        print(f"  de-anchor turns       : {sorted(t for t in stats['deanchor_turns'] if t is not None)}")
    fa = sorted(t for t in stats["first_anchor_turns"] if t is not None)
    if fa:
        print(f"first anchor turn       : median {fa[len(fa)//2]}, range {fa[0]}-{fa[-1]}"
              f"  (anchored in {len(fa)}/{args.games} games)")
    print("\nun-anchored share by turn:")
    for t in sorted(stats["by_turn"], key=lambda x: (x is None, x)):
        n, u = stats["by_turn"][t], stats["by_turn_un"].get(t, 0)
        print(f"  turn {str(t):>4}: {u:>4}/{n:<4} un-anchored ({100*u/n:5.1f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
