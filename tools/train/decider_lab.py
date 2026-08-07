"""Decider lab — the **Decision Gate**, against a RECORDED baseline (ADR-0072 decision 2, as amended
by ADR-0085 Amendment I).

Replays every replayable Correction through a fresh shipped Pilot and diffs what the agent DECIDES
against a committed capture.

    python tools/train/decider_lab.py capture --out data/decider_lab/baseline.json
    python tools/train/decider_lab.py diff --baseline data/decider_lab/baseline.json
    python tools/train/decider_lab.py diff --baseline ... --context 15   # one phase's frames

"Agree" is `satisfies_human` (`correct ⊆ chosen`, ADR-0085 Amendment J) modulo the Option
Equivalence Class (ADR-0091); a Voided Ruling is out of the rate, so the denominator is `gradeable`,
not `labelled` (ADR-0088). Green means *nothing regressed*, NOT that the agent is right.

**The baseline is a RULING RECORD, never auto-recaptured**, or the gate becomes a mirror.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from train.gates import (REFUSED_SHAPE_RULES, classes_of, decider_lab_diff,  # noqa: E402
                         decision_gate_verdict, decision_fail_keys, equivalence_index,
                         guarded_capture, held_out_frames, keyed_corrections, off_policy_frames,
                         orphan_rulings, print_agree_delta, print_gate_report,
                         print_off_policy_readout, print_ruling_moves,
                         print_ruling_readout, records_a_decline_it_cannot_state, refused_shapes,
                         restamp_artifact, rows_by_key, ruling_index, satisfies_human,
                         split_excused, voided_frames, write_json_artifact)


def _git_rev() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO,
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return "unknown"


def _tune():
    spec = importlib.util.spec_from_file_location("tune_mod", REPO / "tools" / "train" / "tune.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _records(store: Path, agent: str | None):
    """`gates.keyed_corrections` is THE Corpus Reader (ADR-0087 decision 1); the predicate runs on
    the CONSTRUCTED record. Sorted by key so a capture's row order is stable across machines."""
    def keep(c):
        return getattr(c, "scope", None) != "match" and bool(c.obs and c.agent) and (
            not agent or c.agent == agent)

    return sorted(keyed_corrections(store, predicate=keep), key=lambda kc: kc[0])


def _portable_error(exc: Exception) -> str:
    """Repo-relative: an absolute path makes a Windows and a Linux capture of one verdict differ.
    Slashes normalise BEFORE the root is stripped — an exception's ``str`` is already repr-escaped."""
    text = f"{type(exc).__name__}: {exc}".replace("\\\\", "/").replace("\\", "/")
    root = str(REPO).replace("\\", "/")
    return text.replace(root + "/", "").replace(root, "")


def build_report(store, agent=None, *, voided=(), equiv=None) -> dict:
    """ONE Pilot per frame — it is stateful, so a shared one inherits the previous frame's board.
    Unreplayable and Voided frames are still RECORDED; only the agree rate excludes a voided one."""
    voided = set(voided or ())
    equiv = equiv or {}
    tune = _tune()
    rows, errors = [], 0
    for key, rec in _records(store, agent):
        select = ((rec.obs or {}).get("select") or {})
        row = {"key": key, "episode": str(rec.episode_id),
               "frame": (rec.decision or {}).get("frame"),
               "agent": rec.agent, "context": select.get("context"),
               "correct": rec.correct}
        if key in voided:                  # ON the row, so the artifact says WHICH, not just how many
            row["voided"] = True
        eq = equiv.get(key)
        if eq:                             # same reason: WHICH options were one decision, so a
            row["equiv"] = classes_of(eq)  # reviewer can see WHY a frame scored as agreement
        try:
            pilot = tune._build_pilot(rec.agent)[0]
            row["chosen"] = pilot.explain(rec.obs).chosen
        except Exception as e:                      # a frame this build cannot replay at all
            row["chosen"] = None
            row["error"] = _portable_error(e)
            errors += 1
        rows.append(row)
    labelled = [r for r in rows if r.get("correct") is not None and r.get("chosen") is not None]
    gradeable = gradeable_rows(rows)
    agree = sum(1 for r in gradeable
                if satisfies_human(r["chosen"], r["correct"], equiv=equiv.get(r["key"])))
    return {"rows": rows, "n": len(rows), "errors": errors,
            "labelled": len(labelled), "voided": len(labelled) - len(gradeable),
            "gradeable": len(gradeable), "agree": agree}


def gradeable_rows(rows) -> list:
    """ONE definition with three readers, so a readout cannot say "still graded" about a frame
    something else quietly dropped."""
    return [r for r in rows if r.get("correct") is not None and r.get("chosen") is not None
            and not r.get("voided")]


def unstatable_frames(store, agent=None) -> list:
    """A REPORTING caller and deliberately the only kind (Issue #251). A SECOND corpus pass on
    purpose: recording the exposure on the row would move the committed ruling record."""
    return [key for key, rec in _records(store, agent)
            if records_a_decline_it_cannot_state(rec, rec.obs)]


