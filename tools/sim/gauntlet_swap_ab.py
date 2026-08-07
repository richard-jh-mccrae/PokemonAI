"""Paired-delta A/B for a CODE SWAP — the merge evidence a decider swap owes (ADR-0069 §8).

`gauntlet_ab.py` A/Bs a PROFILE flag with both arms on the same code — the wrong instrument once a
swap DELETES the flag's fallback, since flag-OFF is then degraded mode, not the incumbent. This
runner A/Bs two BUILDS, opponent held fixed at the incumbent:

    ON = winrate(D@candidate vs O@incumbent), OFF = winrate(D@incumbent vs O@incumbent)

Two builds in one process is the ``sys.modules`` collision the harness is process-isolated to
avoid, so each contestant is a self-contained BUNDLE in its own subprocess, NO shared syspath.
    python tools/sim/gauntlet_swap_ab.py --candidate /tmp/ab/new_bundles \\
        --incumbent /tmp/ab/old_bundles --n 200 --jobs 4 --out /tmp/ab

``--stage`` picks the rule (`paired_ab.STAGES`); both are a 95% CI LOWER BOUND, so the report prints
the achieved half-width beside the verdict — a wide-but-passing interval is not precision."""
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
from sim.paired_ab import STAGES, paired_delta          # noqa: E402


def _wins(results):
    """(A-wins, n, crashes) from a Battle's contestant-relative BattleMatch list — A is our deck D."""
    n = len(results)
    return sum(1 for r in results if r.winner == 0), n, sum(len(r.crashed) for r in results)


def run(agents, n, *, candidate: Path, incumbent: Path, jobs: int, out_dir: Path, stage: str):
    verdict_fn, reg_tol, rule_text, verdict_label = STAGES[stage]
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
    verdict = verdict_fn(result, crashes=crashes)
    print(f"\nAGGREGATE delta={result['delta']:+.4f}  95% CI "
          f"[{result['ci_lo']:+.4f}, {result['ci_hi']:+.4f}]  (+-{half:.4f})  crashes={crashes}")
    # The rule is the CI LOWER BOUND, not the half-width, so both are reported: a positive enough
    # delta clears the bound at a width that could never have done so on its own.
    print(f"PRECISION: +-{half:.1%} at n={n} per arm per matchup — this run excludes a regression "
          f"worse than {abs(result['ci_lo']):.1%}, and is {'' if half <= reg_tol else 'NOT '}tight "
          f"enough to have cleared the rule on width alone.")
    print(f"STAGE: {stage}")
    # mid-build is a TRIPWIRE, never a "flip rule" — that phrase is on the Tripwire's _Avoid_ list
    # (`tools/sim/CONTEXT.md`) because it claims more than the verdict means.
    print(f"{verdict_label}: {verdict}  (rule: {rule_text})")
    if stage == "mid-build":
        # Say what this verdict does NOT claim, next to the verdict itself — the whole failure mode
        # ADR-0072 exists to fix was a red/green symbol read as more than it meant.
        print("NOTE: mid-build excludes CATASTROPHES only — this is NOT a claim of non-regression. "
              "Merit is the Decision Gate + Discrimination Gate (train.gates), not this number.")
    print(f"{sum(m[1] + m[3] for m in matchups)} games in {round(time.time() - started)}s")
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "swap_paired_ab.json"
    out.write_text(json.dumps({"table": table, "result": result, "crashes": crashes,
                               "verdict": verdict, "verdict_label": verdict_label,
                               "stage": stage, "rule": rule_text, "reg_tol": reg_tol,
                               "n_per_battle": n, "ci_half_width": half,
                               # NB the width criterion, NOT the stage rule (which is the CI lower
                               # bound) — a run can fail this and still pass on a clear delta.
                               "ci_width_under_1pct": half <= 0.01}, indent=2), encoding="utf-8")
    print(f"-> {out}")
    return result, verdict


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--candidate", type=Path, required=True, help="dir of candidate-build bundles")
    ap.add_argument("--incumbent", type=Path, required=True, help="dir of incumbent-build bundles")
    ap.add_argument("--agents", nargs="+",
                    default=["dragapult_ex", "mega_lucario", "mega_starmie"])
    ap.add_argument("--n", type=int, default=200, help="matches per arm per directed matchup")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--out", type=Path, default=REPO / "reports")
    ap.add_argument("--stage", choices=sorted(STAGES), required=True,
                    help="which #136 directive-6 rule grades this run (ADR-0072): 'mid-build' "
                         "(Phases 1a-1g) is the Tripwire — crashes==0 AND CI-lo>=-5%%, no delta "
                         "clause; 'post-composition' (#145 onward) is the original flip rule. "
                         "REQUIRED: a run must name the rule that graded it")
    a = ap.parse_args()
    run(a.agents, a.n, candidate=a.candidate, incumbent=a.incumbent, jobs=a.jobs, out_dir=a.out,
        stage=a.stage)
