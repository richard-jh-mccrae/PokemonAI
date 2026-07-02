"""Run a slice of a Battle's Matches in an isolated process; print one JSON result per line.

Spawned by `battle.run_battle` for parallelism. Each worker owns its own native engine
instance and a *persistent* pair of agent servers (so the heavy agent import is paid once,
not per Match), and the engine's per-process global state stays private to this worker.

    python _battle_worker.py <dirA> <dirB> <seats> <overlayA|-> <overlayB|-> [extra_syspath ...]

`seats` is a comma-joined list of A's engine seat per Match (e.g. "0,0,1"), assigned globally by
`run_battle` so the whole run stays seat-balanced even when a worker's share is odd.
"""
import json
import sys
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parents[1]),          # tools/ -> import sim.battle
                str(Path(__file__).resolve().parents[2] / "src")]  # src/  -> cg for driver

from sim.battle import AgentServer, _play_seated, read_deck  # noqa: E402


def main() -> None:
    dir_a, dir_b, seats_arg, overlay_a, overlay_b, *extra = sys.argv[1:]
    seats = [int(s) for s in seats_arg.split(",") if s != ""]   # A's engine seat per Match (global plan)
    overlay_a = None if overlay_a == "-" else overlay_a         # "-" sentinel = no overlay this side
    overlay_b = None if overlay_b == "-" else overlay_b
    deck_a, deck_b = read_deck(Path(dir_a)), read_deck(Path(dir_b))
    a, b = AgentServer(dir_a, extra, overlay=overlay_a), AgentServer(dir_b, extra, overlay=overlay_b)
    try:
        for a_seat in seats:                       # seats this worker was assigned (ADR-0021)
            r = _play_seated(a, b, deck_a, deck_b, a_seat)
            print(json.dumps({"a_seat": r.a_seat, "winner": r.winner, "crashed": list(r.crashed)}),
                  flush=True)
            if not a.alive():                      # respawn a server a crash killed, for next Match
                a = AgentServer(dir_a, extra, overlay=overlay_a)
            if not b.alive():
                b = AgentServer(dir_b, extra, overlay=overlay_b)
    finally:
        a.close()
        b.close()


if __name__ == "__main__":
    main()
