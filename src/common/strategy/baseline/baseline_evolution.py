"""BASELINE cluster: EVOLUTION — bringing the line online (ADR-0025). Evolve into the win-condition,
prefer a rush-evolve tutor in setup, and penalise a rush-evolve with no target. Pure data, no Mixin.
"""
from common.strategy.context import _EVOLVE, _PLAY, _WINCON_ROLES
from common.strategy.strategy import Hypothesis, Plan

HYPOTHESES = [
    Hypothesis(
        id="evolve-into-wincon",
        rationale="Evolving into the win-condition (e.g. Staryu → Mega Starmie ex) brings your main "
                  "attacker online — almost always do it when you can. Strongly prefer an Evolve "
                  "option whose result carries the `win_condition` / `primary_attacker` Role over a "
                  "chip attack or lesser development. (A lethal attack still wins — a positional "
                  "weight never beats a KO.)",
        when=lambda c: c.option_type == _EVOLVE and bool(_WINCON_ROLES & set(c.roles)),
        weight=40, status="testing"),
    Hypothesis(
        id="prefer-rush-evolve-tutor",
        rationale="During setup, prefer a card that can rush-evolve your line (Function Tag "
                  "`rush_evolve`, e.g. Salvatore: fetch a Pokémon and evolve it the same turn its "
                  "pre-evolution was played). It collapses two turns of setup into one and gets the "
                  "win-condition online a turn early. Stands down when there's no pre-evolution in "
                  "play to evolve — without an evolution target the rush-evolve does nothing — AND "
                  "when the payoff is already in hand: you can evolve directly this turn, so spending "
                  "a tutor (and a second copy from the deck) to do the same is wasteful (mirrors "
                  "`tutor-the-wincon`'s `not wincon_in_hand` gate). ALSO stands down when the tutor's "
                  "evolution target is provably GONE from the deck (`search_targets_exhausted`, the "
                  "sound deck-oracle over its `rush_evolve` fetch-filter): with an in-play Staryu but "
                  "every Mega Starmie ex prized/played, Salvatore whiffs — don't endorse it (ep83117367). "
                  "Without this gate the +30 would swamp `dont-search-an-empty-deck`'s −60.",
        when=lambda c: c.plan == Plan.SETUP and c.option_type == _PLAY and "rush_evolve" in c.tags
        and c.board.line_preevo_in_play and not c.board.wincon_in_hand
        and not c.search_targets_exhausted,
        weight=30, status="testing"),
    Hypothesis(
        id="dont-rush-evolve-without-target",
        rationale="Don't play a rush-evolve tutor (Function Tag `rush_evolve`, e.g. Salvatore — "
                  "'search for a card that evolves from 1 of your Pokémon and put it onto that Pokémon "
                  "to evolve it') when there is NO pre-evolution in play to evolve — it whiffs, a "
                  "wasted card. The positive `prefer-rush-evolve-tutor` already stands down here; this "
                  "actively penalises the play so the agent attaches / develops instead. Pushes it "
                  "below an endorsed attach and below 0 (sequenced last).",
        when=lambda c: c.option_type == _PLAY and "rush_evolve" in c.tags
        and not c.board.line_preevo_in_play,
        weight=-60, status="testing"),
]
