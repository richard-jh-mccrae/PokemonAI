"""Triage: consecutive-decision Φ-deltas that rank fork budget but never label (S3a design §D2).

For each seat, over its own MAIN decisions in film order, the triage drop at decision ``k`` is
``V_k − V_{k+1}`` — the Suphx Φ-delta shape. Crossing to the seat's *next* own decision folds the
opponent's reply and any coin luck into the drop, so a big triage drop is **suspicious, not proven**:
triage produces a ranking only. Two consumers, both in the design:

1. Fork-budget ranking — the counterfactual expert (``detect``) spends its budget on the biggest
   triage drops first (a stratum added for the labeler mission; s3b's ambiguity/uniform strata stand).
2. The played-well-lost screen (``report``) — a cheap full-coverage pass so "zero flags" is a
   meaningful claim without forking every frame.

Outcome-blind by construction: it never looks at who won (a blunder in a won game still ranks).
"""
from __future__ import annotations

from cg.api import SelectContext

MAIN = int(SelectContext.MAIN)


def triage_drops(value_records, contexts=(MAIN,)) -> list[dict]:
    """Per-seat consecutive-decision drops over ``value_records`` (vread's output).

    Keeps only records whose ``context`` is in ``contexts`` (MAIN by default — the strategic
    choices), groups by seat, and pairs each kept decision with the seat's *next* kept decision in
    film order. Yields one drop dict per adjacent pair::

        {episode_id, seat, agent, frame, turn, v, frame_next, v_next, drop}   # drop = v − v_next

    A seat's final decision has no successor and is omitted (no drop to measure).
    """
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
    """The drops with ``drop ≥ theta_triage``, largest first — the fork-budget order. Gains
    (negative drops: the position improved) never rank."""
    return sorted((d for d in drops if d["drop"] >= theta_triage),
                  key=lambda d: d["drop"], reverse=True)
