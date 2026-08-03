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

A ruling naming one of an **indistinguishable** set of options is satisfied by a pick of ANY member
of its **Option Equivalence Class** (ADR-0091, Issue #247) — two identical undamaged Riolu are one
decision, so the agent picking the human's twin is agreement, not disagreement. The map is resolved
from the CORPUS once and threaded through capture and diff, never read back off a capture; each row
records its own classes so the artifact says WHY a frame agreed. That closes ADR-0088's deferral, and
it is why the `transposition` ledger entry is gone while the disposition survives.

A frame carrying a **Voided Ruling** — `refuted` (the ruling was disowned) or `transposition` (it
stands but names one of an indistinguishable set) — is OUT of the rate entirely (ADR-0088). It is
neither agreement nor disagreement, so the denominator is `gradeable`, not `labelled`, and both are
recorded. Measured at the re-capture: **253/371 -> 248/346**, 25 frames voided. Those frames also stop
gating: 18 of the 101 recorded disagreements carried a refuted label, so a build correcting one used
to fail `main` as a REGRESSION.

It is still a DIAGNOSTIC number, never the gate's verdict. The gate is the per-frame diff below, and
a green gate means *nothing regressed*, **not** that the agent is right — the baseline records every
frame it captured as the reference, including the ones where the agent contradicts a human
(`docs/plans/decider-disagreement-triage.md` ranks those).

## Reading the `unstatable` section

A Correction on an **optional** select that names only the agent's own pick has not said *"taking it
was right"* — before Issue #229 that was the only shape a ruling on such a frame could take, because
`decision` scope refused the empty `correct` that means *decline*. Grading a decider against such a
record grades it against the opposite of what the human meant.
`gates.records_a_decline_it_cannot_state` detects the shape; **Issue #251 ruled that this report
NAMES those frames and never excludes them.** Excluding one would remove it from grading forever —
including after the record is repaired, which Issue #229 made possible — and a gate that under-reports is
indistinguishable from one with nothing to report. The line says what to do about it: re-rule the
record, do not ungrade the frame.

## Reading the `refused shape` section

`build_correction` validates at write time; `Correction.from_dict` — what the **Corpus Reader** loads
through — does not validate at all, so the store can hold a shape its own writer forbids. One did:
`85709280|1|match|` was `match` scope carrying `correct: [0]`, which the constructor refuses outright,
grading in both gates until the developer repaired it (ADR-0113 Amendment A: re-scoped to
`decision`/subject 51 — `85709280|1|decision|51` today). `gates.refused_shapes` re-applies the
constructor's rules to every committed record and this section names what it finds — empty on the
current corpus, and the property it was built for is that it stops being empty the moment a NEW bad
shape lands. **The asymmetry stays** (ADR-0113): a validating loader would reject committed records
at read time and take both gates down over a record that has been green for weeks. Reported, never a
verdict — the cure is to re-rule the record.

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

from train.gates import (REFUSED_SHAPE_RULES, classes_of, decider_lab_diff,  # noqa: E402
                         decision_gate_verdict, decision_fail_keys, equivalence_index,
                         guarded_capture, held_out_frames, keyed_corrections, orphan_rulings,
                         print_agree_delta, print_gate_report, print_ruling_moves,
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


def build_report(store, agent=None, *, voided=(), equiv=None) -> dict:
    """Replay every record through a FRESH shipped Pilot and record its decision.

    Fresh per frame, deliberately: the Pilot is stateful (deck tracker, caches), and the
    `needs_sweep` / `threat_sweep` discipline — both probes now deleted with the shadows they read
    (Issue #261 item 2h), the discipline outliving them — is one pilot per frame so a replay cannot inherit a
    previous frame's board. Unreplayable frames are recorded with `error` rather than dropped —
    a shrinking gated set must be visible, not silent. The *unreadable* ones used to be dropped
    silently, one layer earlier, which is what ADR-0087 fixes.

    A **Voided Ruling** frame is still replayed and still recorded — only the agree rate excludes it
    (ADR-0088 decision 4). ``labelled`` keeps its raw meaning and ``gradeable`` is the honest
    denominator, printed as ``agree/gradeable``: carrying both is what lets a re-capture's smaller
    denominator read as a deliberate exclusion rather than a vanishing corpus.
    """
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
        if key in voided:                  # recorded ON the row, so the artifact says WHICH, not just how many
            row["voided"] = True
        eq = equiv.get(key)
        if eq:                             # same reason: the row says WHICH options were one decision,
            row["equiv"] = classes_of(eq)  # so a reviewer can see WHY a frame scored as agreement
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
    """The rows behind the honest denominator — labelled on BOTH sides, and not voided.

    ONE definition with three readers: `build_report`'s totals, `_print_summary`'s per-context
    breakdown, and the `unstatable` readout's claim that an exposed frame is *still graded*. Written
    out three times it would be free to drift, and the readout's entire job is to say truthfully
    whether a frame the gate cannot properly grade is nevertheless still in the population the gate
    scores. A readout that answered that from its own private definition could say "still graded"
    about a frame something else had quietly dropped."""
    return [r for r in rows if r.get("correct") is not None and r.get("chosen") is not None
            and not r.get("voided")]


def unstatable_frames(store, agent=None) -> list:
    """The **Frame Keys** whose Correction is an **Unstatable Decline**
    (`gates.records_a_decline_it_cannot_state`), over the same replayable population `build_report`
    scores — so *"is it still gradeable?"* is answerable against that report's own rows.

    **A REPORTING caller, and deliberately the only kind.** Issue #251 ruled AGAINST wiring this
    predicate into either gate verdict: excluding a frame removes it from grading permanently,
    including after Issue #229 made the shape writable and the record repairable. The predicate's
    own docstring carries the ruling and its reasons.

    Read through the Corpus Reader like everything else (ADR-0087 decision 1): 23 records carry no
    explicit ``scope`` and only default to ``decision`` inside `Correction.from_dict`, so a raw JSONL
    walk mis-scopes them and this predicate — which tests ``scope`` first — would under-count.

    This is a SECOND pass over the corpus, and deliberately so. `build_report` holds every
    `(key, record)` pair but keeps only the row, and recording the exposure ON the row — the way
    ``voided`` and ``equiv`` are recorded — would change the shape of the committed capture, which is
    a **ruling record**. A reporting-only issue does not get to move the artifact. The pass costs one
    `load_corrections`, against 372 Pilot replays."""
    return [key for key, rec in _records(store, agent)
            if records_a_decline_it_cannot_state(rec, rec.obs)]


def print_unstatable_readout(exposed, rpt: dict) -> None:
    """Name every frame whose Correction cannot state the ruling it means — and say it is still
    **gradeable**.

    The section exists because *unwired and unreported* is the weakest of the three states. The
    predicate has detected a real encoding gap since Issue #197 and has had no caller at all since
    Issue #243, so nothing any operator reads has ever mentioned it. If the agent's pick moves on one
    of these frames, the gate's verdict is computed against a record that says the opposite of what
    the human meant, and no line in the report says why.

    Always visible when it fires, for the same reason `print_gate_report`'s ``HELD OUT`` and
    ``VOIDED`` sections are: a frame that a gate cannot grade properly must not become scenery.
    Silent at zero, so a clean corpus prints a clean report.

    It reports ``chosen``/``correct`` as measured rather than an AGREE/DISAGREE verdict: the
    agreement test is `satisfies_human`'s, threaded with an equivalence map this printer is not
    given, and a second opinion about agreement is exactly the drift `gradeable_rows` exists to
    avoid one class of.

    The exposure is a property of the CORPUS, so this section is not narrowed by ``--context`` and
    does not claim to be — unlike `print_agree_delta`, which is withheld there because it is a delta
    over the gated population. It says *this capture's* gradeable population, which is corpus-wide in
    every run.

    ``exposed`` is passed in rather than computed here so the section is testable on a synthetic
    record. Neither live exposed frame's pick has moved off the baseline, so a test that only ran
    against the corpus could not prove the section survives a flip."""
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
    """Name every committed record carrying a shape `build_correction` would refuse to create — and
    say whether it is **grading anyway** (Issue #256).

    A second reporting-only section beside `print_unstatable_readout`, and deliberately not a shared
    helper with it: the two answer different questions about different populations (that one is
    report-scoped and asks *"can this record state its ruling?"*; this one is corpus-wide and asks
    *"could the writer have written this record at all?"*). Two printers of eleven lines beat one
    parameterised printer that has to explain which mode it is in; if a third arrives, that is when to
    extract one.

    What it shares is the shape that made that one testable: a pure `(data, report) -> None` printer,
    resolved once in `main` and called from both subcommands, silent at zero, and indexing rows
    through `gates.rows_by_key` — *the one place a capture is turned into a lookup*.

    The gradeable claim is COMPUTED from `gradeable_rows`, never asserted, for that function's own
    reason: a readout with a private idea of the denominator could say "still grading" about a frame
    something else had quietly dropped. A corpus-wide audit legitimately names records that are in no
    capture at all (unreplayable, or filtered out by ``--agent``), and the line says so rather than
    implying a row exists.

    ``refused`` is passed in rather than computed here so the section is testable on a synthetic
    finding. The live one has never moved, so a test that only read the corpus could not prove the
    section survives a second record appearing — which is the whole property the audit adds."""
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
        if row is not None:                   # absent when the record is in no capture at all;
            print(f"      recorded correct {row.get('correct')}; this build's agent picks "
                  f"{row.get('chosen')}")     # `correct None; picks None` would read as DATA
        print("      -> re-rule the record. `Correction.from_dict` does not validate, deliberately "
              "(ADR-0113): a loader that refused this would take both gates down on load.")


def _print_summary(rpt: dict, equiv=None) -> None:
    by_ctx = {}
    for r in rpt["rows"]:
        by_ctx.setdefault(r.get("context"), []).append(r)
    # `gradeable` is absent from a capture taken before ADR-0088; fall back rather than crash, so
    # a diff against an older committed baseline still reads.
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

    # The **Ruling Index** is read ONCE and threaded through both subcommands: the rulings are one
    # corpus, not a property of a capture, so a capture and the diff that reads it must not resolve
    # two different voided sets (ADR-0088 decision 2).
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
    # The **Option Equivalence Class** map, read once for the same reason and threaded the same way
    # (ADR-0091 decision 2): it is a property of the CORPUS, so a capture and the diff reading it
    # must not resolve two different ideas of which options are one decision.
    equiv = equivalence_index(args.store)
    rpt = build_report(args.store, args.agent, voided=set(voided), equiv=equiv)
    # The **unstatable** exposure, resolved here and reported by both subcommands because it is a
    # property of the CORPUS, not of a capture or a diff — the same reason the Ruling Index is read
    # up here. Unlike that index it costs a second corpus read, which is a deliberate trade:
    # see `unstatable_frames`. Reported only — it reaches no verdict, and Issue #251 ruled it
    # never should.
    exposed = unstatable_frames(args.store, args.agent)
    # The **Refused Shape** audit (Issue #256), resolved here for the same reason and reported the
    # same way — a property of the CORPUS, not of a capture. Unlike `exposed` it is deliberately NOT
    # narrowed by `--agent`: "could the writer have written this record?" is not a question about
    # which agent is being gated, and a record hidden by a filter is the one least likely to be
    # repaired. Reported only; it reaches no verdict.
    refused = refused_shapes(args.store)

    if args.cmd == "capture":
        # A baseline is a RULING RECORD (CLAUDE.md), so overwriting one is guarded, not free: a frame
        # whose pick this build moves OFF the human's ruling may only become the new reference once a
        # human has ruled it. The fail direction is `decider_lab_diff`'s own REGRESSION verdict, so
        # the guard and the gate cannot drift into two ideas of "worse" (ADR-0094 decision 1).
        def _write():
            write_json_artifact(args.out, {"git_rev": _git_rev(), "agent": args.agent, **rpt})
            _print_summary(rpt, equiv)
            print_ruling_readout(index, voided, orphans=orphans, detail=True)
            print_unstatable_readout(exposed, rpt)
            print_refused_shape_readout(refused, rpt)
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
        if args.context is None:
            print_agree_delta(diff["agree_delta"])
        else:
            # The delta is corpus-wide while `--context` reports one SelectContext's frames. Printing
            # it here would put two populations in one report — the exact trap `ruling_moves`' `keep`
            # argument exists to avoid — so it is withheld rather than mislabelled.
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
