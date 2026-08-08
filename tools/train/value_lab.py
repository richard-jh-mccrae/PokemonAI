"""Value lab — score every replayable corpus frame with **`state_value`** and dump the per-term
workings (POC-T3 / Issue #262, ADR-0092 §4-T3).

Two jobs: COVERAGE (every replayable frame scores without raising — a raise under 1-ply ordering is a
forfeited grader match) and WORKINGS (a flip is unrulable without the per-term decomposition).

    python tools/train/value_lab.py                        # score the corpus, report coverage
    python tools/train/value_lab.py --agent dragapult_ex
    python tools/train/value_lab.py --frame 82756664-97    # one frame's full workings
    python tools/train/value_lab.py --top development      # the boards one term is carrying
    python tools/train/value_lab.py --menu                 # menu-size distribution + derived P95
    python tools/train/value_lab.py --out reports/value.json

NOT a gate: it reports what the scalar says, and a metric nobody has ruled on must not fail `main`.
The derived per-decision figure is a LOWER BOUND — see :data:`APPLY_SEAM_UNMEASURED`.
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

#: In the ARTIFACT, not only here: a consumer reading `per_decision_p95_ms` off the JSON must meet
#: the omission there rather than come back to this module to learn half the cost is missing.
APPLY_SEAM_UNMEASURED = (
    "`apply_option` raised NotImplementedError for every MODELLED fate when this lab was written "
    "(POC-T0's frozen contract); it has been implemented since Issue #382, so the transition half "
    "cost cannot be measured BEFORE the issue that needs it. This figure counts leaf evaluations "
    "only and is a LOWER BOUND."
)


def menu_profile(correction) -> dict:
    """WIDTH, never wall-clock. The ADR-0091 collapse is ASKED, never re-derived, and `unclassified`
    gets its OWN bucket: folding it into `refused` reports a seam verdict the seam never gave."""
    from common.apply_option import ENGINE_RESOLVED, MODELLED, REFUSED, fate, is_terminal
    from common.option_equivalence import class_representatives, option_equivalence

    #: Keyed by the constant `fate` returns and compared by EQUALITY: a substring test would bin any
    #: future fate whose name happens to contain those letters, and the seam owns this vocabulary.
    buckets = {MODELLED: "modelled", ENGINE_RESOLVED: "engine", REFUSED: "refused"}

    obs = correction.obs or {}
    options = (obs.get("select") or {}).get("option") or []
    row = {"key": frame_key(correction), "agent": getattr(correction, "agent", None),
           "menu": len(options), "post_oec": 0,
           "terminal": 0, "modelled": 0, "refused": 0, "engine": 0, "unclassified": 0}
    row["post_oec"] = len(class_representatives(option_equivalence(options, obs), len(options)))
    for option in options:
        try:
            if is_terminal(option):
                row["terminal"] += 1
                continue
            resolved = fate(option)
        except Exception:                    # noqa: BLE001 — reported, never dropped and never
            row["unclassified"] += 1         # laundered into a seam verdict the seam did not give
            continue
        row[buckets.get(resolved, "unclassified")] += 1
    return row


def _percentile(values: list, q: float):
    """THE order-statistic rule here — a product of two percentile conventions is not a percentile.
    `median_ms` is the ONE field that does not use it, and the two differ by one element."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, int(q * len(ordered)) - 1)]


def menu_report(rows: list, *, leaf_p95_ms: float | None) -> dict:
    """Tail x tail: P95 menu against P95 leaf, never either mean. The product OVER-states the joint
    P95 deliberately — an optimistic budget fails on the grader, a pessimistic one just searches less."""
    post = [r["post_oec"] for r in rows]
    p95 = _percentile(post, 0.95)
    return {
        "frames": len(rows),
        "menu_p50": _percentile([r["menu"] for r in rows], 0.50),
        "menu_p95": _percentile([r["menu"] for r in rows], 0.95),
        "post_oec_p50": _percentile(post, 0.50),
        "post_oec_p95": p95,
        "post_oec_max": max(post) if post else None,
        "collapsed_options": sum(r["menu"] - r["post_oec"] for r in rows),
        "fate_totals": {k: sum(r.get(k, 0) for r in rows)
                        for k in ("terminal", "modelled", "refused", "engine", "unclassified")},
        "per_decision_p95_ms": (round(p95 * leaf_p95_ms, 2)
                                if p95 is not None and leaf_p95_ms is not None else None),
        "per_decision_p95_ms_is_lower_bound": True,
        "apply_option_ms": None,
        "apply_option_note": APPLY_SEAM_UNMEASURED,
        "widest": sorted(rows, key=lambda r: -r["post_oec"])[:10],
    }


