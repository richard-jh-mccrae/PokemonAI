"""Duplicate-POSITION replay spike (ADR-0053 WP2 design D4) — PLUMBING ONLY.

The scoped "duplicate-deal" eval is impossible: the engine has no deal seed and a `search_begin`
fork RESHUFFLES every predicted hidden zone (docs/pyeng/determinism.md §4), so identical *deals*
can't be replayed. Identical opening *positions* can: fork from a captured frame and drive repeated
playouts. This module builds that driver; the variance-reduction VERDICT that decides whether it
ships as an auxiliary eval mode is the spike's timeboxed measurement, gated on a corpus of games —
not built here.

Two recorded caveats keep this OFF the primary G2 path (see the design doc):
- **Fork-deterministic frames only.** A native fork is call-to-call reproducible ONLY from a plain
  MAIN select (context 0, type 0); mid-effect forks are not. `opening_frames` yields exactly those.
- **Playout agents run below live strength.** A fork observation carries no `search_begin_input`,
  so the Pilot inside a playout cannot nest its own forks — its lethal-confirm / simulate-line
  tiers are silently OFF. Both arms are equally degraded, but a playout is a DIFFERENT game than
  the live one. v1 also seeds opponent zones count-correct-but-not-identity (the planner's
  `_seed_zones`); true-identity reconstruction from the opponent's own frames is the fidelity
  upgrade the measurement mode needs, not the plumbing.
"""
from __future__ import annotations

# The plain-MAIN select class — the only fork-deterministic frame (determinism.md §4).
_MAIN_CONTEXT = 0
_MAIN_TYPE = 0


def opening_frames(replay: dict) -> list[dict]:
    """The obs at every plain-MAIN, seed-bearing decision frame of ``replay`` — the identical-
    POSITION replay points a fork can re-enter deterministically. A frame qualifies iff its select
    is ``(context 0, type 0)`` with options AND the obs carries a ``search_begin_input`` fork seed.
    Pure film parsing — no engine, never raises."""
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
    """Assemble the ``search_begin`` zone arguments for ``obs`` via the shipped seeding
    (``pilot._seed_zones``): ``(your_deck, your_prize, opp_deck, opp_prize, opp_hand)``, each a
    card-id multiset count-matched to the observation. Opponent zones are count-correct, not
    identity-correct (the v1 caveat). Raises only if the obs has no full board."""
    cur = obs.get("current") or {}
    yi = cur.get("yourIndex", 0)
    players = cur.get("players") or []
    me = players[yi] if 0 <= yi < len(players) else {}
    opp = players[1 - yi] if 0 <= 1 - yi < len(players) else {}
    return pilot._seed_zones(obs, me, opp)


def fork_playout(pilot, obs: dict, *, max_steps: int = 400, manual_coin: bool = False) -> dict:
    """Fork the engine from ``obs`` and drive the Pilot's policy forward until the fork reaches a
    terminal verdict, runs out of selects, or hits ``max_steps``. Returns ``{steps, terminal,
    result, error}`` — ``terminal`` True iff the fork reached an engine verdict (``result`` 0/1, or
    None for a draw). A spike must never crash the harness, so any engine error is captured into
    ``error`` (never raised) and the search is always released.

    NOT a measurement: the playout Pilot's fork tiers are off (no nested forks) and unrevealed
    order is reshuffled — this proves the position-replay driver runs, nothing about strength."""
    from dataclasses import asdict

    from common.strategy.planner import _prune_none

    if not obs.get("search_begin_input"):
        return {"steps": 0, "terminal": False, "result": None, "error": "no seed"}
    try:
        from cg import api as cgapi
    except Exception as e:                                   # engine unavailable -> no-op, not a crash
        return {"steps": 0, "terminal": False, "result": None, "error": f"no engine: {e}"}

    yd, yp, od_, op_, oh = fork_seed(pilot, obs)
    steps, terminal, result, error = 0, False, None, None
    was_planning = getattr(pilot, "_planning", False)
    pilot._planning = True
    try:
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
