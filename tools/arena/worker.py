"""One PvC Match in one subprocess (ADR-0058).

Drives the cabt env with the real agent on one seat and the *human bridge* on the
other: each human decision goes out as an `obs` line on stdout and blocks until the
parent writes a `choice` (or `forfeit`) line on stdin. On any end — played out,
concede, timeout — the replay is tagged and saved before the `end` line is emitted.

Protocol (line-delimited JSON), two-phase so the manager can pre-warm workers:
  stdin   warm:  {agent_dir, agent_name, replay_dir}          # boot env + agent
  stdout  {"kind": "ready"}                                   # slow part done
  stdin   start: {"kind": "start", human_deck, visitor, human_seat}
  stdout  {"kind": "obs", "obs": <raw seat observation>}      # human must act
  stdin   {"kind": "choice", "indices": [..]}                 # the human's pick
        | {"kind": "forfeit", "reason": "concede"|"timeout"}
  stdout  {"kind": "end", "replay_path": .., "statuses": .., "rewards": ..}

stdout is the protocol channel: fd 1 is duplicated for it and then pointed at
stderr, so stray agent/env prints can never corrupt the stream (same trick as
tools/sim/_agent_server.py). Timeouts are overridden at env.make — the cabt
defaults (runTimeout 2000s) would forfeit a slow human mid-game.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]

_A_WEEK = 7 * 24 * 3600     # "no clock" for humans, expressed in env units (seconds)


class _Forfeit(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class HumanBridge:
    """The Visitor's seat: an env agent callable backed by the stdio protocol."""

    def __init__(self, deck: list[int], proto_in, proto_out):
        self._deck = [int(c) for c in deck]
        self._deck_sent = False
        self._in = proto_in
        self._out = proto_out
        self.forfeit: str | None = None

    def __call__(self, obs, _config=None) -> list[int]:
        # (obs, configuration) — the env passes both to class-instance callables
        if obs.get("select") is None:               # the initial deck submission
            if self._deck_sent:
                return []
            self._deck_sent = True
            return self._deck
        self._send({"kind": "obs", "obs": obs})
        line = self._in.readline()
        if not line:                                # parent went away
            self.forfeit = "timeout"
            raise _Forfeit("timeout")
        msg = json.loads(line)
        if msg.get("kind") == "forfeit":
            self.forfeit = msg.get("reason") or "concede"
            raise _Forfeit(self.forfeit)
        return [int(i) for i in msg.get("indices", ())]

    def _send(self, msg: dict) -> None:
        self._out.write(json.dumps(msg) + "\n")
        self._out.flush()


def _load_agent(agent_dir: Path):
    spec = importlib.util.spec_from_file_location("_arena_agent_main",
                                                  agent_dir / "main.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.agent


def main() -> None:
    proto_out = os.fdopen(os.dup(1), "w", encoding="utf-8")
    os.dup2(2, 1)                                   # stray prints -> stderr

    # Phase 1 — warm: everything slow happens here, BEFORE a deck exists, so the
    # manager can boot a worker ahead of the visitor's click (the pre-warm pool).
    warm = json.loads(sys.stdin.readline())
    agent_dir = Path(warm["agent_dir"]).resolve()
    replay_dir = Path(warm["replay_dir"]).resolve()

    os.environ["AGENT_NO_TELEMETRY"] = "1"          # keep the agent's stdout quiet
    for p in (agent_dir, _REPO / "src", _REPO / "tools"):
        sys.path.insert(0, str(p))
    os.chdir(agent_dir)                             # agent reads deck.csv/tuned.json by cwd

    from sim.check_agent import _import_make        # the quiet kaggle_environments import
    from arena import replay_store

    make = _import_make()
    env = make("cabt", configuration={"actTimeout": _A_WEEK, "runTimeout": _A_WEEK})
    agent = _load_agent(agent_dir)

    proto_out.write(json.dumps({"kind": "ready"}) + "\n")
    proto_out.flush()

    # Phase 2 — start: the per-match bits arrive when a visitor claims this worker.
    line = sys.stdin.readline()
    if not line:                                    # never claimed (shutdown)
        return
    start = json.loads(line)
    if start.get("kind") != "start":
        return
    human_seat = int(start.get("human_seat", 0))

    bridge = HumanBridge(start["human_deck"], sys.stdin, proto_out)
    seats: list = [None, None]
    seats[human_seat] = bridge
    seats[1 - human_seat] = agent

    env.run(seats)                                  # agent exceptions end the episode inside

    replay = env.toJSON()
    path = replay_store.save_replay(
        replay, replay_dir, agent=warm["agent_name"], visitor=start.get("visitor"),
        human_seat=human_seat, forfeit=bridge.forfeit)
    proto_out.write(json.dumps({
        "kind": "end", "replay_path": str(path),
        "statuses": replay.get("statuses"), "rewards": replay.get("rewards"),
    }) + "\n")
    proto_out.flush()


if __name__ == "__main__":
    main()
