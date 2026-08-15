"""Battle agent server: load one Bundle's agent, answer observations over stdin/stdout.

Spawned by tools/sim/battle.py with **cwd = the Bundle dir**, so the agent's `deck.csv` and
sibling imports (`strategy`, `common`, `cg`) resolve exactly as on the grader — and each
contestant gets its *own* process, so two different Bundles never collide in `sys.modules`.

Protocol: one JSON observation per line in (stdin) → one JSON response per line out.
Normal Battles return the chosen-index list. Strategy Bench returns that list plus captured
decision telemetry. Agent stdout is redirected to stderr so it cannot corrupt the channel.
"""
import importlib.util
import json
import os
import sys
from contextlib import nullcontext
from pathlib import Path


def _load_agent(bundle: Path):
    spec = importlib.util.spec_from_file_location("_battle_agent_main", bundle / "main.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.agent


def main() -> None:
    capture = os.environ.get("AGENT_CAPTURE_TELEMETRY") == "1"
    os.environ["AGENT_NO_TELEMETRY"] = "0" if capture else "1"
    for root in sys.argv[1:]:                              # extra sys.path roots (e.g. src for source agent)
        sys.path.insert(0, root)
    bundle = Path.cwd()
    sys.path.insert(0, str(bundle))
    if os.environ.get("CG_ENGINE") == "py":            # ADR-0050 M3: the agent's `cg`
        from cgpy.alias import install                 # imports resolve to the cgpy twin
        install()

    # Hand real stdout to the protocol; send any agent prints to stderr instead.
    proto = os.fdopen(os.dup(1), "w", encoding="utf-8")
    os.dup2(2, 1)

    agent = _load_agent(bundle)                            # builds the runtime once
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        if capture:
            from common.telemetry import capture_records
            context = capture_records()
        else:
            context = nullcontext([])
        with context as records:
            choice = agent(json.loads(line))
        payload = ({"choice": [int(i) for i in choice], "telemetry": records}
                   if capture else [int(i) for i in choice])
        proto.write(json.dumps(payload) + "\n")
        proto.flush()


if __name__ == "__main__":
    main()
