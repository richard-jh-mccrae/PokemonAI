"""Paired-delta A/B for a CODE SWAP — the merge evidence a decider swap owes (#139, ADR-0069 §8).

`gauntlet_ab.py` A/Bs a PROFILE flag: it flips the switch through an overlay while both arms run the
same code. That is the wrong instrument once a swap DELETES what the switch used to fall back to —
flag-OFF is then degraded mode, not the incumbent, and the on−off delta measures the decider against
nothing. This runner A/Bs two BUILDS instead.

The construction is the same paired one (`sim.paired_ab`), with the opponent held fixed at the
INCUMBENT build so the raw deck matchup subtracts out:

    for each directed matchup (D, O), D != O:
        ON  = winrate(D@candidate  vs  O@incumbent)
        OFF = winrate(D@incumbent  vs  O@incumbent)
        delta = ON - OFF

Both arms are seat-balanced by ``seat_plan`` (ADR-0021), so first/second-player advantage cancels
inside each arm rather than being handed to one side.

Two builds in one process is exactly the ``sys.modules`` collision the battle harness was
process-isolated to avoid — so each contestant is a self-contained BUNDLE (`submit.package`, which
stages `common/` and `cg/` into the bundle) and is served by its own subprocess with NO shared
``extra_syspath``. That is what lets candidate `common/` and incumbent `common/` coexist.

    # stage the incumbent from a worktree at the pre-swap commit, then:
    python tools/sim/gauntlet_swap_ab.py --candidate /tmp/ab/new_bundles \\
        --incumbent /tmp/ab/old_bundles --n 200 --jobs 4 --out /tmp/ab

**Read the power before reading the verdict.** The grilled flip rule wants a 95% CI lower bound at or
above −1%, which at these variances needs thousands of games per arm per matchup. A short run cannot
clear it and does not pretend to: the report prints the half-width it achieved, so "not powered" is
visible rather than silently reported as "no regression". What a short run DOES establish soundly is
the crash gate (a hard zero) and the exclusion of any regression larger than that half-width.
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from sim.battle import read_deck, run_battle          # noqa: E402
from sim.paired_ab import flips_on, paired_delta       # noqa: E402


def _wins(results):
    """(A-wins, n, crashes) from a Battle's contestant-relative BattleMatch list — A is our deck D."""
    n = len(results)
    return sum(1 for r in results if r.winner == 0), n, sum(len(r.crashed) for r in results)


def run(agents, n, *, candidate: Path, incumbent: Path, jobs: int, out_dir: Path):
    matchups, table, crashes = [], [], 0
    started = time.time()
    for d, o in itertools.permutations(agents, 2):
        deck_d, deck_o = read_deck(candidate / d), read_deck(incumbent / o)
        # NO extra_syspath: each bundle must import ITS OWN common/, which is the whole point.
        on = run_battle(candidate / d, incumbent / o, deck_d, deck_o, n, jobs=jobs)
        off = run_battle(incumbent / d, incumbent / o, read_deck(incumbent / d), deck_o, n, jobs=jobs)
        on_w, on_n, on_c = _wins(on)
        off_w, off_n, off_c = _wins(off)
        crashes += on_c + off_c
        matchups.append((on_w, on_n, off_w, off_n))
        delta = on_w / on_n - off_w / off_n
        table.append({"matchup": f"{d} vs {o}", "on": [on_w, on_n], "off": [off_w, off_n],
                      "delta": round(delta, 4), "crashes": on_c + off_c})
        print(f"  {d:14s} vs {o:14s}: cand {on_w}/{on_n}={on_w / on_n:.3f}  "
              f"incumbent {off_w}/{off_n}={off_w / off_n:.3f}  delta={delta:+.3f}  "
              f"crashes={on_c + off_c}", flush=True)
    result = paired_delta(matchups)
    half = (result["ci_hi"] - result["ci_lo"]) / 2
    flip = flips_on(result, crashes=crashes)
    print(f"\nAGGREGATE delta={result['delta']:+.4f}  95% CI "
          f"[{result['ci_lo']:+.4f}, {result['ci_hi']:+.4f}]  (+-{half:.4f})  crashes={crashes}")
    print(f"POWER: this run excludes a regression worse than {half:.1%}; the grilled rule wants "
          f"the CI lower bound at or above -1.0%, so it is {'MET' if half <= 0.01 else 'NOT MET'} "
          f"at n={n} per arm per matchup.")
    print(f"FLIP: {flip}  (rule: delta>=0 AND CI-lo>=-0.01 AND crashes==0)")
    print(f"{sum(m[1] + m[3] for m in matchups)} games in {round(time.time() - started)}s")
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "swap_paired_ab.json"
    out.write_text(json.dumps({"table": table, "result": result, "crashes": crashes, "flip": flip,
                               "n_per_battle": n, "ci_half_width": half,
                               "powered_for_flip_rule": half <= 0.01}, indent=2), encoding="utf-8")
    print(f"-> {out}")
    return result, flip


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--candidate", type=Path, required=True, help="dir of candidate-build bundles")
    ap.add_argument("--incumbent", type=Path, required=True, help="dir of incumbent-build bundles")
    ap.add_argument("--agents", nargs="+",
                    default=["dragapult_ex", "mega_lucario", "mega_starmie"])
    ap.add_argument("--n", type=int, default=200, help="matches per arm per directed matchup")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--out", type=Path, default=REPO / "reports")
    a = ap.parse_args()
    run(a.agents, a.n, candidate=a.candidate, incumbent=a.incumbent, jobs=a.jobs, out_dir=a.out)
