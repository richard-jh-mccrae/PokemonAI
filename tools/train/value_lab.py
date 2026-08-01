"""Value lab — score every replayable corpus frame with **`state_value`** and dump the per-term
workings (POC-T3 / Issue #262, ADR-0092 §4-T3).

Two jobs, and they are different jobs.

**The coverage job.** T3's first acceptance line is *"`state_value` scores every replayable corpus
frame without error"*. A scalar that raises on 3% of real boards is not a scalar; and because
`state_value` is called once per candidate option per decision under Issue #263's 1-ply ordering, a
raise there is a forfeited grader match rather than a logged warning. So this walks the whole
committed corpus and reports the failures with their frame keys, never a bare count.

**The workings job.** Every term emits a `working` breakdown, and this is what consumes it. The
wave-3 ruling packet asks the user to rule flips frame by frame, and *"the leaf now prefers option 2"*
is unrulable without *"because `survival` moved 0.7 and `development` moved −0.1"*. `--frame` prints
one frame's full decomposition; `--top` ranks the corpus by whichever term you name, which is how you
find the boards a term is carrying.

    python tools/train/value_lab.py                        # score the corpus, report coverage
    python tools/train/value_lab.py --agent dragapult_ex
    python tools/train/value_lab.py --frame 82756664-97    # one frame's full workings
    python tools/train/value_lab.py --top development      # the boards one term is carrying
    python tools/train/value_lab.py --out reports/value.json

**Not a gate, and deliberately so.** The Discrimination Gate (`leaf_lab.py`) and the Decision Gate
(`decider_lab.py`) grade DECISIONS against human rulings; this grades nothing. It reports what the
scalar says. A metric nobody has ruled on must not start failing `main` — the doctrine `gates.py`
already carries — and there is no ruling anywhere on what `development` ought to read on frame 97.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from common.state_value import FAMILIES, state_value            # noqa: E402


def score_frame(pilot, correction) -> dict:
    """Score ONE corpus frame's board, with its per-term workings and the wall-clock it cost.

    Builds the model through `pilot._leaf_state_model` — the SAME seam the planner leaf uses — rather
    than assembling one here. A harness that built its own model would be measuring a board the agent
    never scores, which is the instrument/rung drift the decider sweeps rotted from.

    A failure is CAPTURED, never raised: the coverage job is to report which frames fail and why, and
    a harness that stops at the first one answers "is there a failure" instead of "how many, and
    where". ``error`` is the exception's type and message; `value` and `working` are then None.
    """
    obs = correction.obs or {}
    my_index = ((obs.get("current") or {}).get("yourIndex")) or 0
    row = {"key": frame_key(correction), "agent": getattr(correction, "agent", None),
           "episode_id": getattr(correction, "episode_id", None),
           "value": None, "working": None, "ms": None, "error": None}
    try:
        t0 = time.perf_counter()
        model = pilot._leaf_state_model(obs, my_index)
        working: dict = {}
        row["value"] = float(state_value(model, working=working))
        row["ms"] = (time.perf_counter() - t0) * 1000.0
        row["working"] = {k: round(v, 6) for k, v in working.items()}
    except Exception as exc:                     # noqa: BLE001 — the finding IS the exception
        row["error"] = f"{type(exc).__name__}: {exc}"
    return row


def frame_key(correction) -> str:
    """The Correction's own `identity_key`, via `gates.correction_frame_key` — ONE derivation, so a
    frame carries the same name here that it carries in both gates (ADR-0087 decision 2)."""
    from train.gates import correction_frame_key
    return correction_frame_key(correction)


def value_lab_report(pilot_for, corrections) -> dict:
    """Aggregate over the corpus. `pilot_for(agent)` builds/returns the Pilot for an agent.

    Reports the P95 alongside the median because that is the number Issue #263 has to size its beam
    against: the composer calls this once per candidate option per decision, so the tail is what
    decides whether a wide menu fits the 2-vCPU grader budget, and the median hides it."""
    rows, skipped = [], 0
    for c in corrections:
        if not (getattr(c, "obs", None) or {}):
            continue
        pilot = pilot_for(getattr(c, "agent", None))
        if pilot is None:
            skipped += 1
            continue
        rows.append(score_frame(pilot, c))
    scored = [r for r in rows if r["error"] is None]
    failed = [r for r in rows if r["error"] is not None]
    times = sorted(r["ms"] for r in scored)
    return {"n": len(rows), "scored": len(scored), "failed": len(failed),
            "skipped_agent": skipped,
            "median_ms": statistics.median(times) if times else None,
            "p95_ms": times[max(0, int(0.95 * len(times)) - 1)] if times else None,
            "term_means": {name: (statistics.mean([r["working"][name] for r in scored])
                                  if scored else None) for name in FAMILIES},
            "rows": rows}


def _print_report(rpt, *, top_term=None, frame=None) -> None:
    print(f"\n=== value lab: {rpt['n']} frames "
          f"({rpt['scored']} scored, {rpt['failed']} FAILED, {rpt['skipped_agent']} agent-skip) ===")
    if rpt["median_ms"] is not None:
        print(f"state_value cost: median {rpt['median_ms']:.2f} ms | P95 {rpt['p95_ms']:.2f} ms"
              "   <- Issue #263 sizes its beam against the P95, not the median")
    if rpt["scored"]:
        print("\nmean contribution per term (the shape of the scalar over the whole corpus):")
        for name, mean in rpt["term_means"].items():
            print(f"    {name:<12} {mean:+.4f}")

    failed = [r for r in rpt["rows"] if r["error"]]
    if failed:
        # Named, never counted. "3 frames failed" is not actionable; a frame key is.
        print(f"\n  FAILED ({len(failed)}) — `state_value` must score every replayable frame:")
        for r in failed[:20]:
            print(f"    {r['key']:<28} {r['error']}")
        if len(failed) > 20:
            print(f"    ... and {len(failed) - 20} more")

    if frame:
        hit = [r for r in rpt["rows"] if r["key"].startswith(frame) or frame in (r["key"] or "")]
        if not hit:
            print(f"\n  (no frame matching {frame!r})")
        for r in hit:
            print(f"\n--- {r['key']} ({r['agent']}) ---")
            if r["error"]:
                print(f"    ERROR {r['error']}")
                continue
            print(f"    state_value = {r['value']:+.4f} prizes")
            for name, v in r["working"].items():
                print(f"      {name:<12} {v:+.4f}")

    if top_term:
        if top_term not in FAMILIES:
            print(f"\n  (unknown term {top_term!r} — the six are {', '.join(FAMILIES)})")
        else:
            ranked = sorted((r for r in rpt["rows"] if not r["error"]),
                            key=lambda r: -abs(r["working"][top_term]))
            print(f"\n  frames where `{top_term}` carries the most weight:")
            for r in ranked[:15]:
                print(f"    {r['key']:<28} {top_term}={r['working'][top_term]:+.4f}"
                      f"   total={r['value']:+.4f}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--store", type=Path, default=None,
                    help="corrections file or tree (default: the committed corpus)")
    ap.add_argument("--agent", default=None, help="only this agent's frames")
    ap.add_argument("--frame", default=None, help="print ONE frame's full per-term workings")
    ap.add_argument("--top", default=None, metavar="TERM",
                    help="rank the corpus by |contribution| of TERM")
    ap.add_argument("--out", type=Path, default=None, help="write the report as JSON")
    args = ap.parse_args(argv)

    from train.blunder.store import DEFAULT_ROOT, load_corrections
    from train.leaf_lab import _cgpy_pilot_builder, _git_rev

    corrs = load_corrections(args.store or DEFAULT_ROOT)
    if args.agent:
        corrs = [c for c in corrs if c.agent == args.agent]
    rpt = value_lab_report(_cgpy_pilot_builder(), corrs)
    _print_report(rpt, top_term=args.top, frame=args.frame)

    if args.out:
        from train.gates import write_json_artifact
        write_json_artifact(args.out, {"git_rev": _git_rev(), "agent": args.agent, **rpt})
        print(f"-> {args.out}")
    # 0 even with failures: this REPORTS, it does not gate (see the module docstring). A non-zero
    # exit here would make it a gate nobody ruled on, which is the vacuous-gate failure one lab over.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
