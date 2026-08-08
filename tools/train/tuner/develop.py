"""Develop-rung correction classifier (ADR-0031). Reads a turn_plan Correction's live @T trace and
returns the verdict a `blunder-buster` leaf routes on, WITHOUT re-running the engine.

  - ``rung-right``      the rung committed the human's pick — a rule-RETIREMENT datum, confirmable
                        only by the R-off ladder run.
  - ``leaf-misrank``    the rung fired and committed something else: leaf fodder, unless the human's
                        reasoning is ``cross_turn``, which the within-turn leaf structurally cannot see.
  - ``rung-inactive``   the rung did not fire; greedy or a higher rung drove the pick.
  - ``no-prescription`` prose-only turn tag: nothing to compare.

``leans_on_rule`` is DERIVED from ``opts[correct].fired``, never stored, so it cannot drift.
"""
from __future__ import annotations

# Note phrases meaning the justification reaches BEYOND this turn, which the within-turn leaf
# structurally cannot see — a capability-gap, never a leaf tune.
_CROSS_TURN_MARKERS = ("next turn", "next-turn", "following turn", "turn after", "later turn",
                       "future turn", "subsequent turn")


def _opt(live_trace: dict, i: int) -> dict | None:
    return next((o for o in (live_trace.get("opts") or []) if o.get("i") == i), None)


def _leans_on_rule(live_trace: dict, correct: list) -> list:
    """Positive-weight only: these are retire-candidates when the rung reproduces the pick."""
    rules: list = []
    for i in correct or []:
        o = _opt(live_trace, i)
        for name, weight in (o or {}).get("fired") or []:
            if weight > 0 and name not in rules:
                rules.append(name)
    return rules


def _candidate_value(plan_candidates: list, step: list):
    return next((c.get("value") for c in (plan_candidates or []) if c.get("step") == step), None)


def _is_cross_turn(correction) -> bool:
    text = " ".join([(correction.rationale or ""),
                     (getattr(correction, "turn_plan", None) or {}).get("intended_line", "")]).lower()
    return any(m in text for m in _CROSS_TURN_MARKERS)


def classify_develop_correction(correction) -> dict:
    """The develop-rung verdict for a turn_plan Correction — see the module docstring for the kinds."""
    live = correction.live_trace or {}
    correct = list(correction.correct or [])
    planned = live.get("planned") or {}
    plan_candidates = live.get("plan_candidates")
    cross_turn = _is_cross_turn(correction)
    leans = _leans_on_rule(live, correct)

    base = {"correct": correct, "leans_on_rule": leans, "cross_turn": cross_turn,
            "committed": None, "committed_value": None, "correct_value": None,
            "greedy": None, "diverged": False, "overrode_greedy": False}

    if not correct:
        return {**base, "kind": "no-prescription", "route": "prose"}

    rung_fired = planned.get("goal") == "develop" and bool(plan_candidates)
    if not rung_fired:
        return {**base, "kind": "rung-inactive", "route": "planner-code"}

    committed = planned.get("step")
    greedy = next((c.get("step") for c in plan_candidates if c.get("greedy")), None)
    base.update(committed=committed, committed_value=planned.get("value"),
                correct_value=_candidate_value(plan_candidates, correct),
                greedy=greedy, diverged=bool(planned.get("diverged")))

    if committed == correct:
        return {**base, "kind": "rung-right", "route": "retire-candidate"}
    base["overrode_greedy"] = (greedy is not None and correct == greedy)
    route = "capability-gap" if cross_turn else "leaf-tune"
    return {**base, "kind": "leaf-misrank", "route": route}


def develop_batch_report(corrections) -> dict:
    """``retire_corroboration`` is EVIDENCE a rule's retirement is safe, never proof — only the R-off
    ladder run can confirm it. Non-turn_plan corrections are skipped."""
    counts: dict = {}
    retire: dict = {}
    leaf_tune, capability_gaps = [], []
    for c in corrections:
        if getattr(c, "scope", None) != "turn" or not getattr(c, "turn_plan", None):
            continue
        v = classify_develop_correction(c)
        counts[v["kind"]] = counts.get(v["kind"], 0) + 1
        if v["kind"] == "rung-right":
            for r in v["leans_on_rule"]:
                retire[r] = retire.get(r, 0) + 1
        elif v["kind"] == "leaf-misrank":
            (capability_gaps if v["cross_turn"] else leaf_tune).append(v)
    return {"counts": counts, "retire_corroboration": retire,
            "leaf_tune": leaf_tune, "capability_gaps": capability_gaps}
