"""BASELINE cluster: SEQUENCING — within-turn play ordering (ADR-0025). Dig (draw/search) before
irreversible commitments. Pure data, no Mixin. (The free-dig family; `_finish_turn_last` in the Pilot
handles attack-last sequencing structurally.)
"""
from common.strategy.context import _PLAY
from common.strategy.strategy import Hypothesis

HYPOTHESES = [
    Hypothesis(
        id="dig-before-commit",
        rationale="Play free draw/search before irreversible commitments (Energy attach in setup, the "
                  "turn-ending attack while racing — `_finish_turn_last` still attacks same turn) since "
                  "they cost nothing and see more deck. Stands down for discard-cost search "
                  "(`cost_discard`, not free); DOES endorse Shuffle-Refresh (`shuffle_hand`) as a "
                  "hand-cycling draw — ADR-0024's 'only when hand is dead' premise was REFUTED "
                  "2026-06-30 (hoarding cost ~3:1 in the mega_starmie mirror).",
        when=lambda c: c.option_type == _PLAY
        and ("draw" in c.tags or "search" in c.tags)
        and "cost_discard" not in c.tags,
        weight=20, status="assumed"),
    Hypothesis(
        id="dont-play-damage-boost-when-cant-attack",
        rationale="A flat this-turn attack-damage boost (Premium Power Pro / Black Belt's Training / Maximum "
                  "Belt — `CardStat.damageBoost > 0`) is worth NOTHING unless you attack this turn, and its "
                  "effect expires at end of turn — so don't play it when the Active can't pay any attack this "
                  "turn (`not active_attack_payable`): the guaranteed-dead case (turn-1-going-first can't "
                  "attack, or an unpowered Active with no Energy to reach a cost). The boost would be "
                  "discarded having buffed nothing (ep83966336 f14: two Premium Power Pro over End with a "
                  "0-Energy Riolu and no Energy in hand). −12 nets it below End; silent whenever an attack IS "
                  "affordable, so a real pre-attack boost keeps its tactical value (`_boost_lethal_tactical`).",
        when=lambda c: c.option_type == _PLAY and c.stat is not None
        and getattr(c.stat, "damageBoost", 0) > 0 and not c.board.active_attack_payable,
        weight=-12, status="assumed"),
]
