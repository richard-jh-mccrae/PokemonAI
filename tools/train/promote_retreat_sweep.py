"""Promote/retreat shadow — offline disagreement sweep (docs/plans/promote-retreat-grill-spec.md).

Replays every RECORDED promote/retreat SELECT frame in the correction corpus through a FRESH Pilot
(standing caution), reads the reporting-only `promote_retreat_shadow` record (its pick + agreement
bit vs the shipped rung ladder), and ranks the disagreement rows — the evidence bridge the
shadow-equations ruling calls for. NO fresh ladder submission: it reads the already-recorded corpus.

A disagreement row is `shadow.eq_pick != ladder.chosen`. Where a human `correct` label is present it
is tagged SHADOW-FIXES-LADDER (shadow right, ladder wrong — swap-motivating), shadow-regresses,
both-right, or both-wrong. Boss's-gust-target selects (opponent bodies on a _SWITCH) are excluded by
the shadow itself — that is the gust-value equation's turf.

Run: `python tools/train/promote_retreat_sweep.py`
"""
from __future__ import annotations

import ast
import glob
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "tools"))

_SWITCH, _TO_ACTIVE, _MAIN, _RETREAT = 3, 4, 0, 12


def _build_pilot(agent: str):
    spec = importlib.util.spec_from_file_location("tune_mod", REPO / "tools" / "train" / "tune.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._build_pilot(agent)[0]


def _first(x):
    return (x[0] if x else None) if isinstance(x, list) else x


def _gather_frames() -> dict:
    """Unique promote/retreat SELECT frames, keyed episode-frame. Filters on the obs select context
    (the reliable int) — the recorded `decision.select_context` is a string label."""
    frames: dict = {}
    for f in glob.glob(str(REPO / "data" / "corrections" / "*" / "corrections.jsonl")):
        for line in open(f, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            dec = o.get("decision")
            dec = ast.literal_eval(dec) if isinstance(dec, str) else dec
            obs = o.get("obs")
            obs = ast.literal_eval(obs) if isinstance(obs, str) else obs
            if not (isinstance(dec, dict) and isinstance(obs, dict)):
                continue
            sel = obs.get("select") or {}
            ctx = sel.get("context")
            if ctx in (_SWITCH, _TO_ACTIVE):
                pass
            elif ctx == _MAIN and any(op.get("type") == _RETREAT for op in (sel.get("option") or [])):
                pass                                       # a MAIN menu carrying a native retreat action
            else:
                continue
            key = f"{o.get('episode_id')}-{dec.get('frame')}"
            frames.setdefault(key, {"agent": o.get("agent"), "obs": obs,
                                    "correct": o.get("correct"), "cat": o.get("category"),
                                    "rat": (o.get("rationale") or "")[:80]})
    return frames


def _tag(r: dict) -> str:
    if r["correct"] is None:
        return "no-label"
    if r["shadow_right"] and not r["ladder_right"]:
        return "SHADOW-FIXES-LADDER"
    if not r["shadow_right"] and r["ladder_right"]:
        return "shadow-regresses"
    if r["shadow_right"] and r["ladder_right"]:
        return "both-right"
    return "both-wrong"


def main() -> None:
    frames = _gather_frames()
    print(f"promote/retreat + MAIN-retreat frames in corpus: {len(frames)}")
    rows, skipped = [], 0
    for key, fr in frames.items():
        try:
            d = _build_pilot(fr["agent"]).explain(fr["obs"])   # FRESH pilot per replay
        except Exception:
            skipped += 1
            continue
        rec = getattr(d, "promote_retreat_shadow", None)
        if not rec:                                            # <2 opts / gust select / mid-sim / no dest
            skipped += 1
            continue
        correct = _first(fr["correct"])
        opts = fr["obs"]["select"]["option"]
        base = {"key": key, "agent": fr["agent"], "cat": fr["cat"], "site": rec["site"],
                "agree": rec["agree"], "rat": fr["rat"]}
        if rec["site"] == "pick":
            shadow, ladder = rec["eq_pick"], (d.chosen[0] if d.chosen else None)
            base.update(shadow=shadow, ladder=ladder, correct=correct, eq=rec["eq"],
                        shadow_right=(shadow == correct) if correct is not None else None,
                        ladder_right=(ladder == correct) if correct is not None else None)
        else:                                                  # whether-to-retreat (sign agreement)
            cor_retreat = (opts[correct].get("type") == _RETREAT) if (correct is not None
                           and correct < len(opts)) else None
            base.update(value=rec["value"], worth_it=rec["worth_it"],
                        ladder=rec["ladder_retreated"], correct=cor_retreat,
                        shadow=rec["worth_it"],
                        shadow_right=(rec["worth_it"] == cor_retreat) if cor_retreat is not None else None,
                        ladder_right=(rec["ladder_retreated"] == cor_retreat) if cor_retreat is not None else None)
        rows.append(base)

    for site in ("pick", "whether"):
        srows = [r for r in rows if r["site"] == site]
        disagree = [r for r in srows if not r["agree"]]
        print(f"\n===== SITE: {site} =====")
        print(f"  priced: {len(srows)}   agree vs ladder: {sum(r['agree'] for r in srows)}/{len(srows)}"
              f"   disagree: {len(disagree)}")
        order = {"SHADOW-FIXES-LADDER": 0, "both-wrong": 1, "no-label": 2, "both-right": 3, "shadow-regresses": 4}
        for r in sorted(disagree, key=lambda r: order[_tag(r)]):
            extra = (f"value={r.get('value')} worth_it={r.get('worth_it')}" if site == "whether"
                     else f"eq={r.get('eq')}")
            print(f"  {r['key']:15} {r['agent']:13} {_tag(r):20} shadow={r['shadow']} "
                  f"ladder={r['ladder']} correct={r['correct']} | {r['cat']}")
            print(f"      {extra} | {r['rat']}")
        print(f"  disagreement verdicts: {dict(Counter(_tag(r) for r in disagree))}")
    print(f"\nskipped (gust/unpriced/no-dest): {skipped}")


if __name__ == "__main__":
    main()
