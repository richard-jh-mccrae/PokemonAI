"""Evolve DECIDER sweep — the batched review's input for the no-shadow swap (#140, ADR-0070).

The sibling of ``attach_decider_sweep.py``, same protocol (ADR-0069 §8): run the corpus through
BOTH evolve deciders while both still exist and report every frame where they disagree, with the new
decider's TERM BREAKDOWN on each side of the flip. No decision may flip silently — the human rules on
the WHY, one sitting, one table, BEFORE the deletion commit retires the rungs for good.

The two pilots, built fresh per frame (pilots are stateful; sharing one pollutes verdicts):

  * NEW — ``evolve_value`` ON with the retired ``baseline_evolution`` rungs (and dragapult's
    ``hold-evolution`` deck rung) forced to weight 0. That is exactly the post-deletion agent.
    Zeroing rather than deleting is what lets this run BEFORE the deletion commit.
  * OLD — ``evolve_value`` OFF with every rung at its shipped weight: the pile as it decides today.

Comparison is by the resolved BODY SLOT ``(inPlayArea, inPlayIndex)``, never the raw option index —
two Dreepy→Drakloak options differ only by which body they evolve, and the index says nothing about
which. ``correct`` (the human label, where the frame has one) is shown on both sides so a flip reads
as a FIX, a REGRESSION, or a no-label judgement call.

    python tools/train/probes/evolve_decider_sweep.py            # the flip table + the tally
    python tools/train/probes/evolve_decider_sweep.py --all      # every frame, not only the flips

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

_EVOLVE = 9

#: The rungs the evolve decider retires (ADR-0070 §10). Forced to 0 in the NEW pilot so this probe
#: measures the post-deletion agent without needing the deletion first. The two `_PLAY`-side rungs
#: are NOT here: `dont-rush-evolve-without-target` survives as a Gate (and must keep its Class-B
#: spend-account membership), and `prefer-rush-evolve-tutor` folds to the equation in the deletion
#: commit rather than simply disappearing, so zeroing it here would measure neither agent.
RETIRED = (
    "evolve-into-wincon",
    "advance-the-evolution-line",
    "evolve-the-energized-body-first",
    "advance-the-energized-line-body-first",
    "hold-evolution-until-attacker-ready",      # the dragapult deck rung -> income_loss
)

_TERMS = ("deploy", "income_gain", "income_loss")


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
    """A fresh shipped Pilot for ``agent`` in NEW (decider-only) or OLD (rung-only) mode."""
    from common.runtime import build_pilot
    strategy, deck = _strategy_and_deck(agent)
    params = dict(strategy.params)
    params["evolve_value"] = bool(new)
    overrides = {hid: 0 for hid in RETIRED} if new else None
    return build_pilot(strategy, deck, params=params, overrides=overrides, **seams)


def _seams():
    """Build the engine-backed knowledge seams ONCE and inject them into every Pilot — immutable card
    knowledge, so sharing them is safe where sharing a Pilot is not."""
    from common.scouting.artifact import load_artifact
    from common.scouting.briefs import load_briefs
    from common.scouting.provider import EngineCardStatProvider
    from common.scouting.scout import Scout
    stats = EngineCardStatProvider()
    stats.warm()
    return {"stats": stats, "scout": Scout(load_artifact(), provider=stats),
            "briefs": load_briefs()}


def _opt_slot(option: dict) -> tuple | None:
    """The BODY an evolve option targets — which is the whole content of the pick."""
    if option.get("type") != _EVOLVE:
        return None
    return (option.get("inPlayArea"), option.get("inPlayIndex"))


def _slots(indices, options) -> set:
    out = set()
    for i in indices or []:
        if 0 <= i < len(options):
            s = _opt_slot(options[i])
            if s is not None:
                out.add(s)
    return out


def _cell(slots) -> str:
    return f"{sorted(slots)[0]}" if slots else "(no-evolve)"


def _term_line(row) -> str:
    terms = " ".join(f"{k}={round(row[k], 2)}" for k in _TERMS if row.get(k))
    b, r = row.get("body") or {}, row.get("result") or {}
    clocks = (f"B[now={b.get('this_turn')} arm={b.get('arm')} ko={b.get('ko')}] "
              f"R[now={r.get('this_turn')} arm={r.get('arm')} ko={r.get('ko')}]")
    return (f"      slot={tuple(row['slot'])} total={round(row['tactical'], 2)}"
            f"{('  [' + terms + ']') if terms else ''}  {clocks}")


def sweep(show_all: bool, quiet: bool = False) -> None:
    names, frames, seams = _names(), _frames(), _seams()
    hdr = (f"{'id':<14} {'agent':<13} {'NEW pick':<14} {'OLD pick':<14} {'correct':<14} "
           f"{'verdict':<12}")
    if not quiet:
        print("EVOLVE DECIDER SWEEP — new (body-substituted delta, rungs zeroed) vs old (the rungs)\n")
        print(hdr)
        print("-" * len(hdr))
    tally = defaultdict(int)
    flips = []
    for (ep, fr), rec in frames:
        agent = _agent(rec)
        options = (rec["obs"].get("select") or {}).get("option") or []
        if not any(o.get("type") == _EVOLVE for o in options):
            continue                                   # no evolve on the menu — outside this lane
        try:
            dec_new = _pilot(agent, new=True, seams=seams).explain(rec["obs"])
            dec_old = _pilot(agent, new=False, seams=seams).explain(rec["obs"])
        except Exception as exc:                       # a frame the shipped build can't replay
            tally["error"] += 1
            if show_all:
                print(f"{ep + '-' + str(fr):<14} {agent[:12]:<13} ERROR {exc}")
            continue
        rows = [dict(t.evolve_working, slot=_opt_slot(options[i]))
                for i, t in enumerate(dec_new.options)
                if i < len(options) and t.evolve_working is not None]
        correct = rec.get("correct") or []
        new_slots = _slots(dec_new.chosen, options)
        old_slots = _slots(dec_old.chosen, options)
        correct_slots = _slots(correct, options)
        agree = new_slots == old_slots
        tally["frames"] += 1
        if agree:
            tally["agree"] += 1
            if not show_all:
                continue
            verdict = "agree"
        else:
            tally["flip"] += 1
            # A frame whose `correct` is a NON-evolve play still labels this decision: the question
            # it answers is "evolve at all?", and matching it means picking no evolve. Reading only
            # the evolve slots would score that frame "unlabelled" and hide a real regression.
            if correct:
                new_hit = (new_slots == correct_slots if correct_slots
                           else not new_slots and set(dec_new.chosen or []) & set(correct))
                old_hit = (old_slots == correct_slots if correct_slots
                           else not old_slots and set(dec_old.chosen or []) & set(correct))
                verdict = ("FIX" if new_hit and not old_hit
                           else "REGRESSION" if old_hit and not new_hit else "DIVERGENT")
            else:
                verdict = "unlabelled"
            tally[verdict] += 1
        if not quiet:
            print(f"{ep + '-' + str(fr):<14} {agent[:12]:<13} {_cell(new_slots):<14} "
                  f"{_cell(old_slots):<14} {_cell(correct_slots):<14} {verdict:<12}")
        if not agree:
            flips.append((ep, fr))
            if not quiet:
                lbl = rec.get("correct_label") or ""
                if lbl:
                    print(f"      correct_label: {lbl}")
                for row in sorted(rows, key=lambda r: -r["tactical"]):
                    print(_term_line(row))
    if quiet:
        print(" ".join(f"{k}={tally[k]}" for k in ("frames", "agree", "flip", "FIX", "REGRESSION",
                                                   "DIVERGENT", "unlabelled")))
        return
    print("\nTALLY")
    for k in ("frames", "agree", "flip", "FIX", "REGRESSION", "DIVERGENT", "unlabelled", "error"):
        print(f"  {k:<12} {tally[k]}")
    print(f"\n{len(flips)} frame(s) need a user ruling before the deletion commit: "
          f"{', '.join(f'{e}-{f}' for e, f in flips) or '(none)'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true", help="print every frame, not only the flips")
    ap.add_argument("--quiet", action="store_true", help="tally line only")
    a = ap.parse_args()
    sweep(a.all, quiet=a.quiet)
