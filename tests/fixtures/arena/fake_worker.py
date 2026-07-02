"""A stand-in for tools/arena/worker.py speaking the exact stdio protocol.

Two-phase like the real worker (warm -> ready -> start), then two human
decisions end the match; a forfeit line ends it immediately. Writes a minimal
replay file so the manager's replay_path handling is real.
"""
import json
import sys
from pathlib import Path

warm = json.loads(sys.stdin.readline())
replay_dir = Path(warm["replay_dir"])
replay_dir.mkdir(parents=True, exist_ok=True)


def emit(msg):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


emit({"kind": "ready"})
start = json.loads(sys.stdin.readline() or "{}")
if start.get("kind") != "start":
    raise SystemExit(0)


def save(forfeit):
    path = replay_dir / (f"fake_{warm['agent_name']}_"
                         f"{start.get('visitor') or 'anon'}.json")
    path.write_text(json.dumps({"info": {"pvc": {"forfeit": forfeit}}}),
                    encoding="utf-8")
    return str(path)


def obs():
    return {"select": {"option": [{"type": 14}], "minCount": 1, "maxCount": 1},
            "current": None, "logs": []}


emit({"kind": "obs", "obs": obs()})
rounds = 0
for line in sys.stdin:
    msg = json.loads(line)
    if msg["kind"] == "forfeit":
        emit({"kind": "end", "replay_path": save(msg.get("reason")),
              "statuses": ["ERROR", "DONE"], "rewards": [None, 0]})
        break
    rounds += 1
    if rounds >= 2:
        emit({"kind": "end", "replay_path": save(None),
              "statuses": ["DONE", "DONE"], "rewards": [1, -1]})
        break
    emit({"kind": "obs", "obs": obs()})
