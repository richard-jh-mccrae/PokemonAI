"""Deploy DECIDER sweep — the Decision Gate's input for the no-shadow swap (Issue #197, ADR-0084).

The sibling of `attach_decider_sweep.py` / `evolve_decider_sweep.py` / `promote_retreat_decider_sweep.py`,
same protocol (ADR-0069 §8): run the corpus through BOTH deploy deciders while both still exist and
report every frame where they disagree, with the new decider's TERM BREAKDOWN on each side of the
flip. No decision may flip silently — the human rules on the WHY, one sitting, one table, BEFORE the
deletion commit retires the rungs for good.

The two pilots, built fresh per frame (pilots are stateful; sharing one pollutes verdicts):

  * NEW — `deploy_value` ON with the nine retired rungs forced to weight 0. That is exactly the
    post-deletion agent. Zeroing rather than deleting is what lets this run BEFORE the deletion
    commit, and is also why the shipped PROFILE keeps `deploy_value` ARMED-OFF until then: with the
    rungs still live, ON would double-count every bench play.
  * OLD — `deploy_value` OFF with every rung at its shipped weight: the pile as it decides today.

Comparison is by the resolved OPTION IDENTITY, never the raw option index — and for this lane that
identity is the CARD, not a board slot: a mid-game bench play is `OptionType.PLAY` carrying a bare
hand index and no `area`, so the positional resolver returns None for exactly the options this
decider ranks (ADR-0084's `option_slot` extension). `correct` (the human label, where the frame has
one) is shown on both sides so a flip reads as a FIX, a REGRESSION, or a no-label judgement call.

    python tools/train/probes/deploy_decider_sweep.py            # the flip table + the tally
    python tools/train/probes/deploy_decider_sweep.py --all      # every frame, not only the flips
    python tools/train/probes/deploy_decider_sweep.py --quiet    # one line + the gate verdict

Offline and read-only; two engine-backed Pilot builds per frame.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from train.gates import (DEPLOY_LANE, decision_gate_verdict, frame_key_of,  # noqa: E402
                         held_out_frames, in_lane, lane_slots, option_slot,
                         print_gate_report)

#: The rungs the Deploy Marginal retires (ADR-0084). Forced to 0 in the NEW pilot so this probe
#: measures the post-deletion agent without needing the deletion first.
#:
#: `keep-a-bench` is deliberately ABSENT: it guards a WIN CONDITION rather than a preference
#: (`docs/rules.md` §7 case 2), so decision 7 PROMOTES it to a post-setup sound rung — a filter on the
#: option order — rather than deleting it. Zeroing it here would measure an agent that can lose on the
#: spot, which is neither the old agent nor the new one.
RETIRED = (
    # baseline_bench.py
    "dont-bench-multiprize",
    "pre-position-attacker",
    "develop-a-basic-in-setup",
    "develop-the-wincon-base-first",
    "dont-bench-onto-their-path",
    "develop-the-accel-recipient",
    # doctrine_fetch.py
    "bench-the-supporter-tutor",
    "dont-pre-bench-the-supporter-tutor",
    "dont-pre-bench-a-redundant-utility",
)

_TERMS = ("assignment_relevance", "ability_relevance", "accel_unlock", "exposure")


def _names() -> dict:
    out = {}
    with open(REPO / "data" / "EN_Card_Data.csv", encoding="utf-8") as f:
        for r in csv.reader(f):
            if r and r[0].isdigit():
                out.setdefault(int(r[0]), r[1])
    return out


def _frames():
    index = {}
    for jf in (REPO / "data" / "corrections").glob("*/corrections.jsonl"):
        for line in jf.read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                index[(str(d.get("episode_id")), d.get("decision", {}).get("frame"))] = d
    return [(k, v) for k, v in sorted(index.items()) if v.get("obs") and v.get("agent")]


def _frame_key(rec, ep, fr) -> str:
    """The frame's stable identity, in the SAME form the Leaf Lab and the Held-out Ledger use, so a
    single ruling can hold a frame out of either gate."""
    scope = rec.get("scope") or "decision"
    subject = rec.get("subject")
    if subject is None:
        subject = fr if scope == "decision" else (rec.get("decision") or {}).get("turn")
    return frame_key_of(ep, rec.get("seat"), scope, subject)


def _agent(rec) -> str:
    a = rec.get("agent") or ""
    return a if a in {"dragapult_ex", "mega_lucario", "mega_starmie", "slowking"} else "mega_starmie"


def _strategy_and_deck(agent: str):
    agent_dir = REPO / "src" / "agents" / agent
    spec = importlib.util.spec_from_file_location(f"{agent}_strategy", agent_dir / "strategy.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    deck = [int(x) for x in (agent_dir / "deck.csv").read_text(encoding="utf-8").splitlines()[:60]
            if x.strip()]
    return mod.STRATEGY, deck


def _pilot(agent: str, *, new: bool, seams):
    from common.runtime import build_pilot
    strategy, deck = _strategy_and_deck(agent)
    params = dict(strategy.params)
    params["deploy_value"] = bool(new)
    overrides = {hid: 0 for hid in RETIRED} if new else None
    return build_pilot(strategy, deck, params=params, overrides=overrides, **seams)


def _seams():
    """Engine-backed knowledge seams built ONCE and injected into every Pilot — immutable card
    knowledge, so sharing them is safe where sharing a Pilot is not."""
    from common.scouting.artifact import load_artifact
    from common.scouting.briefs import load_briefs
    from common.scouting.provider import EngineCardStatProvider
    from common.scouting.scout import Scout
    stats = EngineCardStatProvider()
    stats.warm()
    return {"stats": stats, "scout": Scout(load_artifact(), provider=stats),
            "briefs": load_briefs()}


def _records_a_decline_it_cannot_state(rec, obs) -> bool:
    """Does this record sit on an OPTIONAL select while asserting the agent's own pick?

    Such a record cannot grade a decline, and a decline is precisely what an optional select puts on
    the table. `correct` at `decision` scope must be non-empty and index a legal option, so "take
    none" has no encoding; `chosen == correct` then means "no preference was recordable", NOT "taking
    it was right". Grading against it turns a correct decline into a REGRESSION.

    Deliberately narrow. It does NOT skip every `chosen == correct` record — on a MANDATORY select
    those state a real preference (the pick was right), and a decider that flips away from one is a
    genuine regression worth failing on. Only `minCount == 0` carries the encoding gap.

    DORMANT since ADR-0084 decision 9 (2026-07-30), and kept anyway. The two frames it was built for
    are both `_SETUP_BENCH`, where the Pilot now declines by RULE — so both sweep pilots agree, the
    frames never reach grading, and the tally reads `unstatable 0`. The encoding gap it guards is a
    property of the Correction schema rather than of those frames, so it still holds for any future
    optional select; removing it would re-open a hole nothing else covers. Its tests exercise the
    predicate directly, not through the corpus, so they keep working while it is unexercised."""
    select = (obs.get("select") or {})
    if int(select.get("minCount") or 0) != 0:
        return False
    return sorted(rec.get("chosen") or []) == sorted(rec.get("correct") or [])


def _cell(slots, names) -> str:
    """A picked identity as a card NAME — the table is read by a human ruling flips, and
    `('card', 676)` is not a decision anyone can rule on."""
    if not slots:
        return "(no-deploy)"
    out = []
    for s in sorted(slots, key=str):
        out.append(names.get(s[1], str(s[1])) if isinstance(s, tuple) and s and s[0] == "card"
                   else str(s))
    return ",".join(out)[:14]


def _term_line(row, names) -> str:
    terms = " ".join(f"{k}={round(row[k], 2)}" for k in _TERMS if row.get(k))
    return (f"      {names.get(row.get('cid'), row.get('cid'))!s:<20} "
            f"total={round(row.get('total', 0.0), 2):>8}  cap={row.get('capacity')}"
            f"{('  [' + terms + ']') if terms else ''}")


def sweep(show_all: bool, quiet: bool = False) -> int:
    names, frames, seams = _names(), _frames(), _seams()
    hdr = (f"{'id':<14} {'agent':<13} {'NEW pick':<15} {'OLD pick':<15} {'correct':<15} "
           f"{'verdict':<12}")
    if not quiet:
        print("DEPLOY DECIDER SWEEP — new (the Bench marginal, rungs zeroed) vs old (the rungs)\n")
        print(hdr)
        print("-" * len(hdr))
    tally = defaultdict(int)
    graded = []          # per-frame verdicts — the Decision Gate's input (ADR-0072 decision 2)
    for (ep, fr), rec in frames:
        agent = _agent(rec)
        obs = rec["obs"]
        select = obs.get("select") or {}
        options = select.get("option") or []
        ctx = select.get("context")
        if not any(in_lane(o, DEPLOY_LANE, ctx) for o in options):
            continue                                   # no bench entry on the menu — outside the lane
        try:
            dec_new = _pilot(agent, new=True, seams=seams).explain(obs)
            dec_old = _pilot(agent, new=False, seams=seams).explain(obs)
        except Exception as exc:                       # a frame the shipped build can't replay
            tally["error"] += 1
            if show_all:
                print(f"{ep + '-' + str(fr):<14} {agent[:12]:<13} ERROR {exc}")
            continue
        rows = [t.deploy_working for t in dec_new.options if t.deploy_working is not None]
        correct = rec.get("correct") or []
        new_slots = lane_slots(dec_new.chosen, options, lane=DEPLOY_LANE, select_context=ctx, frame=obs)
        old_slots = lane_slots(dec_old.chosen, options, lane=DEPLOY_LANE, select_context=ctx, frame=obs)
        correct_slots = lane_slots(correct, options, lane=DEPLOY_LANE, select_context=ctx, frame=obs)
        agree = new_slots == old_slots
        tally["frames"] += 1
        if agree:
            tally["agree"] += 1
            if not show_all:
                continue
            verdict = "agree"
        else:
            tally["flip"] += 1
            # A frame whose `correct` is a NON-deploy play still labels this decision: the question it
            # answers is "bench at all?", and matching it means picking no deploy. Reading only the
            # deploy identities would score that frame "unlabelled" and hide a real regression — which
            # is exactly f51's shape (correct = play Lillie's, a Supporter).
            if correct and _records_a_decline_it_cannot_state(rec, obs):
                # An OPTIONAL select whose record says `chosen == correct` states NOTHING about
                # whether to decline, and a decline is the one answer the schema cannot hold: at
                # `decision` scope `build_correction` requires `correct` to be non-empty and to index
                # a legal option, so `correct: []` is rejected (all 10 corpus records carrying it are
                # `turn` scope). The record therefore degenerates to "the agent's own pick", and
                # grading a decider against it scores a CORRECT decline as a REGRESSION.
                #
                # ep83661652 f3 is the case — one option, `minCount 0`, and a rationale that says the
                # opposite of what the fields say: "Playing Meowth during setup doesnt allow us to use
                # Last-Ditch Catch ability, thus should be avoided when able." Three records repo-wide
                # share the shape; the dragapult f4 sibling's own note reached this independently
                # ("Degenerate record (decline is take-fewer, no index) — gate via a decline-test").
                #
                # Skipped on the RECORD's shape, not on a per-frame ruling, so no Held-out Ledger
                # entry has to invent an owner for what is a schema limit. The behaviour stays gated
                # by the decline tests that CAN state it (`test_setup_bench_decline.py`).
                verdict = "unstatable"
                tally[verdict] += 1
                if not quiet:
                    print(f"{ep + '-' + str(fr):<14} {agent[:12]:<13} "
                          f"{_cell(new_slots, names):<15} {_cell(old_slots, names):<15} "
                          f"{_cell(correct_slots, names):<15} {verdict:<12}")
                continue
            if correct:
                # A frame may record ALTERNATIVES: a set of picks the human ruled equally correct.
                # f29's ruling is the case — "bench Riolu, Makuhita, and Solrock, ordering doesn't
                # matter, just don't play ultra ball" — where the single `correct` list
                # over-specifies, because the rationale distinguishes a basic from the Ultra Ball
                # and not one basic from another. Without this the sweep scores a REGRESSION for
                # picking a body the human explicitly called correct.
                accepted = rec.get("correct_alternatives") or [correct]

                def _hit(chosen, slots) -> bool:
                    for alt in accepted:
                        alt_slots = lane_slots(alt, options, lane=DEPLOY_LANE,
                                               select_context=ctx, frame=obs)
                        if slots == alt_slots if alt_slots else (
                                not slots and set(chosen or []) & set(alt)):
                            return True
                    return False

                new_hit = _hit(dec_new.chosen, new_slots)
                old_hit = _hit(dec_old.chosen, old_slots)
                verdict = ("FIX" if new_hit and not old_hit
                           else "REGRESSION" if old_hit and not new_hit else "DIVERGENT")
            else:
                verdict = "unlabelled"
            tally[verdict] += 1
            graded.append({"key": _frame_key(rec, ep, fr), "verdict": verdict,
                           "label": rec.get("correct_label") or ""})
        if not quiet:
            print(f"{ep + '-' + str(fr):<14} {agent[:12]:<13} {_cell(new_slots, names):<15} "
                  f"{_cell(old_slots, names):<15} {_cell(correct_slots, names):<15} {verdict:<12}")
        if not agree and not quiet:
            lbl = rec.get("correct_label") or ""
            if lbl:
                print(f"      correct_label: {lbl}")
            for row in sorted(rows, key=lambda r: -r.get("total", 0.0)):
                print(_term_line(row, names))
    held_out = held_out_frames()
    passed = decision_gate_verdict(graded, held_out=held_out)
    if quiet:
        print(" ".join(f"{k}={tally[k]}" for k in ("frames", "agree", "flip", "FIX", "REGRESSION",
                                                   "DIVERGENT", "unlabelled", "unstatable")) +
              f" gate={'PASS' if passed else 'FAIL'}")
        return 0 if passed else 1
    print("\nTALLY")
    for k in ("frames", "agree", "flip", "FIX", "REGRESSION", "DIVERGENT", "unlabelled",
              "unstatable", "error"):
        print(f"  {k:<12} {tally[k]}")
    # Partition by the Held-out Ledger (ADR-0072 decision 4): a frame ruled onto another issue
    # REPORTS but does not gate. Computing the ledger and not splitting on it was the first version's
    # bug — it printed `held out 0` while a ruled frame sat in the gating list.
    regressions = [g for g in graded if g["verdict"] == "REGRESSION"]
    ok = print_gate_report("DECISION GATE (ADR-0072) — deploy decider swap",
                           gating=[g for g in regressions if g["key"] not in held_out],
                           ruled=[g for g in regressions if g["key"] in held_out],
                           held_out=held_out, total=tally["frames"],
                           rule="zero unruled REGRESSION frames",
                           line=lambda g: f"REGRESSION {g['key']}  correct={g['label']}")
    return 0 if (ok and passed) else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--all", action="store_true", help="print every frame, not only the flips")
    ap.add_argument("--quiet", action="store_true", help="one summary line + the gate verdict")
    a = ap.parse_args()
    raise SystemExit(sweep(a.all, a.quiet))
