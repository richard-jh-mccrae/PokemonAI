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

**The menu job** (Issue #291's closeout, feeding Issue #263). The timing above is a LEAF UNIT COST —
one `state_value` call on one board — and Issue #263's acceptance is stated *per decision*. Under its
uniform 1-ply ordering a decision costs one leaf evaluation per surviving candidate, so the missing
factor is the post-Option-Equivalence menu size and the DISTRIBUTION is what matters: a mean-sized
decision is not what overruns a 2-vCPU budget.

    python tools/train/value_lab.py --menu               # the menu-size distribution + derived P95

`menu_profile` collapses each frame's menu through **`option_equivalence.class_representatives`**
(ADR-0091) rather than re-deriving the classes — a second definition of *"these are one decision"*
would drift from the composer this is sizing, silently, because each copy stays internally
consistent. It also splits the menu by apply-seam FATE, since a REFUSED option is a one-action
terminal candidate in Issue #263's design and does not cost a transition.

**What this deliberately does NOT report, and why that is the finding rather than a gap.** The other
half of a per-decision cost is the apply-seam transition, and it **cannot be timed at this commit**:
`apply_option` was POC-T0's frozen contract and raised `NotImplementedError` for every MODELLED fate
when this was written (1690 of 1690 over the committed corpus). It has been IMPLEMENTED since
POC-T4/1 (Issue #382) and now returns a StateModel or a `Refusal`, so the figure below is a
historical measurement, not the current state. Issue #263 built
that transition, so the seam its own budget depends on does not exist to be measured before it. The
derived per-decision figure is therefore a **LOWER BOUND**, carried in the artifact as
`per_decision_p95_ms_is_lower_bound` rather than as prose somewhere a consumer will not read.
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

#: Why the per-decision figure is a lower bound, in the artifact rather than only in the docstring.
#: A consumer reading `per_decision_p95_ms` off the JSON must meet the omission there, not have to
#: come back to this module to learn that half the cost is missing.
APPLY_SEAM_UNMEASURED = (
    "`apply_option` raised NotImplementedError for every MODELLED fate when this lab was written "
    "(POC-T0's frozen contract); it has been implemented since Issue #382, so the transition half "
    "cost cannot be measured BEFORE the issue that needs it. This figure counts leaf evaluations "
    "only and is a LOWER BOUND."
)


def menu_profile(correction) -> dict:
    """ONE frame's decision WIDTH — the menu, its ADR-0091 collapse, and the apply-seam fate split.

    Width, never wall-clock: this is the multiplier that turns :func:`score_frame`'s leaf unit cost
    into a per-decision one, and it is a property of the board rather than of the machine, so it is
    the half of Issue #263's budget that stays comparable across hardware.

    The collapse is `option_equivalence.class_representatives`' and is ASKED, never re-derived. Two
    implementations of *"these are one decision"* drift invisibly — the fingerprint module's own
    header makes the argument, and this instrument sizing a composer that uses the other copy is
    precisely the shape where the drift would not show up as a disagreement, only as a wrong number.

    `refused` options are counted and kept separate because Issue #263 makes a refusal a one-action
    terminal candidate: it is ranked, so it costs a leaf, but it is never transitioned through.

    An option the seam cannot classify at all lands in `unclassified` — its OWN bucket, never folded
    into `refused`. Both keep the WIDTH honest (nothing is dropped, so the multiplier stays right),
    but only the split keeps the FATE totals honest: `refused` is a seam verdict Issue #263 acts on,
    and silently swelling it with instrument failures would report coverage the seam never gave.
    Same doctrine as :func:`score_frame` one function down — the finding IS the exception."""
    from common.apply_option import ENGINE_RESOLVED, MODELLED, REFUSED, fate, is_terminal
    from common.option_equivalence import class_representatives, option_equivalence

    #: The fates this instrument counts, keyed by the constant `fate` actually returns — compared by
    #: EQUALITY against the exported names, never by substring. `"refus" in resolved` would bin any
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
    """**The** order-statistic rule for this module — `p95_ms` and every menu figure call it.

    One spelling, because the derived per-decision figure MULTIPLIES the leaf tail by the menu tail,
    and a product of two hand-written percentile conventions is not a percentile of anything.

    ⚠️ `median_ms` is the ONE field that does not come from here: it is `statistics.median`, which
    averages the middle pair on an even-length corpus, so it can differ from `_percentile(x, 0.50)`
    by one element. That is deliberate — `median_ms` is a long-standing published field and silently
    changing what it means would be a data change wearing a refactor's clothes. `menu_p50` and
    `post_oec_p50` therefore use THIS rule, and the two are not interchangeable to a hair."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, int(q * len(ordered)) - 1)]


def menu_report(rows: list, *, leaf_p95_ms: float | None) -> dict:
    """Aggregate the widths and derive the per-decision P95 — **tail x tail, and a lower bound.**

    P95 menu against P95 leaf rather than either mean: a budget is overrun by its worst decisions,
    which is the same reason `value_lab_report` reports P95 beside the median at all. The product
    over-states the *joint* P95 (the two tails need not co-occur on one frame) and that direction is
    deliberate — a beam sized against an optimistic budget fails on the grader, where a beam sized
    against a pessimistic one merely searches less than it could.

    `widest` names the frames rather than counting them, the same discipline `_print_report` applies
    to failures: "the tail is 40 options" is not actionable, a frame key is."""
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
            # `_percentile`, not a second copy of its index arithmetic: the menu block multiplies
            # this figure by its own P95, and two hand-written spellings of one convention is the
            # drift that makes such a product meaningless. `median_ms` stays `statistics.median` —
            # it is the long-standing published field and moving it would be a silent data change.
            "p95_ms": _percentile(times, 0.95),
            # The WORST single leaf, beside the tail. P95 is what a beam is sized against; `max_ms`
            # is what one pathological board costs, and the two diverge on a long-tailed corpus —
            # Issue #291 §3a asks for both by name and a P95 alone cannot be read back into a max.
            "max_ms": max(times) if times else None,
            "term_means": {name: (statistics.mean([r["working"][name] for r in scored])
                                  if scored else None) for name in FAMILIES},
            "rows": rows}


def _print_menu(menu: dict) -> None:
    """The width distribution and what it derives — printed as a distribution, never as a mean.

    Issue #291 §3a asks for the distribution explicitly *"because the tail is the whole point"*, so a
    single averaged number here would answer a question nobody asked with a number nobody can size a
    beam against."""
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