def print_unstatable_readout(exposed, rpt: dict) -> None:
    """Silent at zero, and reports ``chosen``/``correct`` as MEASURED rather than as a verdict: the
    agreement test needs an equivalence map this printer is not given."""
    if not exposed:
        return
    rows = rows_by_key(rpt)
    gradeable = {r["key"] for r in gradeable_rows(rpt.get("rows") or [])}
    print(f"\n  unstatable ({len(exposed)}) — reported, NEVER excluded (Issue #251):")
    for key in exposed:
        row = rows.get(key) or {}
        state = ("still GRADEABLE, still in the denominator" if key in gradeable
                 else "not in this capture's gradeable population")
        print(f"    {key}  records a decline it cannot state "
              f"(optional select, chosen == correct); {state}")
        print(f"      agent picks {row.get('chosen')} against a recorded correct "
              f"{row.get('correct')}")
        print("      -> re-rule it to `correct: []` (writable at `decision` scope since Issue #229) "
              "rather than excluding it")


def print_refused_shape_readout(refused, rpt: dict) -> None:
    """Corpus-wide — *"could the writer have written this record at all?"* — where
    `print_unstatable_readout` is report-scoped, so the two are not one parameterised printer."""
    if not refused:
        return
    rows = rows_by_key(rpt)
    gradeable = {r["key"] for r in gradeable_rows(rpt.get("rows") or [])}
    print(f"\n  refused shape ({len(refused)}) — committed records `build_correction` would NOT "
          f"create (Issue #256):")
    for f in refused:
        key = f["key"]
        state = ("GRADING anyway, in this capture's denominator" if key in gradeable
                 else "not in this capture's gradeable population")
        print(f"    {key}  ({f.get('id')}, {f.get('scope')} scope); {state}")
        for slug in f["violations"]:
            print(f"      {slug}: {REFUSED_SHAPE_RULES.get(slug, slug)}")
        row = rows.get(key)
        if row is not None:                   # absent when the record is in no capture at all, and
            print(f"      recorded correct {row.get('correct')}; this build's agent picks "
                  f"{row.get('chosen')}")     # `correct None; picks None` would read as DATA
        print("      -> re-rule the record. `Correction.from_dict` does not validate, deliberately "
              "(ADR-0113): a loader that refused this would take both gates down on load.")


