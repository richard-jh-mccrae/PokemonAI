"""Replay every RULED `_TO_HAND` (ctx 7) correction frame through the real Pilot (ADR-0122).

    python tools/train/grab_sweep.py [--agent mega_lucario] [--breadth]

Per frame it prints the human ruling, the pick before and after, and each option's score with the
rungs that fired (or a wired grab equation's working). A human rules a MOVE by reading that, which
is why a bare pick would not do.
"""
from __future__ import annotations

import argparse
import statistics
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from train.blunder import off_policy as _off_policy_mod  # noqa: E402
from train.blunder.store import load_corrections  # noqa: E402
from train.tuner.retest import retest  # noqa: E402
import importlib

_TO_HAND = 7

#: Frames the developer ruled off-policy — a derived view of `train.blunder.off_policy.RULINGS`,
#: kept because this module's docstring and ADR-0122 both name it.
_RULED_OFF_POLICY = frozenset(
    key for key, ruling in _off_policy_mod.RULINGS.items()
    if ruling.verdict == _off_policy_mod.OFF_POLICY)


def _ctx7(store: str) -> list:
    """Every correction whose select is a `_TO_HAND` search — off the OBS, never the human-written label."""
    out = []
    for c in load_corrections(store):
        sel = ((c.obs or {}).get("select") or {})
        if sel.get("context") == _TO_HAND:
            out.append(c)
    return out


def _off_policy(c, by_ep: dict) -> list:
    """Why this follow-up frame is UNGRADEABLE, or `[]`. A CANDIDATE list; a `RULINGS` entry makes it a verdict."""
    return _off_policy_mod.reasons(c, by_ep)


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
    by_ep: dict = {}
    for c in load_corrections(store):
        by_ep.setdefault((c.agent, c.episode_id), []).append(c)
    by_agent: dict = {}
    for c in corrs:
        by_agent.setdefault(c.agent, []).append(c)

    moved, held, unruled, offpolicy = [], [], [], []
    for agent, group in sorted(by_agent.items()):
        pilot, _seeds = tune._build_pilot(agent)
        for c in sorted(group, key=lambda x: (x.episode_id, (x.decision or {}).get("frame"))):
            key = f"{c.episode_id}-{(c.decision or {}).get('frame')}"
            r = retest(c, pilot)
            after = (r.get("after") or {}).get("chosen")
            before = (r.get("before") or {}).get("chosen")
            correct = list(c.correct or [])
            stale = _off_policy(c, by_ep)
            print(f"\n=== {agent} {key}  ({c.category}) ==="
                  + ("   [OFF-POLICY — NOT GRADED]" if stale else ""))
            if stale:
                print(f"  ungradeable: {'; '.join(stale)}")
            print(f"  ruling  : {correct} {c.correct_label!r}")
            print(f"  before  : {before}   after: {after}   fixed: {r.get('fixed')}")
            dec = pilot.explain(c.obs)
            for t in dec.options:
                # `grab_working` is populated only while a grab EQUATION is wired; it is absent on
                # `main`, so the sweep degrades to score + fired rungs rather than breaking.
                w = getattr(t, "grab_working", None) or {}
                mark = "*" if t.index in (after or []) else (
                    "+" if t.index in correct else " ")
                extra = (f" add={w['add_marginal']:7.2f} tot={w['total']:7.2f}"
                         if w else f" fired={[h.id for h, _ in t.fired]}")
                print(f"   {mark} {_label(c.obs, t.index):22s} cid={t.card_id} "
                      f"score={t.score:8.2f}{extra}")
            if not correct:
                unruled.append((agent, key))
            elif stale:
                offpolicy.append((agent, key, r.get("fixed")))
            elif r.get("fixed"):
                held.append((agent, key))
            else:
                moved.append((agent, key, correct, after))

    print("\n" + "=" * 78)
    print(f"ctx-7 frames seen         : {len(corrs)}")
    print(f"  no ruling recorded      : {len(unruled)}")
    print(f"  OFF-POLICY (not graded) : {len(offpolicy)}")
    for a, k, fixed in offpolicy:
        print(f"      {a} {k}  (would have read fixed={fixed})")
    graded = len(held) + len(moved)
    print(f"\n  GRADEABLE               : {graded}")
    print(f"      agreeing            : {len(held)}")
    print(f"      MOVED off ruling    : {len(moved)}")
    for a, k, correct, after in moved:
        print(f"          {a} {k}: ruling {correct} -> {after}")
    print("\nOff-policy frames are EXCLUDED, not failed: the play that opened the select was itself")
    print("ruled wrong, so the board is one the agent should never have reached and its grab is not")
    print("evidence about the grab. See `_off_policy` — the corpus scan is sound but INCOMPLETE, so")
    print("a frame reported gradeable may still be off-policy for a reason nobody filed.")
    return 0


def breadth(agent_filter: str | None, store: str) -> int:
    """The MEASURED eligibility-breadth distribution at both `keep_v2` sites. `needs._keep_slot_dp` is
    exponential in eligible-slot BREADTH, so the cost is safe only because real hands are SPARSE."""
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
