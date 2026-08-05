"""Line-prize denial sweep. **Not a gate.**

Answers what ADR-TEMP-398 owes its own change: does pricing `prize_advance` as the LINE's prize
recover real discrimination in the opponent-target ranking, or does it merely break Flat Ties the
way any number of that size would?

The bar is ADR-0118's sham policy — **a movement number published without its sham baseline is not
evidence** — and this probe exists partly because the previous change on this seam published one
that was not. It also fixes that measurement's OTHER error by default: the tie population is counted
on `value`, the field the ranking actually sorts on, with the `survival_shift` sub-population printed
beside it rather than in place of it (see `fractional_clock_sweep._tied`).

## Arms

    OWN    the pre-ADR-TEMP-398 ranking — `prize_advance` collapsed back to the body's OWN prize.
           Reconstructed by patching the shipped model route for the duration of the frame, so it
           is the real code path answering the OLD question rather than a hand-rebuilt imitation.
    LINE   the ranking as it now ships.
    S_cid  sham — (cid % 7), band-matched to LINE's own measured effect on `value`. No causal claim.
    S_hp   sham — (hp % 70), same band. No causal claim.
    S_pos  sham — position index. The degenerate case: a leg that cannot beat LIST ORDER is not
           ordering anything, and list order is precisely what a Flat Tie falls back to.

**This leg SHOULD clear its shams, and that expectation is worth stating before the run rather than
after.** The fractional clock did not, and correctly so — it declines to break a Structural Zero,
which is most of the population. This leg is different in kind: it separates bodies by a card fact
that varies across them (what their line becomes) rather than by a removal Δ that is zero for every
non-leading body. A LINE arm that merely matches `sham cid%7` would mean the corpus's opponent
benches are mostly dead-end lines, and that is a finding about the corpus, not a vindication.

    python tools/train/probes/line_prize_sweep.py

Reads what SHIPS: a fresh stateful Pilot per arm, deployment profile untouched. Offline, read-only,
always exits 0.
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


def _tune():
    spec = importlib.util.spec_from_file_location("tune_mod", REPO / "tools" / "train" / "tune.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _OwnPrizeOnly:
    """Collapses `forward_line_prize` onto the body's OWN prize for the duration of a block.

    Patches the MODEL route rather than reimplementing the pre-change arithmetic: a hand-rebuilt
    "what it used to do" is the second oracle ADR-0117 was written to avoid, and it would drift from
    the real prior behaviour with nothing reporting it. Returning ``(0, 0)`` is what makes this the
    OLD reading exactly — `needs.line_prize_advance` floors at `own_prize`, so a 0 best-line-prize
    yields the body's own value unchanged, which is precisely `prize_value`."""

    _real = None

    def __enter__(self):
        if _OwnPrizeOnly._real is not None:
            raise RuntimeError("_OwnPrizeOnly is not re-entrant — a nested enter would capture the "
                               "PATCHED function as the real one and never restore it")
        _OwnPrizeOnly._real = TheirSide.forward_line_prize
        TheirSide.forward_line_prize = lambda side, *a, **kw: (0, 0)
        return self

    def __exit__(self, *exc):
        TheirSide.forward_line_prize = _OwnPrizeOnly._real
        _OwnPrizeOnly._real = None
        return False                      # never swallow — restore, then let the frame's try see it


def _subset(rows, scope: str):
    return rows if scope == "all" else [r for r in rows if r["area"] == "bench" and r["value"] > 0]


def _tied(rows) -> tuple[int, int, int]:
    """``(equal-prize groups, tied on VALUE, tied on survival_shift)``.

    Grouped on the row's OWN `prize`, deliberately: that is the printed field an equal-prize group
    means, and grouping on the new `prize_advance` would make the leg look like it dissolved ties it
    had actually renamed. The first count is the Flat Tie — identical `value`, what falls through to
    list order. The `shift` column is the strict sub-population `fractional_clock_sweep` documents,
    printed so the gap between the two stays visible."""
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
            # A FRESH stateful Pilot per arm: the two must not share a per-decision memo or any
            # board cache, or the second would answer with the first's numbers and the comparison
            # would silently be a null control.
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
            for i, n in enumerate(_tied(res[1])):
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
            pre, post = _subset(before, scope), _subset(after, scope)
            if len(pre) < 2:
                continue
            counts[scope] += 1
            base = argmax([r["value"] for r in pre])
            if argmax([r["value"] for r in post]) != base:
                moved[("LINE", scope)] += 1
            # WHICH rows the real leg actually lifted. A band-matched sham perturbs EVERY row; this
            # leg perturbs under a third of them, because most opponent bodies are dead-end lines.
            # Matching on band alone therefore compares a sparse leg against a dense one and the
            # sham wins on volume — see the SPARSITY-MATCHED arm below, which is the honest control.
            lifted = [abs(a["value"] - b["value"]) > 1e-12 for a, b in zip(post, pre)]
            for k, _label in SHAMS:
                # `opponent_target_value` is LINEAR in `prize_advance`, so adding the sham leg to the
                # finished value is exactly adding it to that term.
                shammed = [r["value"] + legs(k, band=band, card_id=r["id"],
                                             hp=(r["body"] or {}).get("hp"), index=i, of=len(pre))
                           for i, r in enumerate(pre)]
                if argmax(shammed) != base:
                    moved[(k, scope)] += 1
                # ...and the same sham confined to the rows the real leg lifted: same band, same
                # COUNT of perturbed rows, meaningless CHOICE of magnitude within them. This is the
                # arm that isolates the only thing the leg claims — that WHICH bodies it lifts, and
                # by how much, tracks something real.
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
          " is a SUB-population — see `fractional_clock_sweep._tied`.)")
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
