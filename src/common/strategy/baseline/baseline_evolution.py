"""BASELINE cluster: EVOLUTION — what survives the evolve-decider swap (ADR-0070 §10, #140).

The four rungs that PRICED an evolve are DELETED, not suppressed: `evolve-into-wincon` (+40) and
`advance-the-evolution-line` (+15) are the decider's deploy term, and both `+5` energized tie-breaks
are EMERGENT — an energized body's clocks are nearer, so its evolve delta is naturally larger, which
is the whole thing they were compensating for. The dragapult `hold-evolution-until-attacker-ready`
(-46) deck rung goes with them: it is `income_loss` (via /deck-align, ADR-0034).

What remains is the `_PLAY` side, which prices a TUTOR rather than an evolve — structure, not value.
`dont-rush-evolve-without-target` is a Gate: structural ABSENCE (no pre-evolution in play means
nothing to evolve), not a valuation, and it must keep its `_CLASS_B_SPEND_IDS` membership or the
develop-rollout planner's spend account loses a term. Pure data, no Mixin.
"""
from common.strategy.context import _EVOLVE, _PLAY, _WINCON_ROLES
from common.strategy.strategy import Hypothesis, Plan

HYPOTHESES = [
    Hypothesis(
        id="prefer-rush-evolve-tutor",
        rationale="A `rush_evolve` tutor (e.g. Salvatore: fetch a Pokémon and evolve it the same turn "
                  "its pre-evolution was played) collapses two setup turns into one, so prefer it — "
                  "gated on a pre-evolution already in play, the payoff not already in hand (mirrors "
                  "`play-a-tutor-for-the-unfound-wincon`'s `not wincon_in_hand` gate), and the evolution "
                  "target not provably exhausted from the deck (`search_targets_exhausted`; without this "
                  "gate the +30 would swamp `dont-search-an-empty-deck`'s -60 — ep83117367).",
        when=lambda c: not c.board.line_ready and c.option_type == _PLAY and "rush_evolve" in c.tags
        and c.board.line_preevo_in_play and not c.board.wincon_in_hand
        and not c.search_targets_exhausted,
        weight=30, status="testing"),
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
