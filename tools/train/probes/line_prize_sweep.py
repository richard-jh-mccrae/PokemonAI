"""Line-prize denial sweep (ADR-0119). **Not a gate.**

Does pricing `prize_advance` as the LINE's prize recover real discrimination, or does it merely break
Flat Ties? OWN is the pre-ADR-0119 reading, by patching the shipped route; the sham arms are
ADR-0118's mandatory null, sparsity-matched because this leg perturbs under a third of the rows.

**The pre-registration stands rather than being edited into agreement with the result**: it predicted
the leg would clear its shams, and it did not. What justifies the change is the TIE POPULATION and
the authored constants it deletes, not discrimination. Read the two halves separately.
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



class _OwnPrizeOnly(ArmPatch):
    """Collapses `forward_line_prize` onto the body's OWN prize — the pre-ADR-0119 reading. ``(0, 0)``
    makes it EXACT: `needs.line_prize_advance` floors at ``own_prize``, which is what shipped before."""

    target, name = TheirSide, "forward_line_prize"

    @classmethod
    def collapse(cls, value):
        return (0, 0)




def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--band", type=float, default=0.0,
                    help="override the sham band (default: LINE's own measured max effect)")
    args = ap.parse_args(argv)
    tune = _tune()
    frames = sorted(keyed_corrections(REPO / "data" / "corrections",
                                      predicate=lambda c: bool(c.obs and c.agent)))

    captured, errors, scanned = [], Counter(), 0
    ties = {"OWN": [0, 0, 0], "LINE": [0, 0, 0]}
    band, lines_seen, bodies_seen = 0.0, 0, 0
    for key, rec in frames:
        try:
            obs = rec.obs
            # A FRESH stateful Pilot per arm: the two must not share a per-decision memo or board
            # cache, or the second would answer with the first's numbers and prove nothing.
            with _OwnPrizeOnly():
                p_own = tune._build_pilot(replay_agent(rec))[0]
                before = p_own._opponent_target_rows(obs, p_own._board(obs, obs.get("select") or {}))
            p_line = tune._build_pilot(replay_agent(rec))[0]
            after = p_line._opponent_target_rows(obs, p_line._board(obs, obs.get("select") or {}))
        except Exception as e:
            errors[type(e).__name__] += 1
            continue
        if not (before and after and before[1] and after[1]):
            continue
        scanned += 1
        for name, res in (("OWN", before), ("LINE", after)):
            for i, n in enumerate(tie_population(res[1])):
                ties[name][i] += n
        # HOW MANY BODIES THE LEG CAN EVEN SPEAK ABOUT. A movement number is uninterpretable without
        # it: if most opponent bodies are dead-end lines, a leg that moves little has not failed.
        for r in after[1]:
            bodies_seen += 1
            lines_seen += 1 if float(r["prize_advance"]) > float(r["prize"]) else 0
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
                moved[("LINE", scope)] += 1
            # WHICH rows the real leg lifted. A band-matched sham perturbs EVERY row while this leg
            # perturbs under a third, so band-alone matching pits a sparse leg against a dense one.
            lifted = [abs(a["value"] - b["value"]) > 1e-12 for a, b in zip(post, pre)]
            for k, _label in SHAMS:
                # `opponent_target_value` is LINEAR in `prize_advance`, so adding the sham leg to the
                # finished value is exactly adding it to that term.
                shammed = [r["value"] + legs(k, band=band, card_id=r["id"],
                                             hp=(r["body"] or {}).get("hp"), index=i, of=len(pre))
                           for i, r in enumerate(pre)]
                if argmax(shammed) != base:
                    moved[(k, scope)] += 1
                # ...and the same sham confined to the rows the real leg lifted: same band, same COUNT
                # of perturbed rows, meaningless CHOICE within them. The honest control.
                masked = [r["value"] + (legs(k, band=band, card_id=r["id"],
                                             hp=(r["body"] or {}).get("hp"), index=i, of=len(pre))
                                        if lifted[i] else 0.0)
                          for i, r in enumerate(pre)]
                if argmax(masked) != base:
                    moved[(k + "_spr", scope)] += 1

    print(f"corpus                              : {len(frames)} replayable corrections")
    print(f"frames ranked under BOTH arms       : {scanned}")
    if errors:
        print(f"replay errors                       : {dict(errors)}")
    print()
    pct = f"{100 * lines_seen / bodies_seen:.1f}%" if bodies_seen else "n/a"
    print("WHAT THE LEG CAN SPEAK ABOUT (a movement number is uninterpretable without it)")
    print(f"  opponent bodies ranked            : {bodies_seen}")
    print(f"  ...whose LINE is worth more       : {lines_seen}  ({pct})  <- the rest are dead ends")
    print()
    print("THE FLAT TIE POPULATION — before and after")
    print("  (a Flat Tie is identical VALUE, which is what falls to list order. The `shift` column"
          " is a SUB-population — see `_sham.tie_population`.)")
    for name in ("OWN", "LINE"):
        g, v, t = ties[name]
        vpct = f"{100 * v / g:.1f}%" if g else "n/a"
        tpct = f"{100 * t / g:.1f}%" if g else "n/a"
        print(f"  {name:<5} equal-prize groups {g:>4}   tied on VALUE {v:>4} ({vpct:>6})"
              f"   tied on shift {t:>4} ({tpct:>6})")
    print()
    print(f"sham band (LINE's own max effect on `value`): {band:.6f}")
    print()
    b, a = counts["bench"], counts["all"]
    arms = ((("LINE", "line prize"),)
            + tuple((k + "_spr", label + " [sparsity]") for k, label in SHAMS)
            + SHAMS)
    print(f"{'arm':<28} {'BENCH (real seam)':<22} all rows")
    for k, label in arms:
        bench = f"{moved[(k,'bench')]}/{b} ({100*moved[(k,'bench')]/b:.1f}%)" if b else "-"
        allr = f"{moved[(k,'all')]}/{a} ({100*moved[(k,'all')]/a:.1f}%)" if a else "-"
        print(f"{label:<28} {bench:<22} {allr}")
        if k == "LINE":
            print(f"  [sparsity] = same band AND same rows perturbed as the real leg — the matched "
                  f"control.\n  The unmasked shams below perturb EVERY row and are reported for "
                  f"continuity, not as the bar.")
            print(f"{'':-<28} {'':-<22} {'':-<18}")

    print()
    print(READING)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
