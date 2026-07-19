"""The played-well-lost view over lost games (S3a design §D6).

A *lost* (not drawn) game for a seat is **played-well-lost** iff, after full triage over that seat's
own MAIN decisions and counterfactual confirmation of every triage hit ≥ ``theta_triage``, no
confirmed blunder with ΔV ≥ θ exists — the deck lost on dice/matchup, not on doctrine. Triage is the
cheap full-coverage screen that makes "zero flags" claimable without forking every frame.

This is a REPORT, never Corrections: a high clean-loss rate in a matchup is a doctrine/matchup-table
signal for the human and WP6's rotation loop, not a weight signal. Opponent identity is the true
``TeamNames`` (evaluation stratification only — never a training input, per S2a §D1).
"""
from __future__ import annotations

from meta_tracker.parse import winner_index
from train.label.detect import MAIN, option_disagreement, recorded_choice
from train.label.detect import _prompt_frames
from train.label.expert import evaluate_options, is_single_pick
from train.label.triage import rank_by_drop, triage_drops
from train.label.vread import agent_name_for_seat, iter_values


def _as_getter(pilot_or_getter):
    """Accept either a single Pilot (mirror corpus) or an ``agent -> Pilot`` callable (cross-deck)."""
    if callable(pilot_or_getter) and not hasattr(pilot_or_getter, "_board"):
        return pilot_or_getter
    return lambda _agent: pilot_or_getter


def _confirm(pilot, prompt_obs, decision, model, theta):
    """Counterfactually confirm a triage hit: fork the option menu, judge the recorded pick vs the
    expert's best. Returns the disagreement (with ``delta``) or None."""
    select = prompt_obs.get("select")
    if not (isinstance(select, dict) and is_single_pick(select)):
        return None
    vals = evaluate_options(pilot, prompt_obs, model)
    if not vals:
        return None
    return option_disagreement(vals, recorded_choice(pilot, decision, prompt_obs), theta)


def assess_replay(pilot_or_getter, replay: dict, model, theta: float, theta_triage: float) -> list[dict]:
    """One played-well-lost record per LOSING seat of ``replay`` (empty on a draw — no loss to
    assess). Each: ``{episode_id, seat, agent, opponent, n_decisions, n_triage_hits, n_confirmed,
    max_confirmed_delta, verdict}`` where verdict is ``clean`` (played-well-lost) or ``blundered``."""
    winner = winner_index(replay)
    if winner is None:                                 # a draw carries no loss (the simulator's delta)
        return []
    get_pilot = _as_getter(pilot_or_getter)
    frames = {d.frame: (d, po) for d, po in _prompt_frames(replay)}
    episode_id = (replay.get("info") or {}).get("EpisodeId")
    out: list[dict] = []
    for seat in (0, 1):
        if seat == winner:
            continue                                   # only the loser is assessed
        agent = agent_name_for_seat(replay, seat)
        pilot = get_pilot(agent)
        records = [r for r in iter_values(pilot, replay, model) if r["seat"] == seat]
        hits = rank_by_drop([d for d in triage_drops(records) if d["seat"] == seat], theta_triage)
        n_decisions = sum(1 for d, po in frames.values()
                          if d.seat == seat and d.select_context == MAIN)
        confirmed: list[float] = []
        for hit in hits:
            d, po = frames.get(hit["frame"], (None, None))
            if not po:
                continue
            dis = _confirm(pilot, po, d, model, theta)
            if dis is not None:
                confirmed.append(dis["delta"])
        out.append({
            "episode_id": episode_id, "seat": seat, "agent": agent,
            "opponent": agent_name_for_seat(replay, 1 - seat),
            "n_decisions": n_decisions, "n_triage_hits": len(hits),
            "n_confirmed": len(confirmed),
            "max_confirmed_delta": max(confirmed) if confirmed else 0.0,
            "verdict": "clean" if not confirmed else "blundered",
        })
    return out


def aggregate(assessments) -> dict:
    """Clean-loss rate per ``agent vs opponent`` — how often each deck lost WITHOUT a confirmed
    blunder (losing on dice/matchup, not doctrine)."""
    from collections import defaultdict

    agg: dict = defaultdict(lambda: {"losses": 0, "clean": 0})
    for a in assessments:
        cell = agg[(a["agent"], a["opponent"])]
        cell["losses"] += 1
        cell["clean"] += 1 if a["verdict"] == "clean" else 0
    return {f"{ag} vs {opp}": {
        "losses": v["losses"], "clean": v["clean"],
        "clean_loss_rate": (v["clean"] / v["losses"]) if v["losses"] else 0.0,
    } for (ag, opp), v in sorted(agg.items())}
