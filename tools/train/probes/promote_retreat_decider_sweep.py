"""Promote/retreat DECIDER sweep — the batched review's input for the no-shadow swap (#141, ADR-0073).

The sibling of ``evolve_decider_sweep.py`` / ``attach_decider_sweep.py``, same protocol (ADR-0069 §8):
run the corpus through BOTH promote/retreat deciders while both still exist and report every frame
where they disagree, with the new decider's TERM BREAKDOWN on each side of the flip. No decision may
flip silently — the human rules on the WHY, one sitting, one table, BEFORE the deletion commit
retires the rungs for good.

This REPLACES ``tools/train/promote_retreat_sweep.py``, which is not merely stale but unrunnable: it
reads a `promote_retreat_shadow` record and a `worth_it` SIGN BIT, and ADR-0073 decision 2 retires
both — deleting `stay_forgone` turns the whether-site verdict from a sign test into a per-option
score, so there is no sign left to agree with.

The two pilots, built fresh per frame (pilots are stateful; sharing one pollutes verdicts):

  * NEW — ``promote_retreat_value`` ON with the eleven retired rungs forced to weight 0. That is
    exactly the post-deletion agent. Zeroing rather than deleting is what lets this run BEFORE the
    deletion commit.
  * OLD — ``promote_retreat_value`` OFF with every rung at its shipped weight: the pile as it decided.

Comparison is by the resolved BODY SLOT, never the raw option index — two promote options differ only
in which body they bring up, and the index says nothing about which (ADR-0073 §12).

Two site families, because the family's mass lives in BOTH and they compare differently:

  * **pick** — a TO_ACTIVE forced promote or a SWITCH retreat destination. The lane is ``PROMOTE_LANE``
    and the comparison is which BODY each agent picks.
  * **whether** — a MAIN menu carrying a native RETREAT (or a switch-class Item). The comparison is
    whether each agent RETREATS at all, which is a membership test on `chosen`, not a slot.

Deleting the `active_can_ko` recusal returns the 24 frames the shadow withdrew from, so the
whether-site corpus goes from 72 priced back to ~96 (ADR-0073 §12).

    python tools/train/probes/promote_retreat_decider_sweep.py          # the flip table + the tally
    python tools/train/probes/promote_retreat_decider_sweep.py --all    # every frame, not only flips

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

from train.gates import (PROMOTE_LANE, decision_gate_verdict, frame_key_of,  # noqa: E402
                         held_out_frames, lane_slots, option_slot, print_gate_report)

_MAIN, _SWITCH, _TO_ACTIVE = 0, 3, 4
_RETREAT, _PLAY = 12, 7

#: The rungs the promote/retreat decider retires (ADR-0073 §11) — eleven of twelve. Forced to 0 in
#: the NEW pilot so this probe measures the post-deletion agent without needing the deletion first.
#: `retreat-to-wall-the-line` is deliberately ABSENT: it survives as #165's Maneuver, so zeroing it
#: would measure neither agent.
RETIRED = (
    "promote-the-ko-attacker",
    "promote-the-accelerator-for-the-ko",
    "promote-the-ready-wincon",
    "dont-promote-onto-their-path",
    "interpose-the-cheap-attacker-to-preserve-the-wincon",
    "dont-promote-into-their-prize-reach",
    "promote-the-staller",
    "retreat-to-ready-attacker",
    "swap-out-the-locked-attacker",
    "dont-play-switch-for-no-gain",
    "hold-position-in-setup",
)

_TERMS = ("my_yield", "closure", "exposure", "tempo_denied", "fatal", "preservation", "retreat_cost")


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
    """The frame's stable identity, in the SAME form the Leaf Lab and the Held-out Ledger use — the
    Correction's `identity_key`. One key shape across both gates is what lets a single ruling hold a
    frame out of either."""
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
    """A fresh shipped Pilot for ``agent`` in NEW (decider-only) or OLD (rung-only) mode."""
    from common.runtime import build_pilot
    strategy, deck = _strategy_and_deck(agent)
    params = dict(strategy.params)
    params["promote_retreat_value"] = bool(new)
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


def _site(options, ctx) -> str | None:
    """Which of ADR-0073 §9's comparable sites this frame is, or None if it is neither."""
    if ctx in (_TO_ACTIVE, _SWITCH):
        return "pick"
    if ctx == _MAIN and any(o.get("type") == _RETREAT for o in options):
        return "whether"
    return None


def _cell(value) -> str:
    if isinstance(value, (set, frozenset)):
        return f"{sorted(value)[0]}" if value else "(no-promote)"
    return "RETREAT" if value else "stay"


def _term_line(row, names) -> str:
    terms = " ".join(f"{k}={row[k]}" for k in _TERMS if row.get(k))
    body = names.get(row.get("card_id"), row.get("card_id"))
    return (f"      slot={row['slot']} {str(body)[:22]:<22} total={row['total']}"
            f"{('  [' + terms + ']') if terms else ''}")


