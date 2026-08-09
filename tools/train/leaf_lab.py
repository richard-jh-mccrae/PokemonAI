"""Leaf lab — measure the SHIPPED end-of-turn LEAF against tagged corrections, and gate on it.

The scorer is `composer.compose`'s depth-0 1-ply differencing (Issue #386), not the retired engine
rollout: values are small `state_value` deltas, and only the RANKING is graded, so the scale change
moves no verdict. `data/leaf_lab/baseline.json` is a RULING RECORD and was NOT re-captured to match
the new scorer — that is how the old Decision Gate died. Every `OK -> MISS` is a flip to be ruled.

    python tools/train/leaf_lab.py [--agent dragapult_ex] [capture|restamp|diff ...]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from common import composer as cp                            # noqa: E402
from train.gates import CAPTURE_POINT, print_gate_report      # noqa: E402

_PLACEHOLDER_SBI = "leaf-lab-cgpy-reseed"   # any non-empty token passes `_simulate_line`'s gate; cgpy
                                            # then reconstructs the search state from the obs. Unused
                                            # here now; kept because `family_diag.py` imports it.

_EPS = 1e-9                                 # `class_asymmetry`'s "the leaf priced this ONE way" bar —
                                            # measured float non-associativity is 2.8e-14, the leaf's
                                            # own reporting granularity 1e-3. See that function.


def board_leaf_values(pilot, obs) -> list:
    """The SHIPPED leaf's value for taking EACH menu option first (index-aligned) — `composer.compose`'s
    own `fanned`, read off the shipped call. `None` = the seam REFUSED the option: unknown, not zero."""
    options = (obs.get("select") or {}).get("option") or []
    if not options:
        return []
    my_index = int((obs.get("current") or {}).get("yourIndex") or 0)
    try:
        model = pilot._leaf_state_model(obs, my_index)
        result = cp.compose(model, options, search_api=getattr(pilot, "_search_api", None))
    except Exception:
        return [None] * len(options)
    return list(result.fanned)


def frame_key(correction) -> str:
    """The Correction's ``identity_key`` flattened via `gates.correction_frame_key` — ONE name across both gates."""
    from train.gates import correction_frame_key
    return correction_frame_key(correction)


def evaluate_leaf_on_correction(pilot, correction) -> dict:
    """Score one correction's board and rank the human's `correct` pick under the leaf. Every verdict is
    computed on the CANONICALISED values (ADR-0091); the recorded `values` column stays RAW."""
    from common.option_equivalence import class_of, fan_out, option_equivalence

    obs = correction.obs or {}
    raw = board_leaf_values(pilot, obs)
    equiv = option_equivalence((obs.get("select") or {}).get("option") or [], obs)
    # TWO readings of one sim (ADR-0091): the finding is read off RAW — canonicalising first would
    # make `class_asymmetry` empty BY CONSTRUCTION — and every verdict off the fanned `values`.
    values = fan_out(raw, equiv)
    correct = list(correction.correct or [])
    scored = [v for v in values if v is not None]
    correct_vals = [values[i] for i in correct if 0 <= i < len(values) and values[i] is not None]
    base = {"key": frame_key(correction),
            "episode_id": getattr(correction, "episode_id", None),
            "agent": getattr(correction, "agent", None), "correct": correct,
            "values": raw,            # RAW stays the recorded column: it is the asymmetry's evidence
            "scored": len(scored), "n_options": len(values)}
    asymmetry = class_asymmetry(raw, equiv)
    if asymmetry:
        base["class_asymmetry"] = asymmetry
    if not scored or not correct_vals:
        return {**base, "unscorable": True, "correct_value": None, "top_value": None,
                "correct_is_top": None, "correct_is_unique_top": None, "correct_rank": None,
                "outscored_by": None, "top_tie": None}
    top = max(scored)
    best_correct = max(correct_vals)
    outscored = sum(1 for v in scored if v > best_correct)
    # Ties are counted over CLASSES, not raw options (ADR-0091): two options that are the same
    # decision tying is correct behaviour, and counting them apart aimed leaf work at a phantom.
    at_top = {i for i, v in enumerate(values) if v is not None and v == top}
    top_tie = len({min(class_of(equiv, i)) for i in at_top})
    is_top = best_correct >= top
    return {**base, "unscorable": False, "correct_value": best_correct, "top_value": top,
            "correct_is_top": is_top, "correct_is_unique_top": is_top and top_tie == 1,
            "correct_rank": outscored + 1, "outscored_by": outscored, "top_tie": top_tie}


