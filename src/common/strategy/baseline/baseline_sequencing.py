"""BASELINE cluster: SEQUENCING — within-turn play ordering (ADR-0025). Dig (draw/search) before
irreversible commitments. Pure data, no Mixin. (The free-dig family; `_finish_turn_last` in the Pilot
handles attack-last sequencing structurally.)
"""
from common.strategy.context import _PLAY
from common.strategy.strategy import Hypothesis, Plan

HYPOTHESES = [
    Hypothesis(
        id="dig-before-commit",
        rationale="Play free draw/search before irreversible commitments (Energy attach in setup, the "
                  "turn-ending attack while racing — `_finish_turn_last` still attacks same turn) since "
                  "they cost nothing and see more deck. Stands down for discard-cost search "
                  "(`cost_discard`, not free); DOES endorse Shuffle-Refresh (`shuffle_hand`) as a "
                  "hand-cycling draw — ADR-0024's 'only when hand is dead' premise was REFUTED "
                  "2026-06-30 (hoarding cost ~3:1 in the mega_starmie mirror).",
        when=lambda c: c.plan in (Plan.SETUP, Plan.RACE) and c.option_type == _PLAY
        and ("draw" in c.tags or "search" in c.tags)
        and "cost_discard" not in c.tags,
        weight=20, status="assumed"),
]
