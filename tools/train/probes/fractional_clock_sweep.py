"""Fractional-clock discrimination sweep. **Not a gate.**

Answers the one question ADR-TEMP-398 owes its own change: does reading `turns_to_ko_me`'s crossing
point fractionally recover REAL discrimination in the opponent-target ranking, or does it merely
break Flat Ties the way any number of that size would?

The bar is ADR-TEMP-398's sham policy, and it applies to this change exactly as it applied to the
denial credit that change replaced: **a movement number published without its sham baseline is not
evidence.** So every arm here is reported against a band-matched meaningless leg.

## Arms

    INT    the pre-ADR-TEMP-398 ranking — `SurvivalClock.exact` collapsed back to `.turns`.
           Reconstructed by patching the model route for the duration of the frame, so it is the
           shipped code path answering the OLD question, not a hand-rebuilt imitation of it.
    FRAC   the ranking as it now ships.
    S_cid  sham — (cid % 7), band-matched to FRAC's own measured effect on `value`. No causal claim.
    S_hp   sham — (hp % 70), same band. No causal claim.
    S_pos  sham — position index. The degenerate case: a leg that cannot beat LIST ORDER is not
           ordering anything, and list order is precisely what a Flat Tie falls back to.

Both control kinds are required and are not interchangeable (ADR-TEMP-398): the shams prove
movement is attributable, and the tie-population rows prove WHY the floor is as high as it is.

Scoped BENCH-ONLY by default because that is the seam `gust_target_slot` actually reads — the
opponent's Active is never a legal gust target, and ranking Active+Bench together lets the Active
dominate the argmax. `all` is printed beside it for continuity with
`opponent_target_credit_sweep.py`, whose headline was wrong for exactly that reason.

    python tools/train/probes/fractional_clock_sweep.py

Reads what SHIPS: a fresh stateful Pilot per frame, deployment profile untouched. Offline,
read-only, always exits 0.
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from train.probes._corpus import replay_agent                  # noqa: E402
from train.probes._sham import READING, SHAMS, argmax, legs    # noqa: E402  THE sham vocabulary
from train.gates import keyed_corrections                      # noqa: E402
from common.state_model import TheirSide                       # noqa: E402
from common.strategy.combat import SurvivalClock               # noqa: E402


def _tune():
    spec = importlib.util.spec_from_file_location("tune_mod", REPO / "tools" / "train" / "tune.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _IntegerClock:
    """Collapses ``SurvivalClock.exact`` back onto ``.turns`` for the duration of a block.

    Patches the MODEL route rather than reimplementing the pre-change arithmetic, because a
    hand-rebuilt "what it used to do" is exactly the kind of second oracle ADR-TEMP-398 exists to
    avoid — it would drift from the real prior behaviour and nothing would report it."""

    _real = None

    def __enter__(self):
        if _IntegerClock._real is not None:
            raise RuntimeError("_IntegerClock is not re-entrant — a nested enter would capture the "
                               "PATCHED function as the real one and never restore it")
        _IntegerClock._real = real = TheirSide.survival_clock

        def integer_only(side, *a, **kw):
            # `*a` rather than a named `my_body`: the shipped signature takes it positionally OR by
            # keyword, and a wrapper that narrows that is a wrapper that changes behaviour.
            clock = real(side, *a, **kw)
            return SurvivalClock(clock.turns, float(clock.turns))

        TheirSide.survival_clock = integer_only
        return self

    def __exit__(self, *exc):
        TheirSide.survival_clock = _IntegerClock._real
        _IntegerClock._real = None
        return False                      # never swallow — restore, then let the frame's try see it


def _subset(rows, scope: str):
    return rows if scope == "all" else [r for r in rows if r["area"] == "bench" and r["value"] > 0]


def _tied(rows) -> tuple[int, int, int]:
    """``(equal-prize groups, tied on VALUE, tied on survival_shift)`` — the Flat Tie population.

    **The first count is the Flat Tie; the second is a sub-population of it.** A Flat Tie is defined
    by identical `value`, because `value` is what the ranking sorts on and therefore what falls
    through to list order. Ties on `survival_shift` are strictly FEWER: equal prize plus equal shift
    forces equal value, but the converse fails — `needs.opponent_target_value` floors the shift at
    `max(0.0, shift)`, so two rows with DIFFERENT negative shifts collapse to the same value, and at
    `phase == 0` the survival term vanishes entirely and every equal-prize row ties whatever its
    shift.

    Reporting only the shift count was this probe's own error, and it biased BOTH directions at
    once: it understated the defect (fewer ties seen than exist) and overstated the fix (recovery
    measured against the wrong denominator). Both are printed now so the gap between them stays
    visible rather than having to be rediscovered."""
    by_prize: dict = {}
    for r in rows:
        by_prize.setdefault(r["prize"], []).append(r)
    groups = [g for g in by_prize.values() if len(g) >= 2]
    return (len(groups),
            sum(1 for g in groups if len({float(r["value"]) for r in g}) == 1),
            sum(1 for g in groups if len({float(r["survival_shift"]) for r in g}) == 1))


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
            # A FRESH stateful Pilot per arm (the `snipe_decider_sweep` discipline): the two arms
            # must not share a per-decision memo or any board cache, or the second would answer with
            # the first's numbers and the comparison would silently be a null control.
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
            for i, n in enumerate(_tied(res[1])):
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
            pre, post = _subset(before, scope), _subset(after, scope)
            if len(pre) < 2:
                continue
            counts[scope] += 1
            base = argmax([r["value"] for r in pre])
            if argmax([r["value"] for r in post]) != base:
                moved[("FRAC", scope)] += 1
            for k, _label in SHAMS:
                # `opponent_target_value` is LINEAR in `prize_advance`, so adding the sham leg to the
                # finished value is exactly adding it to that term — one fewer re-derivation to get
                # wrong, and it keeps the arms differing only by the leg under test.
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
          " is a SUB-population — see `_tied`.)")
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
