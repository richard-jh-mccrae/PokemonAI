"""The corpus-wide off-policy census — every non-MAIN context, not just ctx 7 (Issue #412).

    python tools/train/off_policy_census.py [--frames] [--ctx 15] [--review]

`--frames` names each candidate frame, so the reading can be checked rather than believed; `--review`
lays one out beside its predecessors' rulings, because the dependency test needs the predecessor's
card text read against the follow-up's prose. Every run prints the POSITIVE CONTROL.
"""
from __future__ import annotations

import argparse
import sys
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from train.blunder import off_policy as op                                        # noqa: E402
from train.blunder.store import load_corrections                                  # noqa: E402


def _context_name(ctx) -> str:
    """The engine's own name for a select context, or ``?``. Importing `cg.api` MAPS THE NATIVE LIBRARY
    — fine in a CLI, and the reason `gates.py` writes its constants literally instead."""
    try:
        from cg.api import SelectContext
        return SelectContext(ctx).name
    except Exception:
        return "?"


def _wrap(text: str, indent: int) -> str:
    return textwrap.fill(" ".join((text or "").split()), 100,
                         initial_indent=" " * indent, subsequent_indent=" " * indent)


def _print_control(corrections) -> bool:
    ctl = op.control(corrections)
    state = "HEALTHY" if ctl["healthy"] else "⚠️  BROKEN"
    print(f"positive control (ctx-7 scan): {ctl['flagged']}/{ctl['population']} flagged — {state}")
    if not ctl["healthy"]:
        print("  The scan fires on NOTHING in the population it was built for. Every number below is")
        print("  an artifact of a broken instrument, not a finding. Do not report it.")
    return ctl["healthy"]


def tally(corrections) -> int:
    rows = op.census(corrections)
    print(f"\n{'ctx':>4}  {'name':<22} {'n':>4} {'ruled':>6} {'cand':>5} "
          f"{'OFF':>5} {'UNRULED':>8} {'GRADE':>6}")
    print("-" * 68)
    total = {"n": 0, "ruled": 0, "candidates": 0, "off_policy": 0, "unruled": 0, "gradeable": 0}
    for ctx in sorted(rows, key=lambda k: -rows[k]["n"]):
        r = rows[ctx]
        for k in total:
            total[k] += r[k]
        print(f"{ctx:>4}  {_context_name(ctx):<22} {r['n']:>4} {r['ruled']:>6} "
              f"{r['candidates']:>5} {r['off_policy']:>5} {r['unruled']:>8} {r['gradeable']:>6}")
    print("-" * 68)
    print(f"{'':>4}  {'ALL NON-MAIN':<22} {total['n']:>4} {total['ruled']:>6} "
          f"{total['candidates']:>5} {total['off_policy']:>5} {total['unruled']:>8} "
          f"{total['gradeable']:>6}")
    print("\nUNRULED = the scan found an earlier ruled decision in this turn and NOBODY has ruled")
    print("whether it actually invalidates this frame. Reported, never filtered — see")
    print("`train/blunder/off_policy.py`. Run with --review to rule them.")
    return 0


def frames(corrections, ctx_filter) -> int:
    rows = op.census(corrections)
    for ctx in sorted(rows):
        if ctx_filter is not None and ctx != ctx_filter:
            continue
        r = rows[ctx]
        print(f"\n=== ctx {ctx} {_context_name(ctx)} ({r['n']} frames) ===")
        for key, verdict, found in sorted(r["frames"], key=lambda x: tuple(str(p) for p in x[0])):
            agent, episode, frame = key
            if verdict == op.GRADEABLE and not found:
                continue
            print(f"  {verdict:<10} {agent} {episode}-{frame}")
            for cand in found:
                print(f"      candidate {cand.describe()}")
    return 0


def review(corrections, ctx_filter) -> int:
    """The review packet: every UNRULED candidate frame beside the predecessors that flagged it."""
    by_ep = op.episode_index(corrections)
    by_frame = {op.ruling_key(c): c for c in corrections}
    pending = [c for c in corrections
               if op.is_follow_up(c) and op.classify(c, by_ep) == op.UNRULED
               and (ctx_filter is None or op.select_context(c) == ctx_filter)]
    if not pending:
        print("\nno UNRULED candidates — every flagged follow-up frame carries a ruling.")
        return 0
    print(f"\n{len(pending)} UNRULED candidate frame(s). For each: would the ruled-CORRECT")
    print("predecessor play have PREVENTED this select, or CHANGED a board fact this ruling names?")
    for c in sorted(pending, key=lambda x: (op.select_context(x), x.agent, str(x.episode_id),
                                            (x.decision or {}).get("frame") or -1)):
        ctx = op.select_context(c)
        agent, episode, frame = op.ruling_key(c)
        print(f"\n{'=' * 100}")
        print(f"ctx{ctx} {_context_name(ctx)}  {agent} {episode}-{frame}  "
              f"turn={(c.decision or {}).get('turn')}  [{c.category}]")
        print(f"  FOLLOW-UP  chosen={list(c.chosen)} -> correct={list(c.correct)} "
              f"({c.correct_label!r})")
        print(_wrap(c.rationale or "(no rationale)", 4))
        for cand in op.candidates(c, by_ep):
            p = by_frame.get((agent, episode, cand.frame))
            print(f"  PREDECESSOR f{cand.frame} ctx{cand.context} {_context_name(cand.context)} "
                  f"[{cand.category}]")
            print(f"      PLAYED : {cand.played!r}")
            print(f"      SHOULD : {cand.should!r}")
            print(_wrap(p.rationale if p else "", 8))
    return 0


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", default=str(REPO / "data" / "corrections"))
    ap.add_argument("--frames", action="store_true", help="name every candidate frame")
    ap.add_argument("--review", action="store_true", help="the review packet for UNRULED candidates")
    ap.add_argument("--ctx", type=int, default=None, help="restrict to one select context")
    args = ap.parse_args(argv)

    corrections = load_corrections(args.store)
    print(f"corpus: {len(corrections)} corrections from {args.store}")
    _print_control(corrections)
    if args.review:
        return review(corrections, args.ctx)
    if args.frames:
        return frames(corrections, args.ctx)
    return tally(corrections)


if __name__ == "__main__":
    raise SystemExit(main())
