"""Develop-rung correction classifier — the Phase-3 consumer's machine core (ADR-0031 / develop rung;
`docs/plans/phase3-tooling.md`).

A turn-scope Correction that carries a `turn_plan` note is a develop-rung correction: the human tagged
an ideal line on a setup/development turn. `classify_develop_correction` reads its live @T trace
(`plan_candidates`, `planned`, per-option `fired`) and the note, and returns the verdict a
`blunder-buster` leaf routes on — WITHOUT re-running the engine (the rung's ranking is already in the
trace on an armed-ON game).

The verdict kinds:
  - ``rung-right``     — the rung committed the human's ``correct`` pick. A rule-retirement DATUM: the
                         rung reproduced what the tuned rules would; the rules ``correct`` leans on are
                         retire-candidates (confirmed only by the R-off ladder run — the Catch-22).
  - ``leaf-misrank``   — the rung fired but committed a DIFFERENT pick than ``correct``; its leaf ranked
                         a board the human rejects above the human's. Phase-0 leaf fodder — unless the
                         human's reasoning is ``cross_turn`` (beyond the within-turn leaf), which is a
                         capability-gap, not a leaf tune.
  - ``rung-inactive``  — the rung did not fire here (no develop ``planned`` / no ``plan_candidates``):
                         greedy or a higher rung drove the pick. Route by the existing turn-scope logic.
  - ``no-prescription``— the note names no ``correct`` option (prose-only turn tag): nothing to compare.

``leans_on_rule`` is DERIVED from ``opts[correct].fired`` (positive-weight rules only), never stored —
so it can't drift from the live trace. ``cross_turn`` is a keyword read of the note/rationale.
"""
from __future__ import annotations

# Phrases in the human's note/rationale that mean the justification reaches BEYOND this turn — the
# within-turn leaf structurally cannot see it, so a leaf tune can't fix it (it is a capability-gap).
_CROSS_TURN_MARKERS = ("next turn", "next-turn", "following turn", "turn after", "later turn",
                       "future turn", "subsequent turn")


def _opt(live_trace: dict, i: int) -> dict | None:
    return next((o for o in (live_trace.get("opts") or []) if o.get("i") == i), None)


def _leans_on_rule(live_trace: dict, correct: list) -> list:
    """The positive-weight rules that fired on the human's ``correct`` option(s) — the rules the pick
    currently leans on (retire-candidates when the rung reproduces the pick). Derived from ``fired``."""
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
    """Aggregate the develop-rung verdicts across a batch of turn_plan Corrections — the Phase-3
    report a `blunder-buster` leaf/report reads. Buckets:

    - ``counts``               — verdict kind → count.
    - ``retire_corroboration`` — rule → how many ``rung-right`` corrections leaned on it (the rung
      REPRODUCED that rule's pick on a real board: evidence its retirement is safe, to be CONFIRMED by
      the R-off ladder run — the Catch-22 means the trace alone can't prove it).
    - ``leaf_tune``            — within-turn leaf mis-ranks (the leaf can be fixed to rank right).
    - ``capability_gaps``      — cross-turn leaf mis-ranks (the within-turn leaf structurally can't
      fix; the rung should not have overridden — a gate/horizon concern, not a leaf tune).

    Only turn_plan corrections are considered (others are skipped); ``leaf_tune``/``capability_gaps``
    carry the per-correction verdict so the reader can act without re-deriving it.
    """
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
