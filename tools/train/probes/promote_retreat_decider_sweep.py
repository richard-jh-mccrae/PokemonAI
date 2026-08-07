"""Promote/retreat sweep — the per-term DIAGNOSTIC for the no-shadow swap (ADR-0100). **Not a gate.**

Runs the corpus through the SHIPPED promote/retreat decider and reports what it does per frame,
whether that satisfies the corpus ruling, and the TERM BREAKDOWN behind the call. Comparison is by
resolved BODY SLOT, never the raw option index (ADR-0100 §12).

Two site families, because the mass lives in both and they compare differently: **pick** (a TO_ACTIVE
forced promote or a SWITCH retreat destination — ``PROMOTE_LANE``, and the comparison is which BODY)
and **whether** (a MAIN menu carrying a native RETREAT — a membership test on `chosen`, not a slot).

    python tools/train/probes/promote_retreat_decider_sweep.py [--all] [--quiet]

Offline and read-only. Always exits 0. The Decision Gate is `decider_lab.py diff --baseline
data/decider_lab/baseline.json` (ADR-0085 Amendment I).
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

from train.gates import PROMOTE_LANE, lane_slots, option_slot   # noqa: E402

_MAIN, _SWITCH, _TO_ACTIVE = 0, 3, 4
_RETREAT, _PLAY = 12, 7

_TERMS = ("my_yield", "closure", "exposure", "tempo_denied", "fatal", "preservation", "retreat_cost")


def _names() -> dict:
    out = {}
    with open(REPO / "data" / "EN_Card_Data.csv", encoding="utf-8") as f:
        for r in csv.reader(f):
            if r and r[0].isdigit():
                out.setdefault(int(r[0]), r[1])
    return out


def _frames():
    from train.probes._corpus import frames
    return frames()



def _agent(rec) -> str:
    """The shared replay fallback — not cosmetic: one corpus record has no agent directory."""
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
    """A fresh SHIPPED Pilot per frame — the Pilot is stateful and sharing one pollutes verdicts. No
    params overridden, no rungs zeroed: a probe reading anything but the PROFILE reports no agent."""
    from common.runtime import build_pilot
    strategy, deck = _strategy_and_deck(agent)
    return build_pilot(strategy, deck, **seams)


def _seams():
    """The knowledge seams, built ONCE — immutable, so sharing them is safe where sharing a Pilot is not."""
    from common.scouting.artifact import load_artifact
    from common.scouting.briefs import load_briefs
    from common.scouting.provider import EngineCardStatProvider
    from common.scouting.scout import Scout
    stats = EngineCardStatProvider()
    stats.warm()
    return {"stats": stats, "scout": Scout(load_artifact(), provider=stats),
            "briefs": load_briefs()}


def _site(options, ctx) -> str | None:
    """Which of ADR-0100 §9's comparable sites this frame is, or None if it is neither."""
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
    hdr = f"{'id':<14} {'agent':<13} {'site':<8} {'shipped':<14} {'correct':<14} {'reading':<12}"
    if not quiet:
        print("PROMOTE/RETREAT DECIDER SWEEP — the shipped decider, per frame, with its terms\n")
        print(hdr)
        print("-" * len(hdr))
    tally = defaultdict(int)
    misses = []
    for (ep, fr), rec in frames:
        options = (rec.obs.get("select") or {}).get("option") or []
        ctx = (rec.obs.get("select") or {}).get("context")
        site = _site(options, ctx)
        if site is None:
            continue                                   # outside this family
        agent = _agent(rec)
        try:
            dec = _pilot(agent, seams=seams).explain(rec.obs)
        except Exception as exc:                       # a frame the shipped build can't replay
            tally["error"] += 1
            if show_all:
                print(f"{ep + '-' + str(fr):<14} {agent[:12]:<13} {site:<8} ERROR {exc}")
            continue
        correct = rec.correct
        if site == "pick":
            got = lane_slots(dec.chosen, options, lane=PROMOTE_LANE, select_context=ctx)
            cor_v = lane_slots(correct or [], options, lane=PROMOTE_LANE, select_context=ctx)
            labelled = bool(cor_v)
            hit = got == cor_v
        else:
            # The whether-site question is "retreat at all?", which is a membership test on the
            # chosen set — a slot comparison cannot express "stayed".
            def _retreated(chosen) -> bool:
                return any(0 <= i < len(options) and options[i].get("type") == _RETREAT
                           for i in (chosen or []))
            got, cor_v = _retreated(dec.chosen), _retreated(correct)
            # `correct: []` is a recorded DECLINE, not an absent label — it rules "do not retreat",
            # which `_retreated([])` already reads as False. Only a MISSING `correct` is unlabelled.
            labelled = correct is not None
            hit = got == cor_v
        rows = [dict(t.promote_retreat_working,
                     slot=option_slot(options[i]) if i < len(options) else None,
                     card_id=(options[i] or {}).get("cardId"))
                for i, t in enumerate(dec.options)
                if i < len(options) and getattr(t, "promote_retreat_working", None) is not None]
        tally["frames"] += 1
        tally[f"frames:{site}"] += 1
        if not labelled:
            tally["unlabelled"] += 1
            reading = "unlabelled"
        elif hit:
            tally["agree"] += 1
            reading = "agrees"
            if not show_all:
                continue
        else:
            tally["MISS"] += 1
            reading = "MISSES"
            misses.append((ep, fr))
        if not quiet:
            print(f"{ep + '-' + str(fr):<14} {agent[:12]:<13} {site:<8} {_cell(got):<14} "
                  f"{(_cell(cor_v) if labelled else '(none)'):<14} {reading:<12}")
            if reading != "agrees":
                lbl = rec.correct_label or ""
                if lbl:
                    print(f"      correct_label: {lbl}")
                for row in sorted(rows, key=lambda r: -r["total"]):
                    print(_term_line(row, names))
    keys = ("frames", "frames:pick", "frames:whether", "agree", "MISS", "unlabelled")
    if quiet:
        print(" ".join(f"{k}={tally[k]}" for k in keys))
        return 0
    print("\nTALLY")
    for k in keys + ("error",):
        print(f"  {k:<16} {tally[k]}")
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
