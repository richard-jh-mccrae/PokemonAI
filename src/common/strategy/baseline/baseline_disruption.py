"""BASELINE cluster: DISRUPTION — free pre-attack disruption Items (ADR-0025). Strip opponent Energy
before the turn-ending attack when there's something to strip. Pure data, no Mixin. (Grows as more
disruption mechanics — hand disruption, ability lock — land.)
"""
from common.strategy.context import _PLAY
from common.strategy.strategy import Hypothesis, Plan

HYPOTHESES = [
    Hypothesis(
        id="play-energy-denial",
        rationale="Play an energy-denial Item (Function Tag `energy_denial`, e.g. Crushing Hammer — "
                  "'flip a coin; if heads, discard an Energy from 1 of the opponent's Pokémon') BEFORE "
                  "your turn-ending attack, whenever the opponent has Energy in play to strip. Setting a "
                  "developing attacker back an Energy (e.g. a Riolu about to become Mega Lucario ex, or "
                  "chipping a powered Active toward un-attacking) is free disruption: the Item costs "
                  "nothing, so `_finish_turn_last` sequences it tier 0 and you strip AND still attack the "
                  "same turn (attack-last). A positional weight — a lethal attack still outranks it on "
                  "tactical, so the KO is taken (after the free strip; the attack is just held one slot). "
                  "Stands down when the opponent has no Energy in play: the coin-flip denial whiffs, so "
                  "hold it (which benched/active Pokémon to strip is the engine's target select).",
        when=lambda c: c.plan in (Plan.SETUP, Plan.RACE) and c.option_type == _PLAY
        and "energy_denial" in c.tags and c.board.opp_has_energy_in_play,
        weight=20, status="testing"),
]
