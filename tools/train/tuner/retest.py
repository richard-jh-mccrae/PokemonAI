"""Retest a Correction: how the agent would decide NOW vs how it decided live (ADR-0019).

Closes the far end of the blunder loop. Re-derives the decision under a candidate Pilot via
``Pilot.explain(correction.obs)`` and serialises it with the SAME ``telemetry.to_record`` the live
agent uses — so the ``after`` is directly comparable to the embedded live ``before``
(``correction.live_trace``). Local + instant; the full-game ladder A/B stays the real ship gate.

``retest_span`` is the Turn-scope counterpart (ADR-0049): it walks the Span's Decisions in order and
stops at the **first divergence**, because every later ``obs`` was produced by the line the agent
originally played — off-policy the moment the candidate Pilot picks differently.
"""
from __future__ import annotations

from common.telemetry import to_record


def retest(correction, pilot, *, tier: int = 0) -> dict:
    """Diff the decision at this Correction's state: live ``before`` vs re-derived ``after``.

    ``fixed`` is True when every ``correct`` position is now chosen (the blunder would no longer
    occur under ``pilot``), and **None when the Correction names no ``correct``** — a prose-only
    scoped Correction (ADR-0049) asserts nothing to check, so there is nothing to be fixed. Other
    fields degrade to None when ``obs``/``live_trace`` are absent.
    """
    before = correction.live_trace
    after = to_record(pilot.explain(correction.obs), tier=tier) if correction.obs is not None else None
    chosen_after = after["chosen"] if after else None
    fixed = (None if not correction.correct
             else bool(after) and all(c in chosen_after for c in correction.correct))
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


def retest_span(correction, pilot, *, tier: int = 0) -> dict:
    """Re-drive a scoped Correction's Span under ``pilot``, up to the first divergence (ADR-0049).

    Each Span Decision that carries an ``obs`` is re-derived and its ``chosen`` compared to the line
    the agent actually played. The **first** Decision where they differ is the divergence: from there
    on the recorded ``obs`` describe a board the candidate Pilot would never have reached, so those
    steps are reported ``off_policy`` and never re-driven — the walker refuses to guess.

    A Match Correction's Span holds per-Turn headers with no ``obs``: nothing to re-drive, so
    ``steps`` is empty. That is the honest answer, and why a match blunder's gate is the ladder.
    """
    span = correction.span or []
    steps, first = [], None
    for entry in span:
        obs = entry.get("obs")
        if obs is None:
            continue
        before = entry.get("chosen")
        if first is not None:                       # past the divergence: this obs is off-policy
            steps.append({"frame": entry.get("frame"), "chosen_before": before,
                          "chosen_after": None, "diverged": False, "off_policy": True})
            continue
        after = to_record(pilot.explain(obs), tier=tier)
        chosen_after = after["chosen"] if after else None
        diverged = chosen_after != before
        if diverged:
            first = {"frame": entry.get("frame"), "chosen_before": before,
                     "chosen_after": chosen_after}
        steps.append({"frame": entry.get("frame"), "chosen_before": before,
                      "chosen_after": chosen_after, "diverged": diverged, "off_policy": False})
    return {"scope": correction.scope, "span_len": len(span), "steps": steps,
            "first_divergence": first}
