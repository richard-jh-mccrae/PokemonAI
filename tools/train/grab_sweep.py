"""Replay every RULED `_TO_HAND` (ctx 7) correction frame through the real Pilot — ADR-0121's
validation base, and the instrument acceptance criterion 7 is graded by.

    python tools/train/grab_sweep.py                 # every agent, every ruled ctx-7 frame
    python tools/train/grab_sweep.py --agent mega_lucario
    python tools/train/grab_sweep.py --breadth       # the eligibility-breadth census (criterion 8)

For each frame it prints the human ruling, the pick BEFORE (the live trace as recorded) and the pick
AFTER (re-derived through the shipped Pilot), plus each option's grab working — the add-marginal in
Worth points, its relevance and its damage-scale total. A human rules a MOVE by reading that working,
which is why a bare total would not do (the `deploy_working` discipline, ADR-0086).

**Why a sweep of its own rather than `tune.py`.** The Discrimination Gate grades the develop-rung
LEAF and the Decision Gate grades whatever frames its baseline happens to hold; neither is scoped to
this context. ctx 7 is the second-largest non-MAIN population in the corpus (31 frames against
MAIN's 279), so it can and should be graded at its own seam — and ctx 5, the seam the Deploy
Marginal this equation is modelled on was validated at, has exactly ONE ruled frame. That is an
argument for holding this equation to the stronger bar its own population affords.
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
                w = t.grab_working or {}
                mark = "*" if t.index in (after or []) else (
                    "+" if t.index in correct else " ")
                print(f"   {mark} {_label(c.obs, t.index):22s} cid={t.card_id} "
                      f"score={t.score:8.2f} add={w.get('add_marginal', 0.0):7.2f} "
                      f"rel={w.get('add_relevance', 0.0):6.3f} tot={w.get('total', 0.0):7.2f}"
                      f"{'  [deck-priority]' if t.grab_deck_priority else ''}")
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
                rows, _i = pilot._grab_supplier_rows(obs, board, cid)
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
