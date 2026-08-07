"""Fractional-clock discrimination sweep (ADR-0117). **Not a gate.**

Does reading `turns_to_ko_me`'s crossing point fractionally recover REAL discrimination in the
opponent-target ranking, or does it merely break Flat Ties? INT is the pre-ADR-0117 reading,
reconstructed by patching the shipped model route rather than rebuilt; the sham arms are ADR-0118's
mandatory null. Scoped BENCH-ONLY — the opponent's Active is never a legal gust target, and ranking
both areas lets it dominate the argmax.

    python tools/train/probes/fractional_clock_sweep.py
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from train.probes._corpus import replay_agent                  # noqa: E402
from train.probes._sham import (ArmPatch, READING, SHAMS, argmax, bench_subset,  # noqa: E402
                                legs, tie_population, tune as _tune)   # THE shared probe seam
from train.gates import keyed_corrections                      # noqa: E402
from common.state_model import TheirSide                       # noqa: E402
from common.strategy.combat import SurvivalClock               # noqa: E402



class _IntegerClock(ArmPatch):
    """Collapses ``SurvivalClock.exact`` back onto ``.turns`` — the pre-ADR-0117 reading."""

    target, name = TheirSide, "survival_clock"

    @classmethod
    def collapse(cls, clock):
        return SurvivalClock(clock.turns, float(clock.turns))



def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--band", type=float, default=0.0,
                    help="override the sham band (default: FRAC's own measured max effect)")
    args = ap.parse_args(argv)
    tune = _tune()
    frames = sorted(keyed_corrections(REPO / "data" / "corrections",
                                      predicate=lambda c: bool(c.obs and c.agent)))

    captured, errors, scanned = [], Counter(), 0
    ties = {"INT": [0, 0, 0], "FRAC": [0, 0, 0]}
    band = 0.0
    for key, rec in frames:
        try:
            obs = rec.obs
            # A FRESH stateful Pilot per arm: the two must not share a per-decision memo or board
            # cache, or the second would answer with the first's numbers and prove nothing.
            with _IntegerClock():
                p_int = tune._build_pilot(replay_agent(rec))[0]
                before = p_int._opponent_target_rows(obs, p_int._board(obs, obs.get("select") or {}))
            p_frac = tune._build_pilot(replay_agent(rec))[0]
            after = p_frac._opponent_target_rows(obs, p_frac._board(obs, obs.get("select") or {}))
        except Exception as e:
            errors[type(e).__name__] += 1
            continue
        if not (before and after and before[1] and after[1]):
            continue
        scanned += 1
        for name, res in (("INT", before), ("FRAC", after)):
            for i, n in enumerate(tie_population(res[1])):
                ties[name][i] += n
        # The band is FRAC's OWN largest effect on `value`, so a sham cannot lose by being smaller.
        band = max(band, max((abs(a["value"] - b["value"])
                              for a, b in zip(after[1], before[1])), default=0.0))
        captured.append((key, before[1], after[1]))

    band = args.band or band or 1e-6
    moved: Counter = Counter()
    counts: Counter = Counter()
    for _key, before, after in captured:
        for scope in ("all", "bench"):
            pre, post = bench_subset(before, scope), bench_subset(after, scope)
            if len(pre) < 2:
                continue
            counts[scope] += 1
            base = argmax([r["value"] for r in pre])
            if argmax([r["value"] for r in post]) != base:
                moved[("FRAC", scope)] += 1
            for k, _label in SHAMS:
                # `opponent_target_value` is LINEAR in `prize_advance`, so adding the sham leg to the
                # finished value is exactly adding it to that term — one fewer re-derivation.
                shammed = [r["value"] + legs(k, band=band, card_id=r["id"],
                                             hp=(r["body"] or {}).get("hp"), index=i, of=len(pre))
                           for i, r in enumerate(pre)]
                if argmax(shammed) != base:
                    moved[(k, scope)] += 1

    print(f"corpus                              : {len(frames)} replayable corrections")
    print(f"frames ranked under BOTH arms       : {scanned}")
    if errors:
        print(f"replay errors                       : {dict(errors)}")
    print()
    print("THE FLAT TIE POPULATION — the defect, before and after")
    print("  (a Flat Tie is identical VALUE, which is what falls to list order. The `shift` column"
          " is a SUB-population — see `_sham.tie_population`.)")
    for name in ("INT", "FRAC"):
        g, v, t = ties[name]
        vpct = f"{100 * v / g:.1f}%" if g else "n/a"
        tpct = f"{100 * t / g:.1f}%" if g else "n/a"
        print(f"  {name:<5} equal-prize groups {g:>4}   tied on VALUE {v:>4} ({vpct:>6})"
              f"   tied on shift {t:>4} ({tpct:>6})")
    print()
    print(f"sham band (FRAC's own max effect on `value`): {band:.6f}")
    print()
    b, a = counts["bench"], counts["all"]
    print(f"{'arm':<22} {'BENCH (real seam)':<22} all rows")
    for k, label in (("FRAC", "fractional clock"),) + SHAMS:
        bench = f"{moved[(k,'bench')]}/{b} ({100*moved[(k,'bench')]/b:.1f}%)" if b else "-"
        allr = f"{moved[(k,'all')]}/{a} ({100*moved[(k,'all')]/a:.1f}%)" if a else "-"
        print(f"{label:<22} {bench:<22} {allr}")
        if k == "FRAC":
            print(f"{'':-<22} {'':-<22} {'':-<18}")

    print()
    print(READING)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
