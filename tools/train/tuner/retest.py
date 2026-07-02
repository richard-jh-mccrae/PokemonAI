"""Retest a Correction: how the agent would decide NOW vs how it decided live (ADR-0019).

Closes the far end of the blunder loop. Re-derives the decision under a candidate Pilot via
``Pilot.explain(correction.obs)`` and serialises it with the SAME ``telemetry.to_record`` the live
agent uses — so the ``after`` is directly comparable to the embedded live ``before``
(``correction.live_trace``). Local + instant; the full-game ladder A/B stays the real ship gate.
"""
from __future__ import annotations

from common.telemetry import to_record


def retest(correction, pilot, *, tier: int = 0) -> dict:
    """Diff the decision at this Correction's state: live ``before`` vs re-derived ``after``.

    ``fixed`` is True when every ``correct`` position is now chosen (the blunder would no longer
    occur under ``pilot``). Fields degrade to None when ``obs``/``live_trace`` are absent.
    """
    before = correction.live_trace
    after = to_record(pilot.explain(correction.obs), tier=tier) if correction.obs is not None else None
    chosen_after = after["chosen"] if after else None
    fixed = bool(after) and all(c in chosen_after for c in correction.correct)
    return {
        "before": before,
        "after": after,
        "chosen_before": (before or {}).get("chosen"),
        "chosen_after": chosen_after,
        "correct": list(correction.correct),
        "margin_before": (before or {}).get("margin"),
        "margin_after": after["margin"] if after else None,
        # Layer verdicts (ADR-0030/0031), lifted so a solver/planner fix's proof is one glance —
        # when either is non-null, scoring did NOT drive that side's pick (pilot returns early).
        "lethal_before": (before or {}).get("lethal"),
        "lethal_after": after.get("lethal") if after else None,
        "planned_before": (before or {}).get("planned"),
        "planned_after": after.get("planned") if after else None,
        "fixed": fixed,
    }
