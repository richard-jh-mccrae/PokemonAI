"""Battle agent server: load one Bundle's agent, answer observations over stdin/stdout.

Spawned by tools/sim/battle.py with **cwd = the Bundle dir**, so the agent's `deck.csv` and
sibling imports (`strategy`, `common`, `cg`) resolve exactly as on the grader — and each
contestant gets its *own* process, so two different Bundles never collide in `sys.modules`.

Protocol: one JSON observation per line in (stdin) → one JSON list of chosen indices per
line out. The agent's own stdout (stray prints, telemetry) is redirected to stderr so it
never corrupts the protocol channel. Telemetry is silenced for speed (curiosity mode).
"""
import importlib.util
import json
import os
import sys
from pathlib import Path


def _load_agent(bundle: Path):
    spec = importlib.util.spec_from_file_location("_battle_agent_main", bundle / "main.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.agent


def main() -> None:
    os.environ["AGENT_NO_TELEMETRY"] = "1"                 # protocol channel must stay clean
    for root in sys.argv[1:]:                              # extra sys.path roots (e.g. src for source agent)
        sys.path.insert(0, root)
    bundle = Path.cwd()
    sys.path.insert(0, str(bundle))

    # Hand real stdout to the protocol; send any agent prints to stderr instead.
    proto = os.fdopen(os.dup(1), "w", encoding="utf-8")
    os.dup2(2, 1)

    agent = _load_agent(bundle)                            # builds the Pilot once (the pregame window)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        choice = agent(json.loads(line))
        proto.write(json.dumps([int(i) for i in choice]) + "\n")
        proto.flush()


if __name__ == "__main__":
    main()
