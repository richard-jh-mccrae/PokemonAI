"""Replay every RULED `_TO_HAND` (ctx 7) correction frame through the real Pilot — the seam-scoped
gate the grab has lacked (ADR-0121, Issue #406).

    python tools/train/grab_sweep.py                 # every agent, every ruled ctx-7 frame
    python tools/train/grab_sweep.py --agent mega_lucario
    python tools/train/grab_sweep.py --breadth       # the eligibility-breadth census

For each frame it prints the human ruling, the pick BEFORE (the live trace as recorded) and the pick
AFTER (re-derived through the shipped Pilot), plus each option's score and the rungs that fired — or,
when a grab EQUATION is wired, its legible working instead. A human rules a MOVE by reading that,
which is why a bare pick would not do (the `deploy_working` discipline, ADR-0086).

**Why a sweep of its own rather than `tune.py`.** The Discrimination Gate grades the develop-rung
LEAF and the Decision Gate grades whatever frames its baseline happens to hold; neither is scoped to
this context. ctx 7 is the second-largest non-MAIN population in the corpus (31 frames against
MAIN's 279, of which 30 name a `correct` option), so it can and should be graded at its own seam.

**It exists because it caught something.** Issue #406 proposed replacing the 23 `_TO_HAND` rungs
with a `needs.keep_v2` add-marginal. Built to spec and run here, the equation scored **17/30**
against the incumbent ladder's **23/30** — and at four times its band, **14**, below doing nothing
at all. Nothing about that was visible from the seam's own unit tests, which all passed. The build
is preserved at commit `bd9187d7` and ADR-0121 records the five structural findings; this tool now
grades whatever the successor proposes, and the incumbent in the meantime.

Note the asymmetry ADR-0121 closes on, because it is the reason to run this at all: ctx 5 — the
`_TO_BENCH` seam whose Deploy Marginal that equation was modelled on — has exactly ONE ruled corpus
frame. A design validated at one frame was carried onto a seam with thirty.
"""
from __future__ import annotations

import argparse
import statistics
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from train.blunder.store import load_corrections  # noqa: E402
from train.tuner.retest import retest  # noqa: E402
import importlib

_TO_HAND = 7


def _ctx7(store: str) -> list:
    """Every correction whose select is a `_TO_HAND` search — read off the OBS the frame carries,
    never off the human-written `select_context` label, which is prose."""
    out = []
    for c in load_corrections(store):
        sel = ((c.obs or {}).get("select") or {})
        if sel.get("context") == _TO_HAND:
            out.append(c)
    return out


def _label(obs, i: int) -> str:
    opts = ((obs or {}).get("select") or {}).get("option") or []
    if not (0 <= i < len(opts)):
        return f"#{i}"
    o = opts[i]
    return f"#{i}(area={o.get('area')},idx={o.get('index')})"


