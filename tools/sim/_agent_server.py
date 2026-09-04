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
    emit_enabled = os.environ.get("AGENT_NO_TELEMETRY") != "1"
    for root in sys.argv[1:]:                              # extra sys.path roots (e.g. src for source agent)
        sys.path.insert(0, root)
    bundle = Path.cwd()
    sys.path.insert(0, str(bundle))
    search_backend = os.environ.get(
        "AGENT_ENGINE_BACKEND", os.environ.get("PUCT_ENGINE_BACKEND", "native-cg"))
    if search_backend == "cgpy":                       # ADR-0050 M3: the agent's `cg`
        from cgpy.alias import install                 # imports resolve to the cgpy twin
        install()
        from cgpy.puct import register_backend
        register_backend()

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
            context = capture_records(suppress_output=True)
        else:
            context = nullcontext([])
        request = json.loads(line)
        if isinstance(request, dict) and request.get("telemetry_control") == "receipt":
            if emit_enabled:
                from common.telemetry import flush
                try:
                    flush()
                except Exception:
                    pass
            session = agent.runtime.telemetry_session
            receipt = (session.close_episode()
                       if session.episode_key == str(request.get("episode_key")) else None)
            proto.write(json.dumps({"receipt": receipt}) + "\n")
            proto.flush()
            continue
        if request == {"telemetry_control": "flush"}:
            if emit_enabled:
                from common.telemetry import flush
                flush()
            proto.write('{"flushed":true}\n')
            proto.flush()
            break
        if isinstance(request, dict) and "observation" in request \
                and "telemetry_episode_key" in request:
            observation = request["observation"]
            from common.telemetry import episode_context
            episode = episode_context(request["telemetry_episode_key"])
        else:
            observation = request
            episode = nullcontext()
        with episode, context as records:
            if emit_enabled:
                from common.telemetry import take_caller_seconds
                take_caller_seconds()
            choice = agent(observation)
        if capture:
            payload = {"choice": [int(i) for i in choice], "telemetry": records,
                       "telemetry_seconds": records.emit_seconds}
        elif emit_enabled:
            payload = {"choice": [int(i) for i in choice], "telemetry": [],
                       "telemetry_seconds": take_caller_seconds()}
        else:
            payload = [int(i) for i in choice]
        proto.write(json.dumps(payload) + "\n")
        proto.flush()


if __name__ == "__main__":
    main()
