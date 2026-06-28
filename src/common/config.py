"""The agent config loader: resolve the Pilot's (overrides, params) at import.

`overrides` is the Hypothesis weight map the Tuner ships (`tuned.json`, ADR-0018); `params`
are scalar Strategy params (e.g. `search_budget`). An optional offline **experiment overlay**
(env `AGENT_OVERLAY` -> a JSON file `{overrides, params}`) is layered over both for local A/B
(`tools/sim/battle.py`, ADR-0021). Inert on the grader, where `AGENT_OVERLAY` is unset and the
result matches reading `tuned.json` directly.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

OVERLAY_ENV = "AGENT_OVERLAY"


def _read_tuned(root: Path) -> dict:
    """The shipped weight overrides ({hyp_id: weight}), or {} — `root/tuned.json` first, then
    the grader path (kept identical to the agent's historical `_read_tuned`)."""
    for path in (root / "tuned.json", Path("/kaggle_simulations/agent/tuned.json")):
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    return {}


def load_overrides_and_params(strategy_params: dict, *, env=None, root=".") -> tuple[dict, dict]:
    """Return ``(overrides, params)`` for the Pilot, honoring an optional experiment overlay."""
    env = os.environ if env is None else env
    overrides = _read_tuned(Path(root))
    params = dict(strategy_params)
    overlay_path = env.get(OVERLAY_ENV)
    if overlay_path:
        overlay = json.loads(Path(overlay_path).read_text(encoding="utf-8"))
        overrides = {**overrides, **overlay.get("overrides", {})}   # overlay weights win
        params = {**params, **overlay.get("params", {})}            # overlay params win
    return overrides, params