def sweep(show_all: bool, quiet: bool = False) -> int:
    names, frames, seams = _names(), _frames(), _seams()
    hdr = (f"{'id':<14} {'agent':<13} {'site':<8} {'NEW':<14} {'OLD':<14} {'correct':<14} "
           f"{'verdict':<12}")
    if not quiet:
        print("PROMOTE/RETREAT DECIDER SWEEP — new (sub-lethal residual, rungs zeroed) "
              "vs old (the rungs)\n")
        print(hdr)
        print("-" * len(hdr))
    tally = defaultdict(int)
    flips, graded = [], []
    for (ep, fr), rec in frames:
        options = (rec["obs"].get("select") or {}).get("option") or []
        ctx = (rec["obs"].get("select") or {}).get("context")
        site = _site(options, ctx)
        if site is None:
            continue                                   # outside this family
        agent = _agent(rec)
        try:
            dec_new = _pilot(agent, new=True, seams=seams).explain(rec["obs"])
            dec_old = _pilot(agent, new=False, seams=seams).explain(rec["obs"])
        except Exception as exc:                       # a frame the shipped build can't replay
            tally["error"] += 1
            if show_all:
                print(f"{ep + '-' + str(fr):<14} {agent[:12]:<13} {site:<8} ERROR {exc}")
            continue
        correct = rec.get("correct") or []
        if site == "pick":
            new_v = lane_slots(dec_new.chosen, options, lane=PROMOTE_LANE, select_context=ctx)
            old_v = lane_slots(dec_old.chosen, options, lane=PROMOTE_LANE, select_context=ctx)
            cor_v = lane_slots(correct, options, lane=PROMOTE_LANE, select_context=ctx)
            labelled = bool(cor_v)
        else:
            # The whether-site question is "retreat at all?", which is a membership test on the
            # chosen set — a slot comparison cannot express "stayed".
            def _retreated(chosen) -> bool:
                return any(0 <= i < len(options) and options[i].get("type") == _RETREAT
                           for i in (chosen or []))
            new_v, old_v = _retreated(dec_new.chosen), _retreated(dec_old.chosen)
            cor_v, labelled = _retreated(correct), bool(correct)
        rows = [dict(t.promote_retreat_working,
                     slot=option_slot(options[i]) if i < len(options) else None,
                     card_id=(options[i] or {}).get("cardId"))
                for i, t in enumerate(dec_new.options)
                if i < len(options) and getattr(t, "promote_retreat_working", None) is not None]
        agree = new_v == old_v
        tally["frames"] += 1
        tally[f"frames:{site}"] += 1
        if agree:
            tally["agree"] += 1
            if not show_all:
                continue
            verdict = "agree"
        else:
            tally["flip"] += 1
            if labelled:
                new_hit, old_hit = new_v == cor_v, old_v == cor_v
                verdict = ("FIX" if new_hit and not old_hit
                           else "REGRESSION" if old_hit and not new_hit else "DIVERGENT")
            else:
                verdict = "unlabelled"
            tally[verdict] += 1
            graded.append({"key": _frame_key(rec, ep, fr), "verdict": verdict, "site": site,
                           "label": rec.get("correct_label") or ""})
        if not quiet:
            print(f"{ep + '-' + str(fr):<14} {agent[:12]:<13} {site:<8} {_cell(new_v):<14} "
                  f"{_cell(old_v):<14} {_cell(cor_v) if labelled else '(none)':<14} {verdict:<12}")
        if not agree:
            flips.append((ep, fr))
            if not quiet:
                lbl = rec.get("correct_label") or ""
                if lbl:
                    print(f"      correct_label: {lbl}")
                for row in sorted(rows, key=lambda r: -r["total"]):
                    print(_term_line(row, names))
    held_out = held_out_frames()
    passed = decision_gate_verdict(graded, held_out=held_out)
    keys = ("frames", "frames:pick", "frames:whether", "agree", "flip", "FIX", "REGRESSION",
            "DIVERGENT", "unlabelled")
    if quiet:
        print(" ".join(f"{k}={tally[k]}" for k in keys) +
              f" gate={'PASS' if passed else 'FAIL'}")
        return 0 if passed else 1
    print("\nTALLY")
    for k in keys + ("error",):
        print(f"  {k:<16} {tally[k]}")
    print(f"\n{len(flips)} frame(s) need a user ruling before the deletion commit: "
          f"{', '.join(f'{e}-{f}' for e, f in flips) or '(none)'}")

    # DECISION GATE (ADR-0072 decision 2): zero unruled REGRESSION. Held-out frames still RUN and
    # still REPORT — a re-ruling is a state the gate reads, not prose in a review doc, and a frame
    # broken for three phases must not become scenery (decision 4). ADR-0073 §12 adds no gate of its
    # own: there is NO disagreement-rate pass mark, which supersedes the issue's grill agenda item 4.
    regressions = [g for g in graded if g["verdict"] == "REGRESSION"]
    ruled = [g for g in regressions if g["key"] in held_out]
    unruled = [g for g in regressions if g["key"] not in held_out]
    print_gate_report(f"DECISION GATE — {len(graded)} labelled flip(s) graded",
                      gating=unruled, ruled=ruled, held_out=held_out, total=len(graded),
                      rule="zero unruled REGRESSION",
                      line=lambda g: f"REGRESSION [{g['site']}] {g['key']}  {g['label']}")
    return 0 if passed else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true", help="print every frame, not only the flips")
    ap.add_argument("--quiet", action="store_true", help="tally line only")
    a = ap.parse_args()
    raise SystemExit(sweep(a.all, quiet=a.quiet))
