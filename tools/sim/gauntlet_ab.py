"""Tier-5 paired-delta cross-deck A/B runner (grilled 2026-07-05).

For each DIRECTED matchup (our deck D vs a fixed baseline opponent O≠D), measure D's win-rate with
``value_model`` ON vs OFF against the SAME O, and aggregate the on−off deltas (`sim.paired_ab`) — the
paired difference subtracts out the raw deck matchup (D may beat O 55% regardless), leaving only the
switch's effect. Prints the aggregate delta + 95% CI and the grilled flip decision (ON iff aggregate
delta ≥ 0 AND CI lower bound ≥ −1% AND zero crashes).
"""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from sim.battle import read_deck, run_battle          # noqa: E402
from sim.paired_ab import flips_on, paired_delta       # noqa: E402


def _wins(results):
    """(A-wins, n, crashes) from a Battle's contestant-relative BattleMatch list — A is our deck D."""
    n = len(results)
    a_wins = sum(1 for r in results if r.winner == 0)
    crashes = sum(len(r.crashed) for r in results)
    return a_wins, n, crashes


def run(agents, n, *, jobs, overlay, out_dir):
    """Run the 6 directed matchups (both battles each) and report the aggregate paired delta + flip."""
    agents_root = REPO / "src" / "agents"
    src = [REPO / "src"]
    matchups, table, total_crashes = [], [], 0
    for d, o in itertools.permutations(agents, 2):
        dd, do = agents_root / d, agents_root / o
        deck_d, deck_o = read_deck(dd), read_deck(do)
        on = run_battle(dd, do, deck_d, deck_o, n, jobs=jobs, extra_syspath=src, overlay_a=overlay)
        off = run_battle(dd, do, deck_d, deck_o, n, jobs=jobs, extra_syspath=src)
        on_w, on_n, on_c = _wins(on)
        off_w, off_n, off_c = _wins(off)
        total_crashes += on_c + off_c
        matchups.append((on_w, on_n, off_w, off_n))
        delta = on_w / on_n - off_w / off_n
        table.append({"matchup": f"{d} vs {o}", "on": [on_w, on_n], "off": [off_w, off_n],
                      "delta": round(delta, 4), "crashes": on_c + off_c})
        print(f"  {d:14s} vs {o:14s}: on {on_w}/{on_n}={on_w/on_n:.3f}  "
              f"off {off_w}/{off_n}={off_w/off_n:.3f}  delta={delta:+.3f}  crashes={on_c + off_c}",
              flush=True)
    result = paired_delta(matchups)
    flip = flips_on(result, crashes=total_crashes)
    print(f"\nAGGREGATE delta={result['delta']:+.4f}  95% CI "
          f"[{result['ci_lo']:+.4f}, {result['ci_hi']:+.4f}]  crashes={total_crashes}")
    print(f"FLIP value_model ON: {flip}  (rule: delta>=0 AND CI-lo>=-0.01 AND crashes==0)")
    out = Path(out_dir) / "t5_paired_ab.json"
    out.write_text(json.dumps({"table": table, "result": result, "crashes": total_crashes,
                               "flip": flip, "n_per_battle": n}, indent=2), encoding="utf-8")
    print(f"-> {out}")
    return result, flip


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Tier-5 paired-delta cross-deck A/B (ADR-0042 finish).")
    ap.add_argument("agents", nargs="+", help="our agents (e.g. mega_starmie mega_lucario dragapult_ex)")
    ap.add_argument("-n", "--games", type=int, default=4000, help="games per battle (default 4000)")
    ap.add_argument("-j", "--jobs", type=int, default=10)
    ap.add_argument("--overlay", required=True, help="value-on overlay JSON ({'params':{'value_model':true}})")
    ap.add_argument("--out", default=str(REPO / "reports"))
    args = ap.parse_args(argv)
    Path(args.out).mkdir(parents=True, exist_ok=True)
    run(args.agents, args.games, jobs=args.jobs, overlay=args.overlay, out_dir=args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
