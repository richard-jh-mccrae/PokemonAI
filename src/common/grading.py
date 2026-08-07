"""The shared GRADING convention — how a value decays over the turns until it lands.

ONE halving rule and ONE horizon, read by every decider that grades a future quantity, so a re-tune
on one equation cannot silently re-open another. Neither name is a tunable: HORIZON mirrors
``turns_to_ko_me``'s own answer, and `halve` is the shipped `deny_slot` convention (ADR-0070 §6).

Deliberately NOT `common/value/`, which holds the LEARNED value model — this is arithmetic every
equation shares, not a fitted artefact (ADR-0100 §Build entailments).
"""
from __future__ import annotations

#: Turns of survival beyond which nothing on the board threatens the body — `turns_to_ko_me`'s
#: "survives the horizon" answer (``max_t + 1``). Not a tunable: it mirrors the clock's own horizon.
HORIZON = 9


def halve(turns: float) -> float:
    """``value / 2**t``. ``turns`` is CLAMPED at 0, so a quantity landing now or already overdue is
    undiscounted rather than inflated by a negative exponent."""
    return 0.5 ** max(0.0, float(turns))
