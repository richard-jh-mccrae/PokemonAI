"""The expert: one-step engine-fork value lookahead over the option menu (s3b §D1).

Per legal option: fork the engine (`search_begin`, hidden zones from the Pilot's own `_seed_zones`),
`search_step([i])`, then read ``V_i`` from the value net — with a **terminal override**, since an
engine-called game scores the sound 1.0 / 0.0 / 0.5. Seat-consistent, so an opponent-seat obs reads
as ``1 − P(opponent wins)``, and a fresh fork per option because `search_step` advances in place.
**v1:** single-pick only — multi-pick is gated out by ``is_single_pick`` rather than faked.
"""
from __future__ import annotations

from dataclasses import asdict

from common.value.features import features_from_board


def is_single_pick(select: dict) -> bool:
    """``maxCount == 1``. Multi-pick selects (discard-2, multi-grab) are v1-deferred and gated out."""
    return select.get("maxCount") == 1


def _prune_none(v):
    """``asdict``-ed Observation -> the live-obs shape: drop None-VALUED dict keys (the live JSON omits
    them), but KEEP None list elements (a facedown Active carries the zone's count)."""
    if isinstance(v, dict):
        return {k: _prune_none(x) for k, x in v.items() if x is not None}
    if isinstance(v, list):
        return [_prune_none(x) for x in v]
    return v


def _read_v(pilot, obs_dict: dict, model, my_seat: int) -> float | None:
    """``P(my win)`` on a forked obs. Terminal override first (``result``: 0/1 = that seat wins, 2 =
    draw, -1 = ongoing), else the value net flipped to my seat — features are seat-relative."""
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
    """``{option_index: V_i}``, or None when the frame is unscorable. A null ``model`` raises; a failed fork is skipped."""
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
