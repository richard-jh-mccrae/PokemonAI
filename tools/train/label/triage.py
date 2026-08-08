"""Triage: consecutive-decision Φ-deltas that rank fork budget but never label (S3a §D2).

The drop at decision ``k`` is ``V_k − V_{k+1}`` over a seat's own MAIN decisions in film order.
Crossing to the seat's *next* own decision folds in the opponent's reply and any coin luck, so a big
drop is **suspicious, not proven** — triage produces a ranking only, and is outcome-blind.
"""
from __future__ import annotations

from cg.api import SelectContext

MAIN = int(SelectContext.MAIN)


def triage_drops(value_records, contexts=(MAIN,)) -> list[dict]:
    """Per-seat consecutive-decision drops, ``drop = v − v_next``. A seat's last decision has none and is omitted."""
    kept: dict[int, list[dict]] = {}
    for r in sorted(value_records, key=lambda x: x["frame"]):
        if r.get("context") in contexts:
            kept.setdefault(r["seat"], []).append(r)
    out: list[dict] = []
    for seat, recs in kept.items():
        for cur, nxt in zip(recs, recs[1:]):
            out.append({
                "episode_id": cur["episode_id"], "seat": seat, "agent": cur["agent"],
                "frame": cur["frame"], "turn": cur["turn"], "v": cur["v"],
                "frame_next": nxt["frame"], "v_next": nxt["v"], "drop": cur["v"] - nxt["v"],
            })
    out.sort(key=lambda d: (d["seat"], d["frame"]))
    return out


def rank_by_drop(drops, theta_triage: float) -> list[dict]:
    """The drops with ``drop >= theta_triage``, largest first. Gains (the position improved) never rank."""
    return sorted((d for d in drops if d["drop"] >= theta_triage),
                  key=lambda d: d["drop"], reverse=True)
