"""BASELINE cluster: SEQUENCING — within-turn play ordering (ADR-0025). Dig (draw/search) before
irreversible commitments. Pure data, no Mixin. (The free-dig family; `_finish_turn_last` in the Pilot
handles attack-last sequencing structurally.)
"""
from common.strategy.context import _PLAY
from common.strategy.strategy import Hypothesis, Plan

HYPOTHESES = [
    Hypothesis(
        id="dig-before-commit",
        rationale="Play draw and search cards before ending your turn — they cost nothing and see "
                  "more of your deck: during setup, dig before irreversible plays like attaching "
                  "Energy; while racing, dig before the turn-ending attack (you still attack the "
                  "same turn — see `_finish_turn_last`). Free card advantage every turn. Stands down "
                  "for a discard-COST search (`cost_discard`, e.g. Ultra Ball pays 2 cards from hand): "
                  "that dig is NOT free, so it earns no free-dig bonus — its real (cost-aware) value "
                  "is left to dedicated rules, and `_finish_turn_last` sequences it as a commitment. "
                  "Also stands down for a Shuffle-Refresh (`shuffle_hand`, e.g. Lillie's Determination): "
                  "it DESTROYS the hand to redraw, the opposite of a dig — so it earns no early-dig bonus "
                  "and is governed by the separate Shuffle-Refresh doctrine (dead-hand fallback), not here.",
        when=lambda c: c.plan in (Plan.SETUP, Plan.RACE) and c.option_type == _PLAY
        and ("draw" in c.tags or "search" in c.tags)
        and "cost_discard" not in c.tags and "shuffle_hand" not in c.tags,
        weight=20, status="assumed"),
]