def sweep(agent_filter: str | None, store: str) -> int:
    tune = importlib.import_module("train.tune")
    corrs = _ctx7(store)
    if agent_filter:
        corrs = [c for c in corrs if c.agent == agent_filter]
    by_agent: dict = {}
    for c in corrs:
        by_agent.setdefault(c.agent, []).append(c)

    moved, held, unruled = [], [], []
    for agent, group in sorted(by_agent.items()):
        pilot, _seeds = tune._build_pilot(agent)
        for c in sorted(group, key=lambda x: (x.episode_id, (x.decision or {}).get("frame"))):
            key = f"{c.episode_id}-{(c.decision or {}).get('frame')}"
            r = retest(c, pilot)
            after = (r.get("after") or {}).get("chosen")
            before = (r.get("before") or {}).get("chosen")
            correct = list(c.correct or [])
            print(f"\n=== {agent} {key}  ({c.category}) ===")
            print(f"  ruling  : {correct} {c.correct_label!r}")
            print(f"  before  : {before}   after: {after}   fixed: {r.get('fixed')}")
            dec = pilot.explain(c.obs)
            for t in dec.options:
                # `grab_working` is populated only while a grab EQUATION is wired. It is absent on
                # `main` (Issue #406's build was measured worse and reverted, ADR-0121), so the
                # sweep degrades to score + fired rungs rather than breaking — which is exactly the
                # view needed to grade the incumbent ladder it now measures.
                w = getattr(t, "grab_working", None) or {}
                mark = "*" if t.index in (after or []) else (
                    "+" if t.index in correct else " ")
                extra = (f" add={w['add_marginal']:7.2f} tot={w['total']:7.2f}"
                         if w else f" fired={[h.id for h, _ in t.fired]}")
                print(f"   {mark} {_label(c.obs, t.index):22s} cid={t.card_id} "
                      f"score={t.score:8.2f}{extra}")
            if not correct:
                unruled.append((agent, key))
            elif r.get("fixed"):
                held.append((agent, key))
            else:
                moved.append((agent, key, correct, after))

    print("\n" + "=" * 78)
    print(f"ruled ctx-7 frames : {len(corrs)}")
    print(f"  agreeing         : {len(held)}")
    print(f"  MOVED off ruling : {len(moved)}")
    for a, k, correct, after in moved:
        print(f"      {a} {k}: ruling {correct} -> {after}")
    if unruled:
        print(f"  no ruling recorded: {len(unruled)} {unruled}")
    return 0


def breadth(agent_filter: str | None, store: str) -> int:
    """Acceptance criterion 8: the MEASURED eligibility-breadth distribution at both keep_v2 sites.

    `needs._keep_slot_dp` is exponential in eligible-slot BREADTH (how many slots one card can
    supply), not in the slot count its `_MAX_KEEP_SLOTS` bound caps — 1.6 ms at breadth 1 against
    748 ms at the declared bound of 16. Cost here is therefore safe only because real hands are
    SPARSE, and a property that holds by luck should be checked rather than assumed.

    Both sites are censused because the exposure is not confined to the new one: `pilot._needs_v2`
    already runs one `keep_v2` per hand row at every forced discard, and that path DECIDES."""
    tune = importlib.import_module("train.tune")
    corrs = _ctx7(store)
    if agent_filter:
        corrs = [c for c in corrs if c.agent == agent_filter]
    by_agent: dict = {}
    for c in corrs:
        by_agent.setdefault(c.agent, []).append(c)

    widths: list = []
    slot_counts: list = []
    for agent, group in sorted(by_agent.items()):
        pilot, _seeds = tune._build_pilot(agent)
        for c in group:
            obs = c.obs
            board = pilot._board(obs, (obs.get("select") or {}))
            sel = obs.get("select") or {}
            for o in (sel.get("option") or []):
                cid = pilot._option_card_id(obs, sel, o)
                if cid is None:
                    continue
                rows = pilot._needs_hand_rows(obs, board)
                rows = rows + [{"i": len(rows), "cid": cid,
                                "worth": round(pilot._role_value(cid), 1),
                                "deploy": 1.0, "fuel": False}]
                slots, elig = pilot._resolve_needs(obs, board, rows, include_general=True)
                slot_counts.append(len(slots))
                widths.extend(len(e) for e in elig)
    if not widths:
        print("no frames measured")
        return 1
    hist = Counter(widths)
    print("eligibility breadth (slots one card can supply), ctx-7 grab site:")
    for k in sorted(hist):
        print(f"  {k:3d} : {hist[k]:5d}")
    print(f"  max={max(widths)}  mean={statistics.mean(widths):.2f}  n={len(widths)}")
    print(f"slot count per resolve: max={max(slot_counts)} mean={statistics.mean(slot_counts):.1f}")
    return 0


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", default=None)
    ap.add_argument("--store", default=str(REPO / "data" / "corrections"))
    ap.add_argument("--breadth", action="store_true")
    args = ap.parse_args(argv)
    return (breadth if args.breadth else sweep)(args.agent, args.store)


if __name__ == "__main__":
    raise SystemExit(main())
