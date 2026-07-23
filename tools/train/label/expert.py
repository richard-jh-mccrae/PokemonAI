"""The expert: one-step engine-fork value lookahead over the option menu (s3b design §D1).

The expert is the shipped Pilot's value net used as an oracle. For a single-pick decision frame it
scores each legal option ``i``:

1. **Fork** the engine from the frame — ``search_begin`` with both-sides zones. The hidden-zone
   predictions reuse the Pilot's own battle-tested ``_seed_zones`` (the exact anchored own-split when
   the tracker has anchored, a sound decklist prefix otherwise — the same seeding the Lethal Solver
   forks with). A fresh fork per option: ``search_step`` advances a search tree in place, so options
   can't branch off one root.
2. **Step** ``search_step([i])`` → the resulting observation.
3. **Read** ``V_i`` = the value net's ``P(win)`` on that board, with a **terminal override**: if the
   engine has already called the game (result 0/1/2), the sound 1.0 / 0.0 / 0.5 outranks the net —
   the same invariant as the planner's win rung. Seat-consistent: a turn-ender that hands control to
   the opponent yields an opponent-seat obs, read as ``1 − P(opponent wins)``.

**v1 scope (design):** single-pick contexts only (MAIN + single selects). Multi-pick (discard-2,
multi-grab) is deferred — the expert can't enumerate subsets yet, so ``is_single_pick`` gates them
out rather than faking a partial pick. Stochastic effects take one engine sample (``manual_coin`` off);
the θ threshold absorbs the noise (expectimax over coin outcomes is v2).
"""
from __future__ import annotations

from dataclasses import asdict

from common.value.features import features_from_board


def is_single_pick(select: dict) -> bool:
    """True for a choose-exactly-one (or at-most-one) select — ``maxCount == 1``. Multi-pick selects
    (``maxCount > 1``: discard-2, multi-grab) are v1-deferred and gated out here."""
    return select.get("maxCount") == 1


def _prune_none(v):
    """``asdict``-ed engine Observation → the live-obs dict shape: drop None-VALUED dict keys (the
    live JSON omits them; ``option.get('playerIndex', ...)`` would otherwise read None and crash), but
    KEEP None list elements (a facedown Active carries the zone's count). Mirrors the planner helper."""
    if isinstance(v, dict):
        return {k: _prune_none(x) for k, x in v.items() if x is not None}
    if isinstance(v, list):
        return [_prune_none(x) for x in v]
    return v


def _read_v(pilot, obs_dict: dict, model, my_seat: int) -> float | None:
    """``P(my win)`` on a forked resulting obs. Terminal override first (engine ``result``: 0/1 = that
    seat wins, 2 = draw, -1 = ongoing). Otherwise the value net, flipped to my seat when the resulting
    obs belongs to the opponent (features are seat-relative). None if the board can't be built."""
    cur = obs_dict.get("current") or {}
    result = cur.get("result", -1)
    if result == 2:
        return 0.5                                     # draw (the simulator's delta: no tiebreak)
    if result in (0, 1):
        return 1.0 if result == my_seat else 0.0
    try:
        board = pilot._board(obs_dict, obs_dict.get("select"))
    except Exception:
        return None
    p = model.predict(features_from_board(board))
    yi = cur.get("yourIndex")
    return p if yi == my_seat else 1.0 - p


def evaluate_options(pilot, obs: dict, model, *, manual_coin: bool = False) -> dict | None:
    """``{option_index: V_i}`` for a single-pick decision, or None when the frame isn't scorable
    (no seed, multi-pick, opponent Active facedown, or the engine unavailable).

    ``model`` must be present — a null model raises (offline tools fail loud, per vread). Each option
    forks independently; an option whose fork/step raises (a seed-prefix mismatch on a fetch line) is
    skipped, not fatal — the detector compares whatever options scored.
    """
    if not getattr(model, "present", False):
        raise ValueError("expert requires a present value model (a null model would score every "
                         "option 0.5). Pass a trained value_model.json via --model.")
    if not obs.get("search_begin_input"):
        return None
    select = obs.get("select")
    if not isinstance(select, dict) or not select.get("option") or not is_single_pick(select):
        return None
    cur = obs.get("current") or {}
    my_seat = cur.get("yourIndex")
    players = cur.get("players") or []
    if my_seat is None or not (0 <= my_seat < len(players)) or not (0 <= 1 - my_seat < len(players)):
        return None
    me = players[my_seat] or {}
    opp = players[1 - my_seat] or {}
    opp_active = opp.get("active") or []
    if opp_active and opp_active[0] is None:
        return None                                    # facedown opp Active (setup): can't cheaply seed
    try:
        from cg import api as cgapi
    except Exception:
        return None
    yd, yp, od, op_, oh = pilot._seed_zones(obs, me, opp)   # the Pilot's own sound zone predictions

    n_opts = len(select["option"])
    out: dict = {}
    for i in range(n_opts):
        try:
            ob = cgapi.to_observation_class(obs)
            st = cgapi.search_begin(ob, yd, yp, od, op_, oh, [], manual_coin=manual_coin)
            st = cgapi.search_step(st.searchId, [i])
        except Exception:
            continue                                   # illegal in the forked (predicted) state → skip
        v = _read_v(pilot, _prune_none(asdict(st.observation)), model, my_seat)
        if v is not None:
            out[i] = v
    return out or None