def class_asymmetry(values, equiv) -> list:
    """Every **Option Equivalence Class** whose members do NOT all score the same (ADR-0091), worst
    spread first. Reported, never gating. ``_EPS`` is why "zero classes" is expressible at all."""
    from common.option_equivalence import classes

    out = []
    for members in classes(equiv):
        vals = [values[i] for i in members if i < len(values) and values[i] is not None]
        spread = (max(vals) - min(vals)) if vals else 0.0
        if spread > _EPS:
            out.append({"options": list(members), "spread": spread})
    return sorted(out, key=lambda f: -f["spread"])


def is_leaf_frame(c) -> bool:
    """A MAIN-select (context 0) board with a target the leaf can rank: a ``turn_plan`` correction, or
    any MAIN-select correction naming a ``correct``. MAIN is a SCOPE statement, not a substrate limit."""
    if getattr(c, "scope", None) == "match":
        return False
    obs = getattr(c, "obs", None)
    if not obs:
        return False
    if getattr(c, "turn_plan", None):
        return True
    return bool(getattr(c, "correct", None)) and (obs.get("select") or {}).get("context") == 0


def leaf_lab_report(pilot_for, corrections, *, voided=()) -> dict:
    """Aggregate the leaf verdict across a batch. A **Voided Ruling** frame is still scored and still
    carried in ``rows`` — marked ``voided`` and left out of the RATES only (ADR-0088 decision 4)."""
    voided = set(voided or ())
    rows, skipped = [], 0
    for c in corrections:
        if not is_leaf_frame(c):
            continue
        pilot = pilot_for(c.agent)
        if pilot is None:
            skipped += 1
            continue
        row = evaluate_leaf_on_correction(pilot, c)
        if row["key"] in voided:
            row["voided"] = True
        rows.append(row)
    scorable = [r for r in rows if not r["unscorable"]]
    gradeable = [r for r in scorable if not r.get("voided")]             # the honest denominator
    leaf_correct = [r for r in gradeable if r["correct_is_top"]]         # lenient: shared max counts
    leaf_strict = [r for r in gradeable if r["correct_is_unique_top"]]   # honest: SOLE max (rung's pick)
    return {"n": len(rows), "scorable": len(scorable), "unscorable": len(rows) - len(scorable),
            "skipped_agent": skipped,
            # Reported beside the rates, never in them and never in the verdict (decision 4).
            "class_asymmetry": sum(1 for r in rows if r.get("class_asymmetry")),
            "voided": len(scorable) - len(gradeable), "gradeable": len(gradeable),
            "leaf_correct": len(leaf_correct),
            "leaf_correct_rate": (len(leaf_correct) / len(gradeable)) if gradeable else None,
            "leaf_correct_strict": len(leaf_strict),
            "leaf_correct_strict_rate": (len(leaf_strict) / len(gradeable)) if gradeable else None,
            "avg_top_tie": (sum(r["top_tie"] for r in gradeable) / len(gradeable)) if gradeable else None,
            "rows": rows}


def _cgpy_pilot_builder(*, memoize=True):
    """A cgpy-wired `pilot_for(agent)`; callers can request fresh Pilots for live-path checks."""
    import importlib
    from cgpy.compat import api as cgpy_api
    tune = importlib.import_module("train.tune")
    cache: dict = {}

    def build(agent):
        if not memoize or agent not in cache:
            try:
                pilot, _ = tune._build_pilot(agent)
                pilot._search_api = cgpy_api      # the seam: re-score offline via cgpy, not native
                if memoize:
                    cache[agent] = pilot
                else:
                    return pilot
            except Exception as exc:              # noqa: BLE001 — an unbuildable agent is skipped, reported
                print(f"  (could not build {agent}: {type(exc).__name__}: {exc})")
                cache[agent] = None
        return cache[agent]
    return build


def _git_rev() -> str:
    """The build a capture was taken at, so a diff against the wrong baseline is detectable."""
    import subprocess
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, check=True,
                              capture_output=True, text=True,
                              encoding="utf-8").stdout.strip()
    except Exception:                       # noqa: BLE001 — provenance is best-effort, never fatal
        return "unknown"


def _build_report(store, agent, *, voided=()):
    from train.blunder.store import load_corrections
    corrs = [c for c in load_corrections(store) if is_leaf_frame(c)]
    if agent:
        corrs = [c for c in corrs if c.agent == agent]
    return leaf_lab_report(_cgpy_pilot_builder(), corrs, voided=voided)


