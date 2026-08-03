"""WIN BAND — does any NON-winning option out-score a coin-free simulated WIN? (Issue #362)

`planner._engine_leaf_value` short-circuits a coin-free simulated win to a dominant terminal value.
Its magnitude used to be `KO_SCORE * (start_prizes + 1)` — and `start_prizes` counts prizes still
REMAINING, so it paid a win MOST when six prizes were still to take and LEAST when the win was about
to land. It was written against the retired hand-composed leaf, whose entire positional band summed
to 590 against `KO_SCORE` 1000, and there even its floor was dominant. Since the POC-T3 swap
(Issue #262) the other branch is `KO_SCORE * state_value(board)`, whose `prize_race` lead leg has
UNIT SLOPE and is deliberately uncapped — so a merely-WINNING position out-scored a won GAME, and
nothing in the tree asserted otherwise. `state_value.WIN_PRIZES` is the derived band that fixed it.

This probe is what makes that claim CHECKABLE instead of remembered. It sweeps every correction whose
observation can be reseeded, scores every option through the SHIPPED leaf, and reports the two
numbers the issue's acceptance is stated in:

    python tools/train/probes/win_band_sweep.py           # the shipped leaf: expect 0 of 26
    python tools/train/probes/win_band_sweep.py --legacy  # the retired magnitude, for the contrast

Measured 2026-08-03 at the fix's parent commit `5f44bd86` (cgpy backend): **26** frames reach a
coin-free simulated win, **4** of them out-scored by a non-win — `82749168|1|decision|88` (won 2000
vs 6789.9), `82523164|1|decision|75` (3000 vs 4914.5), `82524455|1|decision|55` (5000 vs 6191.2),
`82522698|1|decision|62` (4000 vs 4400.7). At `HEAD`: **0 of 26**.

**The positive control is not optional and is asserted, not printed.** A sweep that never reached the
win branch — a broken reseed, an unbuildable agent, a renamed tuple element — would report "0 of 0
out-scored", which is indistinguishable from a clean result. So a run with no win frames RAISES.

cgpy is a parity-limited twin of the native engine, so the leaf VALUES differ slightly from native;
the ORDERING between a win and a non-win is the signal, and it is the same signal `leaf_lab.py` acts
on. Frames whose agent cannot be built, or whose every option fails to sim, are skipped and counted.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]   # tools/train/probes/x.py -> repo root
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from train.leaf_lab import _cgpy_pilot_builder, _PLACEHOLDER_SBI, frame_key   # noqa: E402
from train.blunder.store import load_corrections                              # noqa: E402
from common.state_value import WIN_PRIZES, state_value                        # noqa: E402
from common.strategy.context import KO_SCORE                                  # noqa: E402
from common.strategy.planner import _LINE_CAP                                 # noqa: E402


def option_values(pilot, obs, n_options, *, legacy: bool):
    """``[(win_value_or_None, value), ...]`` per option, index-aligned; ``None`` where the sim failed.

    Both branches are re-derived around the REAL `_simulate_line` rather than read off
    `_engine_leaf_value`, because the whole question is what the two branches pay RELATIVE to each
    other — and `--legacy` has to be able to score a magnitude the shipped leaf no longer has.
    """
    out = []
    for i in range(n_options):
        pilot._planning = True                      # the rung's reentrancy guard (never nest a search)
        try:
            sim = pilot._simulate_line(obs, [i])
        except Exception:                           # noqa: BLE001 — a failed fork is skipped, counted
            sim = None
        finally:
            pilot._planning = False
        if sim is None:
            out.append(None)
            continue
        end, my_index, start_prizes, result, line_val, coins, _stream = sim
        won = (result == my_index and not coins)    # the shipped gate: COINS alone, never `stream`
        try:
            board = (KO_SCORE * state_value(pilot._leaf_state_model(end, my_index))
                     + min(_LINE_CAP, line_val))
        except Exception:                           # noqa: BLE001
            board = None
        if not won:
            out.append((None, board))
            continue
        win = KO_SCORE * (start_prizes + 1) if legacy else KO_SCORE * WIN_PRIZES
        out.append((win, win))
    return out


def sweep(*, legacy: bool) -> dict:
    build = _cgpy_pilot_builder()
    corrs = [c for c in load_corrections(REPO / "data" / "corrections") if (getattr(c, "obs", None) or {})]
    swept = skipped = 0
    win_frames, out_scored = [], []
    for c in corrs:
        pilot = build(c.agent)
        if pilot is None:
            skipped += 1
            continue
        obs = {**c.obs, "search_begin_input": c.obs.get("search_begin_input") or _PLACEHOLDER_SBI}
        options = (obs.get("select") or {}).get("option") or []
        if not options:
            skipped += 1
            continue
        swept += 1
        rows = option_values(pilot, obs, len(options), legacy=legacy)
        wins = [r[0] for r in rows if r and r[0] is not None]
        if not wins:
            continue
        key = frame_key(c)
        win_frames.append(key)
        best_win = max(wins)
        over = [(i, r[1]) for i, r in enumerate(rows)
                if r and r[0] is None and r[1] is not None and r[1] > best_win]
        if over:
            i, v = max(over, key=lambda t: t[1])
            out_scored.append((key, best_win, i, v))
    return {"swept": swept, "skipped": skipped, "win_frames": win_frames, "out_scored": out_scored}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--legacy", action="store_true",
                    help="score wins with the RETIRED `KO_SCORE * (start_prizes + 1)` magnitude")
    args = ap.parse_args()
    r = sweep(legacy=args.legacy)
    band = "LEGACY KO_SCORE x (start_prizes + 1)" if args.legacy else f"WIN_PRIZES {WIN_PRIZES}"
    print(f"\n=== win band ({band}) — {r['swept']} frames swept, {r['skipped']} skipped ===")
    print(f"frames reaching a coin-free simulated WIN: {len(r['win_frames'])}")
    # THE POSITIVE CONTROL. Not a print — an assertion. "0 of 0 out-scored" reads exactly like a
    # clean result, so an instrument that stopped reaching the win branch must fail loudly.
    assert r["win_frames"], (
        "POSITIVE CONTROL FAILED: no frame reached the win branch, so a clean report would be "
        "vacuous. The sweep is broken, not the leaf.")
    print(f"of those, out-scored by a NON-winning option: {len(r['out_scored'])}")
    for key, win, i, val in sorted(r["out_scored"], key=lambda t: t[3] - t[1], reverse=True):
        print(f"  {key}  win {win:.1f}  out-scored by opt {i} at {val:.1f}  margin {val - win:.1f}")
    return 1 if r["out_scored"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
