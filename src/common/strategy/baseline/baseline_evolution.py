"""BASELINE cluster: EVOLUTION — bringing the line online (ADR-0025). Evolve into the win-condition,
prefer a rush-evolve tutor in setup, and penalise a rush-evolve with no target. Pure data, no Mixin.
"""
from common.strategy.context import _EVOLVE, _PLAY, _WINCON_ROLES
from common.strategy.strategy import Hypothesis, Plan

HYPOTHESES = [
    Hypothesis(
        id="evolve-into-wincon",
        rationale="Evolving into the win-condition (e.g. Staryu -> Mega Starmie ex) brings your main "
                  "attacker online, so prefer an Evolve option whose result carries the "
                  "`win_condition` / `primary_attacker` Role over a chip attack or lesser development. "
                  "A lethal attack still wins — a positional weight never beats a KO.",
        when=lambda c: c.option_type == _EVOLVE and bool(_WINCON_ROLES & set(c.roles)),
        weight=40, status="testing"),
    Hypothesis(
        id="prefer-rush-evolve-tutor",
        rationale="A `rush_evolve` tutor (e.g. Salvatore: fetch a Pokémon and evolve it the same turn "
                  "its pre-evolution was played) collapses two setup turns into one, so prefer it — "
                  "gated on a pre-evolution already in play, the payoff not already in hand (mirrors "
                  "`play-a-tutor-for-the-unfound-wincon`'s `not wincon_in_hand` gate), and the evolution "
                  "target not provably exhausted from the deck (`search_targets_exhausted`; without this "
                  "gate the +30 would swamp `dont-search-an-empty-deck`'s -60 — ep83117367).",
        when=lambda c: c.plan == Plan.SETUP and c.option_type == _PLAY and "rush_evolve" in c.tags
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
