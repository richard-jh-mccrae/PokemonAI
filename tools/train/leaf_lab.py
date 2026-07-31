"""Leaf lab — measure the develop rung's end-of-turn LEAF against tagged turn_plan corrections.

The develop rollout rung commits the option whose simmed end-of-turn board scores highest under
`_engine_leaf_value`. When it plays badly, the leaf is the suspect (`docs/plans/turn-planner-develop-rung.md`
Phase 0: "leaf value first — the bottleneck"). This lab re-scores a tagged correction's MAIN-select
board OFFLINE — cgpy-backed, so any leaf version is measurable without a Kaggle-ladder round-trip — and
reports the one thing that matters: **does the leaf rank the human's `correct` option highest, or bury
it under a degenerate tie?**

A *leaf frame* (`is_leaf_frame`) is any reseedable MAIN-select correction with a target to rank: a
turn-planner correction (`turn_plan` payload — the rung's own domain) OR any MAIN-select pick correction
that names a `correct` option. The second shape lets the whole tagged corpus of setup-turn pick
corrections drive leaf enrichment, not only the handful that carry the prose `turn_plan` payload.

    python tools/train/leaf_lab.py                 # score every turn_plan correction, print the report
    python tools/train/leaf_lab.py --agent dragapult_ex

cgpy is a PARITY-LIMITED twin of the native engine (~298/434 ladder): its leaf VALUES differ slightly
from native, but the RANKING it reveals is the signal we act on. Boards cgpy can't reseed are skipped
and counted (never silently dropped).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from train.gates import print_gate_report                     # noqa: E402

_PLACEHOLDER_SBI = "leaf-lab-cgpy-reseed"   # any non-empty token passes `_simulate_line`'s gate; cgpy
                                            # then reconstructs the search state from the structured obs


def board_leaf_values(pilot, obs) -> list:
    """The leaf value `_engine_leaf_value` assigns to taking EACH menu option first (index-aligned;
    None where the sim is unavailable). Injects a placeholder `search_begin_input` so the offline obs
    passes the sim gate — cgpy rebuilds the state from the board when no real token is present."""
    obs = {**obs, "search_begin_input": obs.get("search_begin_input") or _PLACEHOLDER_SBI}
    options = (obs.get("select") or {}).get("option") or []
    values = []
    for i in range(len(options)):
        pilot._planning = True                  # the rung's reentrancy guard (never nest a search)
        try:
            values.append(pilot._engine_leaf_value(obs, [i]))
        except Exception:
            values.append(None)
        finally:
            pilot._planning = False
    return values


def frame_key(correction) -> str:
    """The **stable identity** of a leaf frame, as a flat string a JSON capture can key on.

    This is the Correction's own ``identity_key`` — ``(episode, seat, scope, subject)``, already the
    repo's answer to "are these two records the same blunder" (ADR-0049). It matters because the
    Discrimination Gate diffs captures per frame, and ``episode_id`` alone is NOT unique: keying on
    it merged frames from one episode and collapsed a real 276-row diff to 221. A gate that
    under-reports is the exact failure it exists to prevent.

    Delegates to `gates.correction_frame_key`, the single derivation the **Corpus Reader** uses
    (ADR-0087 decision 2) — so a frame carries ONE name across both gates and a ruling held out
    of one is held out of the other. The Decision Gate hand-built its own and read ``seat`` off the
    ``decision`` snapshot, which has no such field: 163 of its 332 keys were wrong, and four standing
    Held-out Ledger rulings could not reach it."""
    from train.gates import correction_frame_key
    return correction_frame_key(correction)


def evaluate_leaf_on_correction(pilot, correction) -> dict:
    """Score one `turn_plan` correction's board and rank the human's `correct` pick under the leaf.

    Returns per-option `values`, and the verdict: `correct_is_top` (a correct option holds the strict
    or shared maximum — LENIENT, a shared max counts), `correct_is_unique_top` (a correct option is the
    SOLE maximum — the honest "the argmax rung would actually pick your option", since ties break by
    option order, not by you), `correct_rank` (1 = best; ties don't demote), `outscored_by` (options
    strictly above the best correct), and `top_tie` (how many share the top value — a large tie is a leaf
    that can't discriminate). `scored` is None-free option count; `unscorable` when no correct option scored.
    """
    values = board_leaf_values(pilot, correction.obs or {})
    correct = list(correction.correct or [])
    scored = [v for v in values if v is not None]
    correct_vals = [values[i] for i in correct if 0 <= i < len(values) and values[i] is not None]
    base = {"key": frame_key(correction),
            "episode_id": getattr(correction, "episode_id", None),
            "agent": getattr(correction, "agent", None), "correct": correct,
            "values": values, "scored": len(scored), "n_options": len(values)}
    if not scored or not correct_vals:
        return {**base, "unscorable": True, "correct_value": None, "top_value": None,
                "correct_is_top": None, "correct_is_unique_top": None, "correct_rank": None,
                "outscored_by": None, "top_tie": None}
    top = max(scored)
    best_correct = max(correct_vals)
    outscored = sum(1 for v in scored if v > best_correct)
    top_tie = sum(1 for v in scored if v == top)
    is_top = best_correct >= top
    return {**base, "unscorable": False, "correct_value": best_correct, "top_value": top,
            "correct_is_top": is_top, "correct_is_unique_top": is_top and top_tie == 1,
            "correct_rank": outscored + 1, "outscored_by": outscored, "top_tie": top_tie}


def is_leaf_frame(c) -> bool:
    """Does this correction exercise the develop-rung leaf — a reseedable MAIN-select (context 0) board
    with a target the leaf can be asked to rank? Two shapes qualify (ADR-0031 develop rung): a
    turn-planner correction (carries a ``turn_plan`` payload — the rung's own domain, kept even when
    ``correct`` is empty so an unscored setup turn is still *counted* as a leaf frame), and any
    MAIN-select pick correction that names a ``correct`` option — the human's intended first action,
    whatever the correction's scope. Non-MAIN / obs-less records are excluded: the offline sim reseeds
    ONLY from a MAIN-select board (the leaf-lab gotcha), so they could never be scored regardless."""
    obs = getattr(c, "obs", None)
    if not obs:
        return False
    if getattr(c, "turn_plan", None):
        return True
    return bool(getattr(c, "correct", None)) and (obs.get("select") or {}).get("context") == 0


def leaf_lab_report(pilot_for, corrections, *, voided=()) -> dict:
    """Aggregate the leaf verdict across a batch. `pilot_for(agent)` builds/returns the cgpy-wired Pilot
    for an agent (memoised by the caller). Only leaf frames (``is_leaf_frame``) are considered.

    A **Voided Ruling** frame is still scored and still carried in ``rows`` — it is marked ``voided``
    and left out of the RATES only (ADR-0088 decision 4). It deliberately stays *scorable*, so the
    diff still compares it and `ruling_moves` still sees it: a voided ruling stops grading, it does not
    stop existing, and a frame vanishing from ``compared`` would be the shrinking-gated-set failure
    ``added``/``removed`` exist to prevent."""
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
            "voided": len(scorable) - len(gradeable), "gradeable": len(gradeable),
            "leaf_correct": len(leaf_correct),
            "leaf_correct_rate": (len(leaf_correct) / len(gradeable)) if gradeable else None,
            "leaf_correct_strict": len(leaf_strict),
            "leaf_correct_strict_rate": (len(leaf_strict) / len(gradeable)) if gradeable else None,
            "avg_top_tie": (sum(r["top_tie"] for r in gradeable) / len(gradeable)) if gradeable else None,
            "rows": rows}


def _cgpy_pilot_builder():
    """A memoised `pilot_for(agent)` that builds each agent's real Pilot and wires cgpy as its offline
    search backend. Returns None for an agent whose Pilot can't be built."""
    import importlib
    from cgpy.compat import api as cgpy_api
    tune = importlib.import_module("train.tune")
    cache: dict = {}

    def build(agent):
        if agent not in cache:
            try:
                pilot, _ = tune._build_pilot(agent)
                pilot._search_api = cgpy_api      # the seam: re-score offline via cgpy, not native
                cache[agent] = pilot
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
    # `gradeable` is absent from a capture taken before ADR-0088; fall back rather than crash,
    # so a diff against an older committed baseline still reads. Same field name the Decision Gate
    # uses — one concept, one word.
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
    for r in rpt["rows"]:
        if r["unscorable"]:
            print(f"  ep{r['episode_id']} correct={r['correct']}: UNSCORABLE ({r['scored']}/{r['n_options']} sim'd)")
        else:
            flag = "OK " if r["correct_is_top"] else "MISS"
            print(f"  ep{r['episode_id']} correct={r['correct']}: {flag} rank {r['correct_rank']}/{r['n_options']}"
                  f"  correct={r['correct_value']} top={r['top_value']} top_tie={r['top_tie']}")


def _print_diff(diff, held_out, before_meta, voided=None) -> None:
    """The Discrimination Gate's report. The aggregate metrics are printed by `_print_report` for
    context and are deliberately absent from the verdict — over 1b they moved the GOOD way while six
    frames broke, so a gate keyed on them would have passed the swap that motivated this gate."""
    if diff["added"] or diff["removed"]:
        # Never silently tolerated: a shifted corpus means the two captures are not comparable, and a
        # diff that quietly skips frames reads green for the wrong reason.
        print(f"  CORPUS SHIFTED: +{len(diff['added'])} frame(s) added, "
              f"-{len(diff['removed'])} removed since the capture — re-capture the baseline.")
    for f in diff["miss_to_ok"]:
        print(f"  IMPROVED  {f['key']}  MISS -> OK")
    from train.gates import split_excused
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
    cap = sub.add_parser("capture", help="write a baseline report artifact (the gate's reference)")
    cap.add_argument("--out", type=Path, required=True)
    dif = sub.add_parser("diff", help="Discrimination Gate: diff this build against a capture")
    dif.add_argument("--baseline", type=Path, required=True)
    dif.add_argument("--out", type=Path, default=None,
                     help="write the gate verdict as JSON (machine-readable, for a phase checklist)")
    args = ap.parse_args(argv)

    # Read ONCE and threaded through both subcommands — the rulings are one corpus, not a property of
    # a capture, so a capture and the diff reading it must not resolve two different voided sets.
    from train.gates import orphan_rulings, ruling_index, voided_frames
    index = ruling_index(args.store)
    voided = voided_frames(index)
    orphans = orphan_rulings(args.store)
    rpt = _build_report(args.store, args.agent, voided=set(voided))

    if args.cmd == "capture":
        from train.gates import print_ruling_readout, write_json_artifact
        write_json_artifact(args.out, {"git_rev": _git_rev(), "agent": args.agent, **rpt})
        _print_report(rpt)
        print_ruling_readout(index, voided, orphans=orphans, detail=True)
        print(f"-> captured {rpt['scorable']} scorable frames at {_git_rev()} to {args.out}")
        return 0

    if args.cmd == "diff":
        from train.gates import (discrimination_gate_verdict, held_out_frames, leaf_lab_diff,
                                 print_agree_delta, print_ruling_moves, print_ruling_readout,
                                 write_json_artifact)
        before = json.loads(args.baseline.read_text(encoding="utf-8"))
        diff = leaf_lab_diff(before, rpt, voided=set(voided))
        held_out = held_out_frames()
        passed = discrimination_gate_verdict(diff, held_out=held_out, voided=set(voided))
        _print_report(rpt)
        # Context BEFORE the verdict, matching the Decision Gate: `_print_diff` ends with the
        # PASS/FAIL line, and a reader who stops there must not have skipped the delta that explains
        # the numbers above it.
        print_ruling_moves(diff["ruling_moves"])
        print_ruling_readout(index, voided, orphans=orphans)
        print_agree_delta(diff["agree_delta"])
        _print_diff(diff, held_out, before, voided)
        if args.out:                      # US6: the gate's verdict as a machine-readable artifact
            write_json_artifact(args.out, {
                "gate": "discrimination", "passed": passed, "git_rev": _git_rev(),
                "baseline_git_rev": before.get("git_rev"), "compared": diff["compared"],
                "ok_to_miss": [f["key"] for f in diff["ok_to_miss"]],
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
