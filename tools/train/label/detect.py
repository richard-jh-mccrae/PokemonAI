"""Disagreement detection: the labeler IS the disagreement detector (s3b unifies WP3+WP4).

For each single-pick MAIN decision the expert scores the option menu (``label.expert``); where the
expert's best option beats the **chosen** option by ≥ θ in P(win), that's a disagreement to emit as a
machine Correction. The **choice provider** is the one knob that separates the two missions (§D1):

- ``recorded_choice`` — the move the build that played actually made (blunder-mining).
- ``replayed_choice`` — the *current* Pilot's pick on the same frame (s3b's expert-iteration mission).

Same expert, same θ, same emission; only the choice differs. The expert forks the **prompt obs**
``film[i].obs`` (the state AT the decision, whose option menu the recorded ``chosen`` indexes) — NOT
``Decision.obs`` (= ``film[i+1].obs``, the post-choice state vread/extract read for value training).
"""
from __future__ import annotations

from train.blunder.decisions import _film, iter_decisions
from train.label.expert import evaluate_options, is_single_pick
from train.label.triage import MAIN                     # one source of truth for SelectContext.MAIN
from train.label.vread import agent_name_for_seat


def recorded_choice(pilot, decision, prompt_obs) -> int | None:
    """The option the build that played chose (the film's recorded selection)."""
    return decision.chosen[0] if decision.chosen else None


def replayed_choice(pilot, decision, prompt_obs) -> int | None:
    """The current Pilot's pick on the prompt obs — the expert-iteration apprentice choice."""
    pick = pilot.decide(prompt_obs)
    return pick[0] if pick else None


def option_disagreement(expert_vals: dict, chosen_index, theta: float) -> dict | None:
    """A disagreement iff the expert's best option differs from ``chosen_index`` AND beats it by
    ≥ ``theta`` in P(win). None otherwise (chose the best, gap below θ, or the chosen option wasn't
    scored — a fork that was skipped, so we can't fairly judge it)."""
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
    """(decision, prompt_obs) per decision — ``prompt_obs = film[decision.frame].obs`` (the fork
    state whose menu matches ``decision.options``)."""
    film = _film(replay)
    for d in iter_decisions(replay):
        prompt = film[d.frame].get("obs") if 0 <= d.frame < len(film) else None
        yield d, prompt


def detect_disagreements(pilot, replay: dict, model, theta: float, *, choose=recorded_choice,
                         seat: int | None = None):
    """Yield a disagreement dict per single-pick MAIN decision where the ``choose``-n option loses to
    the expert's best by ≥ θ. Each carries the source ``Decision`` (for emission) plus provenance
    fields (episode/frame/seat/turn/agent). ``model`` must be present (expert raises on a null model).

    ``seat`` restricts detection to one seat's decisions — so a cross-deck game is driven twice, once
    per seat with that seat's own Pilot (a mirror needs only one pass)."""
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