def score_frame(pilot, correction) -> dict:
    """Builds through `pilot._leaf_state_model`, the SAME seam the planner leaf uses; a harness with
    its own model measures a board the agent never scores. A failure is CAPTURED, never raised."""
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
    """P95 beside the median because a beam is sized against the TAIL: the composer calls this once
    per candidate per decision, and the median hides what a wide menu costs the 2-vCPU grader."""
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
            "p95_ms": _percentile(times, 0.95),
            # The WORST single leaf, beside the tail: a P95 cannot be read back into a max, and the
            # two diverge on a long-tailed corpus.
            "max_ms": max(times) if times else None,
            "term_means": {name: (statistics.mean([r["working"][name] for r in scored])
                                  if scored else None) for name in FAMILIES},
            "rows": rows}


def _print_menu(menu: dict) -> None:
    """A DISTRIBUTION, never a mean: a single averaged number is one nobody can size a beam against."""
    print(f"\n=== menu width over {menu['frames']} frames "
          "(the multiplier from leaf UNIT cost to per-DECISION cost) ===")
    print(f"  raw menu      P50 {menu['menu_p50']}  P95 {menu['menu_p95']}")
    print(f"  post-OEC      P50 {menu['post_oec_p50']}  P95 {menu['post_oec_p95']}"
          f"  max {menu['post_oec_max']}"
          f"   ({menu['collapsed_options']} options collapsed by ADR-0091)")
    totals = menu["fate_totals"]
    print(f"  fate split    modelled {totals['modelled']}  terminal {totals['terminal']}"
          f"  refused {totals['refused']}  engine {totals['engine']}"
          # Printed even at 0, and named separately from `refused`: a non-zero here is the
          # instrument failing to classify, not the seam declining to model.
          f"  unclassified {totals['unclassified']}")
    if menu["per_decision_p95_ms"] is not None:
        print(f"\n  derived per-decision P95: {menu['per_decision_p95_ms']:.1f} ms"
              "   <- LOWER BOUND, leaf evaluations only")
    print(f"  {menu['apply_option_note']}")
    print("\n  widest decisions (named, not counted — a beam is sized against these):")
    for r in menu["widest"][:10]:
        print(f"    {r['key']:<28} post-OEC {r['post_oec']:>3} of {r['menu']:>3}")


def _print_report(rpt, *, top_term=None, frame=None) -> None:
    print(f"\n=== value lab: {rpt['n']} frames "
          f"({rpt['scored']} scored, {rpt['failed']} FAILED, {rpt['skipped_agent']} agent-skip) ===")
    if rpt["median_ms"] is not None:
        print(f"state_value cost: median {rpt['median_ms']:.2f} ms | P95 {rpt['p95_ms']:.2f} ms"
              f" | max {rpt['max_ms']:.2f} ms"
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
        hit = [r for r in rpt["rows"] if frame in (r["key"] or "")]
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
    ap.add_argument("--menu", action="store_true",
                    help="also report the post-OEC menu-width distribution and the DERIVED "
                         "per-decision P95 (a lower bound — see the module docstring)")
    ap.add_argument("--out", type=Path, default=None, help="write the report as JSON")
    args = ap.parse_args(argv)

    from train.blunder.store import DEFAULT_ROOT, load_corrections
    from train.leaf_lab import _cgpy_pilot_builder, _git_rev

    corrs = load_corrections(args.store or DEFAULT_ROOT)
    if args.agent:
        corrs = [c for c in corrs if c.agent == args.agent]
    rpt = value_lab_report(_cgpy_pilot_builder(), corrs)
    _print_report(rpt, top_term=args.top, frame=args.frame)

    menu = None
    if args.menu:
        menu = menu_report([menu_profile(c) for c in corrs if (getattr(c, "obs", None) or {})],
                           leaf_p95_ms=rpt["p95_ms"])
        _print_menu(menu)

    if args.out:
        from train.gates import write_json_artifact
        write_json_artifact(args.out, {"git_rev": _git_rev(), "agent": args.agent,
                                       "menu": menu, **rpt})
        print(f"-> {args.out}")
    # 0 even with failures: this REPORTS, it does not gate (see the module docstring). A non-zero
    # exit here would make it a gate nobody ruled on, which is the vacuous-gate failure one lab over.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
