"""Evolve decider sweep — the per-term DIAGNOSTIC for the no-shadow swap (#140, ADR-0070). **Not a gate.**

Runs the corpus through the SHIPPED evolve decider and reports, per frame carrying an evolve option,
which body it evolves, whether that satisfies the corpus ruling, and the decider's TERM BREAKDOWN
(`deploy` / `income_gain` / `income_loss`) behind the call. The breakdown is why this file outlived
the gate it used to be — `decider_lab.py` records the decision, never the terms that produced it.

Comparison is by the resolved BODY SLOT ``(inPlayArea, inPlayIndex)``, never the raw option index —
two Dreepy→Drakloak options differ only by which body they evolve, and the index says nothing about
which.

    python tools/train/probes/evolve_decider_sweep.py            # the miss table + the tally
    python tools/train/probes/evolve_decider_sweep.py --all      # every frame, not only the misses

Offline and read-only; one engine-backed Pilot build per frame. Always exits 0: it reports, it does
not gate.

## Why the OLD arm is GONE (ADR-0085 Amendment J, 2026-07-30)

This probe used to build TWO pilots per frame — NEW (``evolve_value`` ON, the retired rungs forced to
weight 0) and OLD (``evolve_value`` OFF, the pile at its shipped weights) — and classify each
disagreement `FIX` / `REGRESSION` / `DIVERGENT`. ADR-0072 called that pairing the **Decision Gate**,
and at the swap it was right: OLD *was* the incumbent pile, so the diff measured the equation against
what it replaced.

The deletion commit ended that, as tracker directive 1 requires. **All five ids the NEW arm zeroed are
gone from `baseline_evolution`** — the two rungs left (`prefer-rush-evolve-tutor`,
`dont-rush-evolve-without-target`) are the Gates this probe's own header says were never part of the
retired set. So the zeroing override applied to ids that no longer exist, and OLD was
``evolve_value`` OFF over a pile with nothing in it: an empty scorer whose argmax falls to option
index. Measured in that state, this probe reported **4 FIX, 0 REGRESSION** — and a comparison that
cannot produce a REGRESSION is not evidence of not regressing.

Amendment I moved the gate to `tools/train/decider_lab.py diff --baseline
data/decider_lab/baseline.json`, which diffs against a RECORDED capture. Amendment J removes the dead
arm here rather than leaving a `4 FIX` line for someone to read as merit. What remains is the one
reading that means something: the shipped agent, against the human.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from train.gates import (EVOLVE_LANE, in_lane, lane_slots,  # noqa: E402
                         option_slot, satisfies_human)

_EVOLVE = 9

_TERMS = ("deploy", "income_gain", "income_loss")


def _names() -> dict:
    out = {}
    with open(REPO / "data" / "EN_Card_Data.csv", encoding="utf-8") as f:
        for r in csv.reader(f):
            if r and r[0].isdigit():
                out.setdefault(int(r[0]), r[1])
    return out


def _frames():
    """THE Corpus Reader, via the shared probe helper (ADR-0087 / ADR-0089)."""
    from train.probes._corpus import frames
    return frames()



def _agent(rec) -> str:
    """The shared replay fallback (`_corpus.replay_agent`). It is no longer papering over a missing
    `agent` — `from_dict` backfills that from `agent_build` — but it is not cosmetic either: the
    corpus holds one `SkiChu` record with no agent directory."""
    from train.probes._corpus import replay_agent
    return replay_agent(rec)


def _strategy_and_deck(agent: str):
    agent_dir = REPO / "src" / "agents" / agent
    spec = importlib.util.spec_from_file_location(f"{agent}_strategy", agent_dir / "strategy.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    deck = [int(x) for x in (agent_dir / "deck.csv").read_text(encoding="utf-8").splitlines()[:60]
            if x.strip()]
    return mod.STRATEGY, deck


def _pilot(agent: str, *, seams):
    """A fresh SHIPPED Pilot for ``agent`` — one per frame, because the Pilot is stateful (deck
    tracker, per-decision caches) and sharing one leaks a previous frame's board.

    No params are overridden and no rungs are zeroed: `common/runtime.py` resolves the single
    deployment PROFILE, and a probe that reads anything else reports an agent nobody runs."""
    from common.runtime import build_pilot
    strategy, deck = _strategy_and_deck(agent)
    return build_pilot(strategy, deck, **seams)


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


def _cell(slots) -> str:
    return f"{sorted(slots)[0]}" if slots else "(no-evolve)"


def _term_line(row) -> str:
    terms = " ".join(f"{k}={round(row[k], 2)}" for k in _TERMS if row.get(k))
    b, r = row.get("body") or {}, row.get("result") or {}
    clocks = (f"B[now={b.get('this_turn')} arm={b.get('arm')} ko={b.get('ko')}] "
              f"R[now={r.get('this_turn')} arm={r.get('arm')} ko={r.get('ko')}]")
    return (f"      slot={tuple(row['slot'])} total={round(row['tactical'], 2)}"
            f"{('  [' + terms + ']') if terms else ''}  {clocks}")


def _hits(chosen, chosen_slots, correct, correct_slots) -> bool:
    """Does the shipped pick satisfy the ruling, read through the EVOLVE lane?

    A frame whose ``correct`` is a NON-evolve play still labels this decision: the question it
    answers is *"evolve at all?"*, and matching it means picking no evolve. Reading only the evolve
    slots would score that frame "unlabelled" and hide a real miss — which is why the no-slot branch
    falls back to `satisfies_human` over the raw indices."""
    if correct_slots:
        return chosen_slots == correct_slots
    return not chosen_slots and satisfies_human(chosen, correct)


def sweep(show_all: bool, quiet: bool = False) -> int:
    names, frames, seams = _names(), _frames(), _seams()
    hdr = f"{'id':<14} {'agent':<13} {'shipped':<14} {'correct':<14} {'reading':<12}"
    if not quiet:
        print("EVOLVE DECIDER SWEEP — the shipped decider, per frame, with its term breakdown\n")
        print(hdr)
        print("-" * len(hdr))
    tally = defaultdict(int)
    misses = []
    for (ep, fr), rec in frames:
        agent = _agent(rec)
        options = (rec.obs.get("select") or {}).get("option") or []
        if not any(o.get("type") == _EVOLVE for o in options):
            continue                                   # no evolve on the menu — outside this lane
        try:
            dec = _pilot(agent, seams=seams).explain(rec.obs)
        except Exception as exc:                       # a frame the shipped build can't replay
            tally["error"] += 1
            if show_all:
                print(f"{ep + '-' + str(fr):<14} {agent[:12]:<13} ERROR {exc}")
            continue
        rows = [dict(t.evolve_working, slot=(option_slot(options[i])
                                     if in_lane(options[i], EVOLVE_LANE) else None))
                for i, t in enumerate(dec.options)
                if i < len(options) and t.evolve_working is not None]
        correct = rec.correct
        chosen_slots = lane_slots(dec.chosen, options, lane=EVOLVE_LANE)
        correct_slots = lane_slots(correct or [], options, lane=EVOLVE_LANE)
        tally["frames"] += 1
        if correct is None:
            tally["unlabelled"] += 1
            reading = "unlabelled"
        elif _hits(dec.chosen, chosen_slots, correct, correct_slots):
            tally["agree"] += 1
            reading = "agrees"
            if not show_all:
                continue
        else:
            tally["MISS"] += 1
            reading = "MISSES"
            misses.append((ep, fr))
        if not quiet:
            print(f"{ep + '-' + str(fr):<14} {agent[:12]:<13} {_cell(chosen_slots):<14} "
                  f"{_cell(correct_slots):<14} {reading:<12}")
            if reading != "agrees":
                lbl = rec.correct_label or ""
                if lbl:
                    print(f"      correct_label: {lbl}")
                for row in sorted(rows, key=lambda r: -r["tactical"]):
                    print(_term_line(row))
    if quiet:
        print(" ".join(f"{k}={tally[k]}" for k in ("frames", "agree", "MISS", "unlabelled", "error")))
        return 0
    print("\nTALLY")
    for k in ("frames", "agree", "MISS", "unlabelled", "error"):
        print(f"  {k:<12} {tally[k]}")
    print(f"\n{len(misses)} frame(s) where the shipped decider misses the ruling: "
          f"{', '.join(f'{e}-{f}' for e, f in misses) or '(none)'}")
    print("\nThis probe REPORTS, it does not gate — the Decision Gate is "
          "`decider_lab.py diff --baseline data/decider_lab/baseline.json` (ADR-0085 Amendment I).")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true", help="print every frame, not only the flips")
    ap.add_argument("--quiet", action="store_true", help="tally line only")
    a = ap.parse_args()
    raise SystemExit(sweep(a.all, quiet=a.quiet))
