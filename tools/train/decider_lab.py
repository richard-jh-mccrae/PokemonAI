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

## Reading the agree rate

"Agree" means the agent's pick **satisfies** the Correction — `correct ⊆ chosen` (`satisfies_human`,
ADR-0085 Amendment J), not `correct == chosen`. A Correction's `correct` names *the card the ruling
was about*; a multi-pick select returns every index the engine demands. Equality across those two
vocabularies mis-reports: it read `DISCARD` at **1/12** purely because the agent picks `[2, 3]` where
the ruling says `[2]`. On single-pick contexts the two tests are identical.

It is still a DIAGNOSTIC number, never the gate's verdict. The gate is the per-frame diff below, and
a green gate means *nothing regressed*, **not** that the agent is right — the baseline records every
frame it captured as the reference, including the ones where the agent contradicts a human
(`docs/plans/decider-disagreement-triage.md` ranks those).

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
                         held_out_frames, keyed_corrections, print_gate_report,
                         print_ruling_moves, satisfies_human, write_json_artifact)


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
    """Every replayable Correction, already paired with its **Frame Key**.

    One line, because it must be: this is `gates.keyed_corrections`, THE Corpus Reader
    (ADR-0087 decision 1). What used to live here was a private raw-JSONL walk with a
    hand-built key, and it cost 40 dropped records plus 163 mis-keyed ones — see that function's
    docstring for the measurement. The predicate runs on the CONSTRUCTED record, so an empty
    ``agent`` has already been backfilled from ``agent_build`` before anything filters on it.

    Sorted by key so a capture's row order is stable across runs and machines."""
    def keep(c):
        return bool(c.obs and c.agent) and (not agent or c.agent == agent)

    return sorted(keyed_corrections(store, predicate=keep), key=lambda kc: kc[0])


def _portable_error(exc: Exception) -> str:
    """One unreplayable frame's error, with every machine-specific path removed.

    The baseline is a COMMITTED ruling record, so anything it embeds must be reproducible on any
    box. It was embedding an absolute path — `/home/user/PokemonAI/...` from the Linux capture,
    `C:\\Users\\...` from a Windows one — so the same build re-captured on a different machine
    produced a different artifact for a frame whose *verdict* had not moved. Dev is Windows and the
    grader is Linux (CLAUDE.md), so that difference is the normal case, not an edge one.

    Repo-relative and forward-slashed, keeping the diagnostic (which file, which error) while
    dropping the part that only says who ran it.

    Slashes are normalised BEFORE the root is stripped: an exception's ``str`` carries the path
    already repr-escaped (``C:\\\\Users\\\\...``), so matching ``str(REPO)`` against the raw text
    silently fails on Windows and leaves the absolute path in.
    """
    text = f"{type(exc).__name__}: {exc}".replace("\\\\", "/").replace("\\", "/")
    root = str(REPO).replace("\\", "/")
    return text.replace(root + "/", "").replace(root, "")


def build_report(store, agent=None) -> dict:
    """Replay every record through a FRESH shipped Pilot and record its decision.

    Fresh per frame, deliberately: the Pilot is stateful (deck tracker, caches), and the
    `needs_sweep` / `threat_sweep` discipline is one pilot per frame so a replay cannot inherit a
    previous frame's board. Unreplayable frames are recorded with `error` rather than dropped —
    a shrinking gated set must be visible, not silent. The *unreadable* ones used to be dropped
    silently, one layer earlier, which is what ADR-0087 fixes.
    """
    tune = _tune()
    rows, errors = [], 0
    for key, rec in _records(store, agent):
        select = ((rec.obs or {}).get("select") or {})
        row = {"key": key, "episode": str(rec.episode_id),
               "frame": (rec.decision or {}).get("frame"),
               "agent": rec.agent, "context": select.get("context"),
               "correct": rec.correct}
        try:
            pilot = tune._build_pilot(rec.agent)[0]
            row["chosen"] = pilot.explain(rec.obs).chosen
        except Exception as e:                      # a frame this build cannot replay at all
            row["chosen"] = None
            row["error"] = _portable_error(e)
            errors += 1
        rows.append(row)
    labelled = [r for r in rows if r.get("correct") is not None and r.get("chosen") is not None]
    agree = sum(1 for r in labelled if satisfies_human(r["chosen"], r["correct"]))
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
        ok = sum(1 for r in lab if satisfies_human(r["chosen"], r["correct"]))
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
        write_json_artifact(args.out, {"git_rev": _git_rev(), "agent": args.agent, **rpt})
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
        print_ruling_moves(diff["ruling_moves"])
        passed = print_gate_report(
            f"DECISION GATE (ADR-0072) — {diff['compared']} frames compared vs "
            f"{before.get('git_rev', '?')}"
            + (f", context {args.context} only" if args.context is not None else ""),
            gating=gating, ruled=ruled, held_out=held_out, total=len(regressions),
            rule="zero unruled REGRESSION",
            line=lambda r: f"REGRESSED {r['key']}  {r['before']} -> {r['after']}  "
                           f"(human {r['correct']})")
        if args.out:
            write_json_artifact(args.out, {"passed": passed, "rows": rows})
        return 0 if passed else 1

    _print_summary(rpt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
