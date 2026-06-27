"""Run a slice of a Battle's Matches in an isolated process; print one JSON result per line.

Spawned by `battle.run_battle` for parallelism. Each worker owns its own native engine
instance and a *persistent* pair of agent servers (so the heavy agent import is paid once,
not per Match), and the engine's per-process global state stays private to this worker.

    python _battle_worker.py <dirA> <dirB> <count> [extra_syspath ...]
"""
import json
import sys
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parents[1]),          # tools/ -> import sim.battle
                str(Path(__file__).resolve().parents[2] / "src")]  # src/  -> cg for the driver

from sim.battle import AgentServer, play_match, read_deck  # noqa: E402


def main() -> None:
    dir_a, dir_b, count, *extra = sys.argv[1:]
    count = int(count)
    deck_a, deck_b = read_deck(Path(dir_a)), read_deck(Path(dir_b))
    a, b = AgentServer(dir_a, extra), AgentServer(dir_b, extra)
    try:
        for _ in range(count):
            r = play_match(a, b, deck_a, deck_b)
            print(json.dumps({"winner": r.winner, "crashed": list(r.crashed)}), flush=True)
            if not a.alive():                      # respawn a server a crash killed, for the next Match
                a = AgentServer(dir_a, extra)
            if not b.alive():
                b = AgentServer(dir_b, extra)
    finally:
        a.close()
        b.close()


if __name__ == "__main__":
    main()
