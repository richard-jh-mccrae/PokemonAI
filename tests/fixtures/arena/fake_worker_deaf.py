"""A worker that stops responding after its first obs — forfeit lines are ignored.

Exercises the manager's force-kill path: a worker that never honors the forfeit
must not hold its Table slot forever. Speaks the two-phase protocol.
"""
import json
import sys

sys.stdin.readline()                     # warm config
sys.stdout.write(json.dumps({"kind": "ready"}) + "\n")
sys.stdout.flush()
sys.stdin.readline()                     # start
sys.stdout.write(json.dumps({"kind": "obs", "obs": {
    "select": {"option": [{"type": 14}], "minCount": 1, "maxCount": 1},
    "current": None, "logs": []}}) + "\n")
sys.stdout.flush()
for _ in sys.stdin:                      # swallow everything, answer nothing
    pass
