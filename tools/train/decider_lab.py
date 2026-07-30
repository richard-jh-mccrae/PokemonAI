"""Decider lab — the **Decision Gate**, against a RECORDED baseline (ADR-0072 decision 2, as amended
by ADR-0085 Amendment I).

Replays every replayable Correction through a fresh shipped Pilot and records what the agent DECIDES,
then diffs that against a committed capture. It is the Discrimination Gate's sibling one level up: the
leaf lab asks *"does the leaf still rank the human's option top?"*, this asks *"does the agent still
PLAY the human's option?"* — the end-to-end question, and the one a ladder actually sees.

## Why this exists — the sweeps' reference rotted, silently

ADR-0072 named the Decision Gate as *"the phase's `tools/train/probes/*_decider_sweep.py`"*, and every
one of those compares the shipped agent against its own kill-switch turned OFF. That was exactly right
at the swap: OFF was *the incumbent rung pile*, so the diff measured the equation against what it
replaced.

Then each phase DELETED its pile, as tracker directive 1 requires — and nothing re-pointed the gates.
Verified 2026-07-30, not assumed:

    baseline_promote      0 rungs left (was 12)      promote_retreat_decider_sweep
    baseline_energy       3        (was 22)          attach_decider_sweep
    baseline_evolution    2        (was 6)           evolve_decider_sweep
    baseline_snipe        3        (was 9)           snipe_decider_sweep   <- counter rungs only

With the pile gone, "OFF" is an empty scorer whose argmax falls to option index, so every sweep
compares the agent against nothing. `evolve_decider_sweep` reports `4 FIX, 0 REGRESSION`;
`snipe_decider_sweep` reports `12 FIX, 0 REGRESSION`. **A gate that can only ever report FIX cannot
detect a regression**, which is the single thing ADR-0072 built it to do — and a vacuous gate is worse
than an absent one, because `PASS` gets read as evidence.

The Discrimination Gate never had this problem for one structural reason: it diffs against a committed
capture, never against a live switch. This applies that fix to the decision level.

## Use

    python tools/train/decider_lab.py capture --out data/decider_lab/baseline.json
    python tools/train/decider_lab.py diff --baseline data/decider_lab/baseline.json
    python tools/train/decider_lab.py diff --baseline ... --context 15   # one phase's frames

**The baseline is a RULING RECORD, never auto-recaptured** — the same discipline `data/leaf_lab/`
carries. Re-capture only once a build's flips have been ruled with the user, or the gate becomes a
mirror that agrees with whatever it is shown. Frames ruled out of a decider's scope are held out via
the Held-out Ledger (ADR-0072 decision 4) and reported but never gated.

Offline and read-only apart from `capture --out`.
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

from train.gates import (decider_lab_diff, decision_gate_verdict,  # noqa: E402
                         frame_key_of, held_out_frames, print_gate_report)


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
    """Every Correction carrying the obs needed to replay it, keyed so duplicates collapse."""
    index = {}
    for jf in sorted(Path(store).glob("*/corrections.jsonl")):
        for line in jf.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            if agent and d.get("agent") != agent:
                continue
            if not (d.get("obs") and d.get("agent")):
                continue
            index[(str(d.get("episode_id")), d.get("decision", {}).get("frame"))] = d
    return [v for _k, v in sorted(index.items(), key=lambda kv: (kv[0][0], kv[0][1] or 0))]


def _key(rec) -> str:
    """The frame's Held-out-Ledger key. Built through `gates.frame_key_of` so one ruling holds a
    frame out of BOTH gates — a second implementation drifting by a field would silently stop
    matching, which is the failure ADR-0072 decision 4 exists to prevent."""
    d = rec.get("decision") or {}
    return frame_key_of(rec.get("episode_id"), d.get("seat", 0), "decision", d.get("frame"))


def build_report(store, agent=None) -> dict:
    """Replay every record through a FRESH shipped Pilot and record its decision.

    Fresh per frame, deliberately: the Pilot is stateful (deck tracker, caches), and the
    `needs_sweep` / `threat_sweep` discipline is one pilot per frame so a replay cannot inherit a
    previous frame's board. Unreplayable frames are recorded with `error` rather than dropped —
    a shrinking gated set must be visible, not silent.
    """
    tune = _tune()
    rows, errors = [], 0
    for rec in _records(store, agent):
        select = ((rec.get("obs") or {}).get("select") or {})
        row = {"key": _key(rec), "episode": str(rec.get("episode_id")),
               "frame": (rec.get("decision") or {}).get("frame"),
               "agent": rec.get("agent"), "context": select.get("context"),
               "correct": rec.get("correct")}
        try:
            pilot = tune._build_pilot(rec["agent"])[0]
            row["chosen"] = pilot.explain(rec["obs"]).chosen
        except Exception as e:                      # a frame this build cannot replay at all
            row["chosen"] = None
            row["error"] = f"{type(e).__name__}: {e}"
            errors += 1
        rows.append(row)
    labelled = [r for r in rows if r.get("correct") is not None and r.get("chosen") is not None]
    agree = sum(1 for r in labelled if r["chosen"] == r["correct"])
    return {"rows": rows, "n": len(rows), "errors": errors,
            "labelled": len(labelled), "agree": agree}


def _print_summary(rpt: dict) -> None:
    by_ctx = {}
    for r in rpt["rows"]:
        by_ctx.setdefault(r.get("context"), []).append(r)
    print(f"{rpt['n']} frames replayed, {rpt['errors']} unreplayable; "
          f"{rpt['agree']}/{rpt['labelled']} agree with the human")
    for ctx in sorted(by_ctx, key=lambda c: (c is None, c)):
        rs = by_ctx[ctx]
        lab = [r for r in rs if r.get("correct") is not None and r.get("chosen") is not None]
        ok = sum(1 for r in lab if r["chosen"] == r["correct"])
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
    dif = sub.add_parser("diff", help="Decision Gate: diff this build against a capture")
    dif.add_argument("--baseline", type=Path, required=True)
    dif.add_argument("--context", type=int, default=None,
                     help="gate only one SelectContext's frames (e.g. 15 for the DAMAGE snipe pick)")
    dif.add_argument("--out", type=Path, default=None, help="write the verdict as JSON")
    args = ap.parse_args(argv)

    rpt = build_report(args.store, args.agent)

    if args.cmd == "capture":
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps({"git_rev": _git_rev(), "agent": args.agent, **rpt},
                                       indent=2), encoding="utf-8")
        _print_summary(rpt)
        print(f"-> captured {rpt['n']} frames at {_git_rev()} to {args.out}")
        return 0

    if args.cmd == "diff":
        before = json.loads(args.baseline.read_text(encoding="utf-8"))
        diff = decider_lab_diff(before, rpt)
        rows = diff["rows"]
        if args.context is not None:
            rows = [r for r in rows if r.get("context") == args.context]
        held_out = held_out_frames()
        passed = decision_gate_verdict(rows, held_out=held_out)
        regressions = [r for r in rows if r["verdict"] == "REGRESSION"]
        gating = [r for r in regressions if r["key"] not in held_out]
        ruled = [r for r in regressions if r["key"] in held_out]
        _print_summary(rpt)
        for v in ("FIX", "NEUTRAL", "UNLABELLED"):
            hits = [r for r in rows if r["verdict"] == v]
            if hits:
                print(f"\n  {v} ({len(hits)}) — reported, never gating:")
                for r in hits:
                    print(f"    {r['key']}  {r['before']} -> {r['after']}  (human {r['correct']})")
        if diff["added"] or diff["removed"]:
            print(f"\n  ⚠️ corpus shape moved: +{len(diff['added'])} / -{len(diff['removed'])} frames")
        passed = print_gate_report(
            f"DECISION GATE (ADR-0072) — {diff['compared']} frames compared vs "
            f"{before.get('git_rev', '?')}"
            + (f", context {args.context} only" if args.context is not None else ""),
            gating=gating, ruled=ruled, held_out=held_out, total=len(regressions),
            rule="zero unruled REGRESSION",
            line=lambda r: f"REGRESSED {r['key']}  {r['before']} -> {r['after']}  "
                           f"(human {r['correct']})")
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps({"passed": passed, "rows": rows}, indent=2),
                                encoding="utf-8")
        return 0 if passed else 1

    _print_summary(rpt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
