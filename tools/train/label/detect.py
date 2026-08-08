"""Disagreement detection: the labeler IS the disagreement detector (s3b unifies WP3+WP4).

The **choice provider** is the one knob separating the two missions: ``recorded_choice``
(blunder-mining) versus ``replayed_choice`` (expert iteration). The expert forks the **prompt obs**
``film[i].obs`` — whose menu the recorded ``chosen`` indexes — NOT the post-choice ``Decision.obs``.
"""
from __future__ import annotations

from train.blunder.decisions import _film, iter_decisions
from train.label.expert import evaluate_options, is_single_pick
from train.label.triage import MAIN                     # one source of truth for SelectContext.MAIN
from train.label.vread import agent_name_for_seat


def recorded_choice(pilot, decision, prompt_obs) -> int | None:
    return decision.chosen[0] if decision.chosen else None


def replayed_choice(pilot, decision, prompt_obs) -> int | None:
    pick = pilot.decide(prompt_obs)
    return pick[0] if pick else None


def option_disagreement(expert_vals: dict, chosen_index, theta: float) -> dict | None:
    """A disagreement iff the expert's best differs from ``chosen_index`` AND beats it by >= ``theta``."""
    if not expert_vals or chosen_index is None or chosen_index not in expert_vals:
        return None
    best = max(expert_vals, key=lambda k: expert_vals[k])
    delta = expert_vals[best] - expert_vals[chosen_index]
    if delta <= 0.0 or delta < theta:
        return None                                    # a tie (best co-equal with chosen) is not a blunder
    return {
        "correct": best, "chosen": chosen_index, "delta": delta,
        "v_best": expert_vals[best], "v_chosen": expert_vals[chosen_index],
        "v_table": {k: round(v, 4) for k, v in sorted(expert_vals.items())},
    }


def _prompt_frames(replay: dict):
    film = _film(replay)
    for d in iter_decisions(replay):
        prompt = film[d.frame].get("obs") if 0 <= d.frame < len(film) else None
        yield d, prompt


def detect_disagreements(pilot, replay: dict, model, theta: float, *, choose=recorded_choice,
                         seat: int | None = None):
    """One disagreement per single-pick MAIN decision where ``choose``'s option loses by >= θ; ``seat`` scopes it."""
    for decision, prompt_obs in _prompt_frames(replay):
        if decision.select_context != MAIN or not prompt_obs:
            continue
        if seat is not None and decision.seat != seat:
            continue
        select = prompt_obs.get("select")
        if not isinstance(select, dict) or not is_single_pick(select):
            continue
        expert_vals = evaluate_options(pilot, prompt_obs, model)
        if not expert_vals:
            continue
        dis = option_disagreement(expert_vals, choose(pilot, decision, prompt_obs), theta)
        if dis is None:
            continue
        dis.update(episode_id=decision.episode_id, frame=decision.frame, seat=decision.seat,
                   turn=decision.turn, agent=agent_name_for_seat(replay, decision.seat),
                   decision=decision)
        yield dis
