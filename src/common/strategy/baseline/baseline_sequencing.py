"""BASELINE cluster: SEQUENCING — within-turn play ordering (ADR-0025). Dig (draw/search) before
irreversible commitments. Pure data, no Mixin. (The free-dig family; `_finish_turn_last` in the Pilot
handles attack-last sequencing structurally.)
"""
from common.strategy.context import _ABILITY, _PLAY
from common.strategy.strategy import Hypothesis

HYPOTHESES = [
    Hypothesis(
        id="use-the-draw-engine-ability",
        rationale="Activate a pure card-advantage Ability at the MAIN menu — a `draw`/`dig` Ability "
                  "(Drakloak Recon Directive, Dudunsparce Run Away Draw, Bibarel) has NO combat value "
                  "(`_tactical`=0 for a non-attack option) and `dig-before-commit` only fires on `_PLAY`, "
                  "so nothing endorsed it: it scored 0, `_finish_turn_last` dropped it to tier 4 beside "
                  "the turn-ending attack, and any positive-tactical attack ended the turn first — the "
                  "free draw/dig was systematically skipped whenever an attack was on the menu (probe: "
                  "Recon + Run Away Draw both scored 0, fired={}). The `_ABILITY` sibling of "
                  "`dig-before-commit`: give a draw/dig Ability a positive weight so it sequences to tier "
                  "0 (before the attack). Scoped to `draw`/`dig` and non-`cost_discard` — a blanket "
                  "'activate any ability' risks firing a counter-move/heal with no good target (deferred "
                  "refinement). Silent for decks with no draw/dig Ability.",
        when=lambda c: c.option_type == _ABILITY
        and ("draw" in c.tags or "dig" in c.tags) and "cost_discard" not in c.tags,
        weight=18, status="assumed"),
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
