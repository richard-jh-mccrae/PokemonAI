"""BASELINE cluster: EVOLUTION — what survives the evolve-decider swap (ADR-0070 §10, #140).

The four rungs that PRICED an evolve are DELETED, not suppressed: `evolve-into-wincon` (+40) and
`advance-the-evolution-line` (+15) are the decider's deploy term, and both `+5` energized tie-breaks
are EMERGENT — an energized body's clocks are nearer, so its evolve delta is naturally larger, which
is the whole thing they were compensating for. The dragapult `hold-evolution-until-attacker-ready`
(-46) deck rung goes with them: it is `income_loss` (via /deck-align, ADR-0034).

`prefer-rush-evolve-tutor` (+30) is FOLDED rather than simply deleted: a rush-evolve tutor's worth IS
the evolve it buys a turn early, which the decider can now compute, so it becomes
`pilot._rush_evolve_tutor_tactical` — the equation over the hypothetical result. Its three premises
survive there as structural gates, unchanged.

What remains here is ONE rung, and it is a Gate rather than a valuation:
`dont-rush-evolve-without-target` reads structural ABSENCE (no pre-evolution in play means nothing to
evolve), and it must keep its `_CLASS_B_SPEND_IDS` membership or the develop-rollout planner's spend
account loses a term. Pure data, no Mixin.
"""
from common.strategy.context import _EVOLVE, _PLAY, _WINCON_ROLES
from common.strategy.strategy import Hypothesis, Plan

HYPOTHESES = [
    Hypothesis(
        id="dont-rush-evolve-without-target",
        rationale="A `rush_evolve` tutor (e.g. Salvatore) whiffs with no pre-evolution in play to "
                  "evolve — penalise the play so the agent attaches/develops instead. Pushes it below "
                  "an endorsed attach and below 0 (sequenced last); complements `prefer-rush-evolve-tutor`, "
                  "which already just stands down in this case.",
        when=lambda c: c.option_type == _PLAY and "rush_evolve" in c.tags
        and not c.board.line_preevo_in_play,
        weight=-60, status="testing"),
]
