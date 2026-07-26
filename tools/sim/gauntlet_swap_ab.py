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

**Two stage rules, chosen by ``--stage`` (#136 directive 6, re-scoped by ADR-0072).** ``mid-build``
(Phases 1a–1g) is the **Tripwire**: ``crashes == 0 AND CI-lo >= -5%``, with **no delta clause** — a
mid-build decider swap is not trying to raise win rate, so merit belongs to the two deterministic
per-frame gates in ``train.gates`` and this run only excludes catastrophes. ``post-composition``
(#145 onward) is the original `flips_on` verbatim, where a positive delta is meaningful.

**Read the precision beside the verdict.** Both rules are a 95% CI LOWER BOUND, so a clearly positive
delta can clear one at a width that could never have done so on its own — and under the
post-composition rule a delta near zero cannot clear it without thousands of games per arm per
matchup (1b: n ≈ 2340/arm/matchup, ~28,000 games). The report prints the rule's verdict, the stage it
applied, and the half-width achieved, so a wide-but-passing interval is never read as precision it
does not have. What any run establishes unconditionally is the crash gate (a hard zero) and the
exclusion of a regression larger than the CI lower bound.
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
from sim.paired_ab import (MID_BUILD_REG_TOL, _REG_TOL, flips_on,  # noqa: E402
                           mid_build_verdict, paired_delta)


def _wins(results):
    """(A-wins, n, crashes) from a Battle's contestant-relative BattleMatch list — A is our deck D."""
    n = len(results)
    return sum(1 for r in results if r.winner == 0), n, sum(len(r.crashed) for r in results)


#: The two stage rules of #136 directive 6 (ADR-0072 decision 1). ``mid-build`` (Phases 1a–1g) is the
#: Tripwire — crashes==0 AND CI-lo >= -5%, NO delta clause; merit lives in the two deterministic
#: per-frame gates (`train.gates`). ``post-composition`` (#145 onward) is `flips_on` verbatim.
STAGES = {
    "mid-build": (mid_build_verdict, MID_BUILD_REG_TOL,
                  "CI-lo>=-0.05 AND crashes==0 (NO delta clause)", "TRIPWIRE"),
    "post-composition": (flips_on, _REG_TOL,
                         "delta>=0 AND CI-lo>=-0.01 AND crashes==0", "FLIP"),
}


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
    # The rule is the CI LOWER BOUND, not the half-width: a positive enough delta clears the bound at
    # a width that could never have done so on its own. Report both, so a wide-but-passing interval is
    # not read as precision it does not have, and a narrow-but-failing one is not excused.
    print(f"PRECISION: +-{half:.1%} at n={n} per arm per matchup — this run excludes a regression "
          f"worse than {abs(result['ci_lo']):.1%}, and is {'' if half <= reg_tol else 'NOT '}tight "
          f"enough to have cleared the rule on width alone.")
    print(f"STAGE: {stage}")
    # The label follows the stage: mid-build is a TRIPWIRE, never a "flip rule" — that phrase is on
    # the Tripwire's _Avoid_ list (tools/sim/CONTEXT.md) precisely because it claims more than the
    # verdict means.
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