def _print_report(rpt) -> None:
    # `gradeable` is absent from a capture taken before ADR-0088; fall back rather than crash, so a
    # diff against an older committed baseline still reads.
    gradeable = rpt.get("gradeable", rpt["scorable"])
    voided = rpt.get("voided", 0)
    print(f"\n=== leaf lab: {rpt['n']} leaf frames "
          f"({rpt['scorable']} scorable, {rpt['unscorable']} unscorable, {rpt['skipped_agent']} agent-skip"
          + (f", {voided} voided" if voided else "") + ") ===")
    strict, lenient = rpt["leaf_correct_strict_rate"], rpt["leaf_correct_rate"]
    tie = rpt["avg_top_tie"]

    def _pct(x):
        return f" ({x:.0%})" if x is not None else ""
    tie_s = f"{tie:.1f}" if tie is not None else "n/a"
    # HEADLINE = strict (the argmax rung would actually pick `correct`); shared-top (lenient) + tie for context
    print(f"leaf picks `correct` (SOLE top): {rpt['leaf_correct_strict']}/{gradeable}{_pct(strict)}"
          f"   | shared-top: {rpt['leaf_correct']}/{gradeable}{_pct(lenient)}"
          f"   | avg top-tie: {tie_s}")
    asym = [r for r in rpt["rows"] if r.get("class_asymmetry")]
    if asym:
        print(f"\n  CLASS ASYMMETRY ({len(asym)}) — the leaf prices ONE decision two ways; "
              f"reported, never gating (Issue #254):")
        for r in asym:
            for f in r["class_asymmetry"]:
                print(f"    {r['key']}  options {f['options']}  spread {f['spread']:.2f}")
        print("")
    for r in rpt["rows"]:
        if r["unscorable"]:
            print(f"  ep{r['episode_id']} correct={r['correct']}: UNSCORABLE ({r['scored']}/{r['n_options']} sim'd)")
        else:
            flag = "OK " if r["correct_is_top"] else "MISS"
            print(f"  ep{r['episode_id']} correct={r['correct']}: {flag} rank {r['correct_rank']}/{r['n_options']}"
                  f"  correct={r['correct_value']} top={r['top_value']} top_tie={r['top_tie']}")


