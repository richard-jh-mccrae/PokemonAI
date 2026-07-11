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

# AreaType values (see src/cg/api.py) — hardcoded so retest never imports the native `cg` lib.
_ACTIVE, _BENCH = 4, 5


def _body_sig(obs, option):
    """The interchangeability signature — ``(card_id, energies, hp)`` — of the in-play Pokémon an
    option targets, or ``None`` when the option does not resolve to a board body (a hand/deck/effect
    option never matches by body). Two options with the SAME signature are indistinguishable picks."""
    try:
        area, idx = option.get("area"), option.get("index")
        if area not in (_ACTIVE, _BENCH):
            return None
        bodies = obs["current"]["players"][option.get("playerIndex", 0)][
            "active" if area == _ACTIVE else "bench"]
        if not (isinstance(idx, int) and 0 <= idx < len(bodies)):
            return None
        body = bodies[idx]
        if not isinstance(body, dict):
            return None
        return (body.get("id"), tuple(sorted(body.get("energies") or [])), body.get("hp"))
    except (KeyError, IndexError, TypeError):
        return None


def _is_fixed(correct, chosen_after, obs):
    """Whether the blunder is resolved: every ``correct`` slot is now chosen, OR the agent chose an
    option targeting a board body INDISTINGUISHABLE from it (same card + attached energy + HP). The
    body reconciliation is the duplicate-species case — f75 offers two byte-identical bench Riolus,
    so picking either satisfies the doctrine (the strict-index bar re-flagged the equally-valid twin).
    An energized copy vs a bare one differ in ``energies`` → NOT interchangeable, so the guard never
    masks a real positional miss. ``None`` when the Correction names no ``correct`` (ADR-0049)."""
    if not correct:
        return None
    if not chosen_after:
        return False
    if all(c in chosen_after for c in correct):
        return True
    options = ((obs or {}).get("select") or {}).get("option") or []

    def sig(i):
        return _body_sig(obs, options[i]) if 0 <= i < len(options) else None

    chosen_sigs = [sig(i) for i in chosen_after]
    for c in correct:
        cs = sig(c)
        if c in chosen_after or (cs is not None and cs in chosen_sigs):
            continue
        return False
    return True


def retest(correction, pilot, *, tier: int = 0) -> dict:
    """Diff the decision at this Correction's state: live ``before`` vs re-derived ``after``.

    ``fixed`` is True when every ``correct`` position is now chosen (or an indistinguishable
    duplicate-species twin of it — see ``_is_fixed``), and **None when the Correction names no
    ``correct``** — a prose-only scoped Correction (ADR-0049) asserts nothing to check, so there is
    nothing to be fixed. Other fields degrade to None when ``obs``/``live_trace`` are absent.
    """
    before = correction.live_trace
    after = to_record(pilot.explain(correction.obs), tier=tier) if correction.obs is not None else None
    chosen_after = after["chosen"] if after else None
    fixed = _is_fixed(correction.correct, chosen_after, correction.obs)
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
