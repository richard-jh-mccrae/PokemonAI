"""The three CALLER-PASSED policies the oracle takes, named rather than spelled: which survival question a harvest read
answers, which energy assumption a clock takes, and whether forward forms count.

Named so a consumer picks one by import and a typo is an ImportError rather than a silent ceiling. Never inferred from
the board — the conservative reading is the default, and choosing the other one is a decision somebody made on
purpose."""
from __future__ import annotations



# The Harvest Readings (ADR-0071 decision 3) — WHICH survival question a caller is asking. One read
# cannot serve both: per-body worst case is conservative for a THREAT read (it over-counts their
# reach) and inflationary for a RESCUE read (it over-credits saving one body), and those pull
# opposite ways. Caller-passed, never inferred from the board — the same convention as `charged`
# (ADR-0064 Decision 1) and `my_benched` (ADR-0070 §9), with the conservative one as the default.
HARVEST_POSSIBLE = "possible"          # in the harvest under SOME optimal allocation — threat/doom

HARVEST_UNAVOIDABLE = "unavoidable"    # ...under EVERY optimal allocation — rescue/value

#: The **doom** energy policy for :meth:`CombatMath.incoming` (POC-T1, Issue #260 — the fold of the
#: legacy `incoming_active_damage` / `forward_incoming_damage` pair). Named rather than a magic
#: string so a consumer picks it by import and a typo is an ImportError, not a silent ceiling.
#: Semantics live on :meth:`CombatMath.incoming`; the short version is *strictly more pessimistic
#: than the ceiling*, on both legs, which is why it is the ONE policy a catastrophe-grade survival
#: boolean may take (`sound_rules`: `doom-ceiling-fail-direction`).
UNCHARGED = "uncharged"

def CURRENT_FORMS_ONLY(_card_id):
    """A forward-availability gate that admits NOTHING — "read the bodies AS THEY STAND".

    A named module-level callable rather than an inline ``lambda`` at each call site, for two
    reasons: the clock memo keys on the callable itself, so a fresh closure per call would key
    differently every time; and one spelling of "no forward forms" is one place to read about why a
    caller wanted that. The live consumer is `Board.incoming_active_damage`, which asks what the body
    in FRONT of me hits for today (a +HP Tool's survival breakpoint) rather than what its line
    becomes — the forward leg is `active_doomed`'s question, not that field's.
    """
    return ()
