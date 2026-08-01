"""The shared GRADING convention — how a value decays over the turns until it lands.

One halving rule and one horizon, read by every decider that grades a future quantity, so a
re-tuning on one equation cannot silently re-open another. Extracted from `evolve_value` when the
promote/retreat equation became its second reader (ADR-0100 §4: "`_halve` and `_HORIZON` are REUSED
from `evolve_value` … they move to a shared module now that two equations read them").

Deliberately NOT `common/value/`, which holds the LEARNED value model (`model.py`,
`value_model.json`) — a grading convention is arithmetic every equation shares, not a fitted
artefact (ADR-0100 §Build entailments).

Neither name is a tunable:

* :data:`HORIZON` mirrors ``turns_to_ko_me``'s own "survives the horizon" answer (``max_t + 1``), so
  it tracks the clock rather than asserting a second opinion about it.
* :func:`halve` is the shipped convention `deny_slot` already used (``value / 2**t``), reused rather
  than a new decay rate invented per equation (ADR-0070 §6).
"""
from __future__ import annotations

#: Turns of survival beyond which nothing on the board threatens the body — `turns_to_ko_me`'s
#: "survives the horizon" answer (``max_t + 1``). Not a tunable: it mirrors the clock's own horizon.
HORIZON = 9


def halve(turns: float) -> float:
    """The shipped grading convention — `deny_slot`'s ``value / 2**t``, reused rather than a new
    decay rate invented for each equation (ADR-0070 §6).

    ``turns`` is clamped at 0, so a quantity landing NOW (or already overdue) is undiscounted rather
    than inflated above its face value by a negative exponent."""
    return 0.5 ** max(0.0, float(turns))
