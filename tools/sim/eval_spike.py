"""Duplicate-POSITION replay spike (ADR-0053 WP2 design D4) — PLUMBING ONLY, never a measurement.

Duplicate-DEAL is impossible: the engine has no deal seed and a `search_begin` fork reshuffles every
predicted hidden zone (`docs/pyeng/determinism.md` §4). Identical opening POSITIONS can be replayed
by forking a captured frame. Two caveats keep this off the primary G2 path: only a plain MAIN select
is fork-deterministic, and a playout Pilot runs BELOW live strength (a fork obs carries no
`search_begin_input`, so its own fork tiers are silently OFF, and opponent zones are seeded
count-correct but not identity-correct).
"""
from __future__ import annotations

# The plain-MAIN select class — the only fork-deterministic frame (determinism.md §4).
_MAIN_CONTEXT = 0
_MAIN_TYPE = 0


def opening_frames(replay: dict) -> list[dict]:
    """The obs at every plain-MAIN, seed-bearing frame — the only points a fork can re-enter
    DETERMINISTICALLY. Pure film parsing; no engine, never raises."""
    from train.blunder.decisions import _film

    out = []
    for frame in _film(replay):
        obs = frame.get("obs") or {}
        select = obs.get("select") or {}
        if (select.get("context") == _MAIN_CONTEXT and select.get("type") == _MAIN_TYPE
                and select.get("option") and obs.get("search_begin_input")):
            out.append(obs)
    return out


def first_opening(replay: dict) -> dict | None:
    """The first plain-MAIN, seed-bearing obs, or None — the natural single fork point per game."""
    frames = opening_frames(replay)
    return frames[0] if frames else None


def fork_seed(pilot, obs: dict) -> tuple:
    """``search_begin``'s zone arguments via the shipped ``pilot._seed_zones``. Opponent zones are
    count-correct, NOT identity-correct."""
    cur = obs.get("current") or {}
    yi = cur.get("yourIndex", 0)
    players = cur.get("players") or []
    me = players[yi] if 0 <= yi < len(players) else {}
    opp = players[1 - yi] if 0 <= 1 - yi < len(players) else {}
    return pilot._seed_zones(obs, me, opp)


def fork_playout(pilot, obs: dict, *, max_steps: int = 400, manual_coin: bool = False) -> dict:
    """Fork from ``obs`` and drive the Pilot forward -> ``{steps, terminal, result, error}``. Any
    engine error is CAPTURED into ``error``, never raised, and the search is always released."""
    from dataclasses import asdict

    from common.strategy.planner import _prune_none

    if not obs.get("search_begin_input"):
        return {"steps": 0, "terminal": False, "result": None, "error": "no seed"}
    try:
        from cg import api as cgapi
    except Exception as e:                                   # engine unavailable -> no-op, not a crash
        return {"steps": 0, "terminal": False, "result": None, "error": f"no engine: {e}"}

    steps, terminal, result, error = 0, False, None, None
    was_planning = getattr(pilot, "_planning", False)
    pilot._planning = True
    try:
        yd, yp, od_, op_, oh = fork_seed(pilot, obs)         # inside try: _seed_zones can raise on a bad frame
        st = cgapi.search_begin(cgapi.to_observation_class(obs), yd, yp, od_, op_, oh, [],
                                manual_coin=manual_coin)
        for _ in range(max_steps):
            o = st.observation
            c = o.current
            if c is None or c.result != -1 or o.select is None:
                terminal = c is not None and c.result != -1
                result = c.result if (terminal and c.result in (0, 1)) else None
                break
            decoded = _prune_none(asdict(o))
            st = cgapi.search_step(st.searchId, list(pilot.decide(decoded)))
            steps += 1
    except Exception as e:                                   # a fork error ends THIS playout, not the run
        error = f"{type(e).__name__}: {e}"
    finally:
        try:
            cgapi.search_end()
        except Exception:
            pass
        pilot._planning = was_planning
    return {"steps": steps, "terminal": terminal, "result": result, "error": error}