def _print_diff(diff, held_out, before_meta, voided=None) -> None:
    """The Discrimination Gate's report. The aggregate metrics are printed for context and are
    deliberately absent from the verdict — over 1b they moved the GOOD way while six frames broke."""
    if diff["added"] or diff["removed"]:
        # Never silently tolerated: a shifted corpus means the two captures are not comparable, and a
        # diff that quietly skips frames reads green for the wrong reason.
        print(f"  CORPUS SHIFTED: +{len(diff['added'])} frame(s) added, "
              f"-{len(diff['removed'])} removed since the capture — re-capture the baseline.")
    for f in diff["miss_to_ok"]:
        print(f"  IMPROVED  {f['key']}  MISS -> OK")
    from train.gates import print_stale_baseline, split_excused
    # BEFORE the gate block: the verdict is the last thing printed, and everything that changes what
    # it MEANS comes ahead of it. These frames still print as `REGRESSED` — the label excuses nothing.
    print_stale_baseline(diff.get("stale_baseline") or [])
    voided = voided or {}
    gating, ruled, void_hits = split_excused(diff["ok_to_miss"], held_out, voided)
    print_gate_report(
        f"DISCRIMINATION GATE (ADR-0072) — {diff['compared']} frames compared "
        f"vs {before_meta.get('git_rev', '?')}",
        gating=gating, ruled=ruled, held_out=held_out, total=diff["compared"],
        rule="zero unruled OK->MISS",
        line=lambda f: (f"REGRESSED {f['key']}  OK -> MISS   "
                        f"rank {f['before'].get('correct_rank')} -> {f['after'].get('correct_rank')}"),
        voided=void_hits, voided_by=voided)


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="Measure the develop-rung leaf on tagged MAIN-select corrections")
    ap.add_argument("--agent", default=None, help="restrict to one agent (default: all)")
    ap.add_argument("--store", default=str(REPO / "data" / "corrections"))
    sub = ap.add_subparsers(dest="cmd")
    cap = sub.add_parser(
        "capture", help="write a baseline report artifact (the gate's reference)",
        # WHERE you capture from is checked by nothing, so the one unenforceable rule is the one
        # `--help` has to state (ADR-0110 decision 4).
        epilog=f"Capture point: {CAPTURE_POINT}. Capturing at HEAD bakes the change under test into "
               f"its own reference, and the gate can then never speak about that change again.")
    cap.add_argument("--out", type=Path, required=True)
    res = sub.add_parser("restamp", help="rewrite ONLY the recorded git_rev (a rebase moved the base)")
    res.add_argument("--baseline", type=Path, required=True)
    res.add_argument("--rev", default=None, help="the revision to stamp (default: this checkout's)")
    dif = sub.add_parser("diff", help="Discrimination Gate: diff this build against a capture")
    dif.add_argument("--baseline", type=Path, required=True)
    dif.add_argument("--out", type=Path, default=None,
                     help="write the gate verdict as JSON (machine-readable, for a phase checklist)")
    args = ap.parse_args(argv)

    # Read ONCE and threaded through both subcommands — the rulings are one corpus, not a property of
    # a capture, so a capture and the diff reading it must not resolve two different voided sets.
    from train.gates import orphan_rulings, restamp_artifact, ruling_index, voided_frames

    # A re-stamp never re-reads the build, so it runs BEFORE the corpus replay — that separation is
    # the point of the subcommand existing (ADR-0094 decision 2), not an optimisation.
    if args.cmd == "restamp":
        rev = args.rev or _git_rev()
        restamp_artifact(args.baseline, rev)
        print(f"-> re-stamped {args.baseline} to {rev} (verdicts untouched)")
        return 0

    index = ruling_index(args.store)
    voided = voided_frames(index)
    orphans = orphan_rulings(args.store)
    # The off-policy exposure (Issue #412), resolved here for the Ruling Index's reason: it is a
    # property of the CORPUS, not of a capture. Reported only — it reaches no verdict.
    from train.gates import off_policy_frames, print_off_policy_readout
    off_policy = off_policy_frames(args.store)
    rpt = _build_report(args.store, args.agent, voided=set(voided))

    if args.cmd == "capture":
        from train.gates import (_scorable, discrimination_fail_keys, guarded_capture,
                                 leaf_lab_diff, print_ruling_readout, rows_by_key,
                                 write_json_artifact)
        # A baseline is a RULING RECORD, so overwriting one is guarded, not free: a frame this build
        # degrades OK -> MISS may only become the new reference once a human has ruled it (ADR-0094).
        def _write():
            write_json_artifact(args.out, {"git_rev": _git_rev(), "agent": args.agent, **rpt})
            _print_report(rpt)
            print_ruling_readout(index, voided, orphans=orphans, detail=True)
            print_off_policy_readout(off_policy, present=rows_by_key(rpt, keep=_scorable))
            print(f"-> captured {rpt['scorable']} scorable frames at {_git_rev()} to {args.out}")

        return guarded_capture(
            args.out, rpt, index=index, write=_write,
            diff_fn=lambda before, after: leaf_lab_diff(before, after, voided=set(voided)),
            fail_keys_fn=discrimination_fail_keys)

    if args.cmd == "diff":
        from train.gates import (_scorable, discrimination_fail_keys, discrimination_gate_verdict,
                                 held_out_frames, leaf_lab_diff, print_agree_delta,
                                 print_ruling_moves, print_ruling_readout, rows_by_key,
                                 write_json_artifact)
        before = json.loads(args.baseline.read_text(encoding="utf-8"))
        diff = leaf_lab_diff(before, rpt, voided=set(voided))
        held_out = held_out_frames()
        passed = discrimination_gate_verdict(diff, held_out=held_out, voided=set(voided))
        _print_report(rpt)
        # Context BEFORE the verdict: `_print_diff` ends with the PASS/FAIL line, and a reader who
        # stops there must not have skipped the delta that explains the numbers above it.
        print_ruling_moves(diff["ruling_moves"])
        print_ruling_readout(index, voided, orphans=orphans)
        # `moved` is the fail direction only. An off-policy frame that improved needs no operator
        # action, so naming it here would dilute the one list that must not become scenery.
        print_off_policy_readout(off_policy, present=rows_by_key(rpt, keep=_scorable),
                                 moved=discrimination_fail_keys(diff))
        print_agree_delta(diff["agree_delta"])
        _print_diff(diff, held_out, before, voided)
        if args.out:                      # US6: the gate's verdict as a machine-readable artifact
            write_json_artifact(args.out, {
                "gate": "discrimination", "passed": passed, "git_rev": _git_rev(),
                "baseline_git_rev": before.get("git_rev"), "compared": diff["compared"],
                "ok_to_miss": [f["key"] for f in diff["ok_to_miss"]],
                # A SUBSET of `ok_to_miss` above, never a subtraction: these flips still gate, and a
                # consumer must tell a stale reference from a regressed build (ADR-0110 decision 2).
                "stale_baseline": [f["key"] for f in diff["stale_baseline"]],
                "miss_to_ok": [f["key"] for f in diff["miss_to_ok"]],
                "added": diff["added"], "removed": diff["removed"],
                "ruling_moves": diff["ruling_moves"],   # reported, never gating (ADR-0087 d7)
                "agree_delta": diff["agree_delta"],     # the aggregate half (ADR-0088 d7)
                # `{key: disposition}`, not a bare key list: a machine consumer must tell a
                # `transposition` exclusion from a `refuted` one without re-reading the ledger.
                "voided": {k: r.disposition for k, r in sorted(voided.items())},
                "orphan_rulings": [k for k, _e in orphans],
                "held_out": held_out})
            print(f"-> {args.out}")
        return 0 if passed else 1

    _print_report(rpt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