def _print_summary(rpt: dict, equiv=None) -> None:
    by_ctx = {}
    for r in rpt["rows"]:
        by_ctx.setdefault(r.get("context"), []).append(r)
    # `gradeable` is absent from a capture taken before ADR-0088; fall back so a diff against an
    # older committed baseline still reads.
    gradeable = rpt.get("gradeable", rpt["labelled"])
    voided = rpt.get("voided", 0)
    classed = sum(1 for r in rpt["rows"] if r.get("equiv"))
    print(f"{rpt['n']} frames replayed, {rpt['errors']} unreplayable; "
          f"{rpt['agree']}/{gradeable} agree with the human"
          + (f" ({voided} voided, out of the rate)" if voided else "")
          + (f"; {classed} carry indistinguishable options" if classed else ""))
    for ctx in sorted(by_ctx, key=lambda c: (c is None, c)):
        rs = by_ctx[ctx]
        lab = gradeable_rows(rs)
        ok = sum(1 for r in lab
                 if satisfies_human(r["chosen"], r["correct"], equiv=(equiv or {}).get(r["key"])))
        print(f"  context {str(ctx):<5} {len(rs):>4} frames   {ok}/{len(lab)} agree")


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="Decision Gate: the agent's decisions vs a recorded baseline")
    ap.add_argument("--agent", default=None, help="restrict to one agent (default: all)")
    ap.add_argument("--store", default=str(REPO / "data" / "corrections"))
    sub = ap.add_subparsers(dest="cmd")
    cap = sub.add_parser("capture", help="write the baseline artifact (the gate's reference)")
    cap.add_argument("--out", type=Path, required=True)
    res = sub.add_parser("restamp", help="rewrite ONLY the recorded git_rev (a rebase moved the base)")
    res.add_argument("--baseline", type=Path, required=True)
    res.add_argument("--rev", default=None, help="the revision to stamp (default: this checkout's)")
    dif = sub.add_parser("diff", help="Decision Gate: diff this build against a capture")
    dif.add_argument("--baseline", type=Path, required=True)
    dif.add_argument("--context", type=int, default=None,
                     help="gate only one SelectContext's frames (e.g. 15 for the DAMAGE snipe pick)")
    dif.add_argument("--out", type=Path, default=None, help="write the verdict as JSON")
    args = ap.parse_args(argv)

    # A re-stamp never re-reads the build, so it runs BEFORE the corpus replay — that separation is
    # the point of the subcommand existing (ADR-0094 decision 2), not an optimisation.
    if args.cmd == "restamp":
        rev = args.rev or _git_rev()
        restamp_artifact(args.baseline, rev)
        print(f"-> re-stamped {args.baseline} to {rev} (verdicts untouched)")
        return 0

    # Every corpus-wide property below is read ONCE here and threaded through both subcommands: a
    # capture and the diff reading it must not resolve two different sets (ADR-0088/ADR-0091).
    index = ruling_index(args.store)
    voided = voided_frames(index)
    orphans = orphan_rulings(args.store)
    equiv = equivalence_index(args.store)
    rpt = build_report(args.store, args.agent, voided=set(voided), equiv=equiv)
    # Reported only, reaching no verdict: Issue #251 ruled that for the Unstatable Decline and
    # Issue #412 for the off-policy set. `refused_shapes` is deliberately NOT narrowed by `--agent`.
    exposed = unstatable_frames(args.store, args.agent)
    refused = refused_shapes(args.store)
    off_policy = off_policy_frames(args.store)

    if args.cmd == "capture":
        # Overwriting a RULING RECORD is guarded, not free, and the fail direction is
        # `decider_lab_diff`'s own REGRESSION verdict so the two cannot drift (ADR-0094 decision 1).
        def _write():
            write_json_artifact(args.out, {"git_rev": _git_rev(), "agent": args.agent, **rpt})
            _print_summary(rpt, equiv)
            print_ruling_readout(index, voided, orphans=orphans, detail=True)
            print_unstatable_readout(exposed, rpt)
            print_refused_shape_readout(refused, rpt)
            print_off_policy_readout(off_policy, present=rows_by_key(rpt))
            print(f"-> captured {rpt['n']} frames at {_git_rev()} to {args.out}")

        return guarded_capture(
            args.out, rpt, index=index, write=_write,
            diff_fn=lambda before, after: decider_lab_diff(before, after, voided=set(voided),
                                                           equiv=equiv),
            fail_keys_fn=decision_fail_keys)

    if args.cmd == "diff":
        before = json.loads(args.baseline.read_text(encoding="utf-8"))
        diff = decider_lab_diff(before, rpt, voided=set(voided), equiv=equiv)
        rows = diff["rows"]
        if args.context is not None:
            rows = [r for r in rows if r.get("context") == args.context]
        held_out = held_out_frames()
        passed = decision_gate_verdict(rows, held_out=held_out, voided=set(voided))
        regressions = [r for r in rows if r["verdict"] == "REGRESSION"]
        gating, ruled, void_hits = split_excused(regressions, held_out, voided)
        _print_summary(rpt, equiv)
        for v in ("FIX", "NEUTRAL", "UNLABELLED"):
            hits = [r for r in rows if r["verdict"] == v]
            if hits:
                print(f"\n  {v} ({len(hits)}) — reported, never gating:")
                for r in hits:
                    print(f"    {r['key']}  {r['before']} -> {r['after']}  (human {r['correct']})")
        if diff["added"] or diff["removed"]:
            print(f"\n  ⚠️ corpus shape moved: +{len(diff['added'])} / -{len(diff['removed'])} frames")
        print_ruling_moves(diff["ruling_moves"])
        print_ruling_readout(index, voided, orphans=orphans)
        print_unstatable_readout(exposed, rpt)
        print_refused_shape_readout(refused, rpt)
        # `moved` is the fail direction only, read off `decision_fail_keys` so this and the gate
        # cannot drift. Present-set is the whole capture: the exposure is corpus-wide.
        print_off_policy_readout(off_policy, present=rows_by_key(rpt),
                                 moved=decision_fail_keys(diff))
        if args.context is None:
            print_agree_delta(diff["agree_delta"])
        else:
            # The delta is corpus-wide while `--context` reports one SelectContext's frames, so
            # printing it here would put two populations in one report.
            print(f"\n  (agree delta withheld: it is corpus-wide, this run is context "
                  f"{args.context} only)")
        passed = print_gate_report(
            f"DECISION GATE (ADR-0072) — {diff['compared']} frames compared vs "
            f"{before.get('git_rev', '?')}"
            + (f", context {args.context} only" if args.context is not None else ""),
            gating=gating, ruled=ruled, held_out=held_out, total=len(regressions),
            rule="zero unruled REGRESSION",
            line=lambda r: f"REGRESSED {r['key']}  {r['before']} -> {r['after']}  "
                           f"(human {r['correct']})",
            voided=void_hits, voided_by=voided)
        if args.out:
            write_json_artifact(args.out, {
                "passed": passed, "rows": rows, "agree_delta": diff["agree_delta"],
                # `{key: disposition}`, not a bare key list: a machine consumer must be able to tell a
                # `transposition` exclusion from a `refuted` one without re-reading the ledger.
                "voided": {k: r.disposition for k, r in sorted(voided.items())},
                "orphan_rulings": [k for k, _e in orphans]})
        return 0 if passed else 1

    _print_summary(rpt, equiv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
