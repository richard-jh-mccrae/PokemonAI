"""The three CALLER-PASSED policies the oracle takes: which survival question a harvest read answers,
which energy assumption a clock takes, and whether forward forms count.

Named so a typo is an ImportError rather than a silent ceiling. Never inferred from the board — the
conservative reading is the default."""
from __future__ import annotations



# The Harvest Readings (ADR-0071 decision 3) — WHICH survival question a caller is asking. One read
# cannot serve both; caller-passed, never inferred from the board, conservative one as the default.
HARVEST_POSSIBLE = "possible"          # in the harvest under SOME optimal allocation — threat/doom

HARVEST_UNAVOIDABLE = "unavoidable"    # ...under EVERY optimal allocation — rescue/value

#: The **doom** energy policy for :meth:`CombatMath.incoming` (Issue #260) — strictly more pessimistic
#: than the ceiling on both legs, so the ONE policy a catastrophe-grade survival boolean may take.
UNCHARGED = "uncharged"

def CURRENT_FORMS_ONLY(_card_id):
    """A forward-availability gate that admits NOTHING — "read the bodies AS THEY STAND". Named, not a
    lambda: the clock memo keys on the callable, so a fresh closure would key differently every call."""
    return ()
