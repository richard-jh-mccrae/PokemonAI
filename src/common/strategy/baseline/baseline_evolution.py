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
        id="evolve-the-energized-body-first",
        rationale="When two pre-evolutions can both become the win-condition, evolve the one that already "
                  "carries Energy (`evolve_body_energy > 0`) — the result can ATTACK this turn (sprint), "
                  "while evolving a bare body wastes the tempo (ep83664991 f25: two Staryu, one at 3 "
                  "Energy — evolve THAT one, then disrupt). A small tie-break (+5) on top of "
                  "`evolve-into-wincon` (+40) so it only orders the WHICH-body pick between equal evolves; "
                  "a KO still dominates (KO_SCORE).",
        when=lambda c: c.option_type == _EVOLVE and bool(_WINCON_ROLES & set(c.roles))
        and (c.evolve_body_energy or 0) > 0,
        weight=5, status="assumed"),
    Hypothesis(
        id="advance-the-evolution-line",
        rationale="Evolving a MID-Line piece (e.g. Dreepy -> Drakloak toward Dragapult ex) advances the "
                  "win-condition line even though the result isn't yet the payoff — `evolve-into-wincon` "
                  "(+40) only fires on the final Role-carrying evolution, so a bare mid-line Evolve sat at "
                  "score 0 and lost to a spread attach onto a 3rd bare base (ep83686860 f29: 'better to "
                  "fully charge single wincon line then spread out energy'). Endorse it so concentrating "
                  "the started line beats spreading; +15 clears `power-up-attacker` (+15 net +10 after "
                  "`attach-energy-last`) but stays below `evolve-into-wincon` (+40). Gated on the result "
                  "being a Line pre-evolution (`card_is_line_preevo`); a KO still dominates (KO_SCORE). "
                  "Silent for single-hop lines (Riolu->Mega, Staryu->Mega) with no mid-Line piece.",
        when=lambda c: c.option_type == _EVOLVE and c.card_is_line_preevo,
        weight=15, status="assumed"),
    Hypothesis(
        id="advance-the-energized-line-body-first",
        rationale="When two MID-line pre-evolutions can both advance the line, evolve the one that already "
                  "carries Energy (`evolve_body_energy > 0`) — the evolved form can ATTACK this turn "
                  "(dragapult f82: energized Active Dreepy -> Drakloak Dragon Headbutt {R}{P} 70 now, vs a "
                  "bare bench Dreepy -> a Drakloak that can't attack). The mid-line analogue of "
                  "`evolve-the-energized-body-first` (which only covers the wincon-Role final evolve); a "
                  "small +5 WHICH-body tie-break on top of `advance-the-evolution-line` (+15), so the "
                  "energized body nets 20 vs a bare one at 15. Needed because the decide() secondary sort "
                  "key `attach_to_needy_line` fires BACKWARDS on an Evolve (it favours the energy-LESS bare "
                  "body as 'needy'), handing the tie to the bare copy; this rung wins the pick on score "
                  "outright. A KO still dominates (KO_SCORE).",
        when=lambda c: c.option_type == _EVOLVE and c.card_is_line_preevo
        and (c.evolve_body_energy or 0) > 0,
        weight=5, status="assumed"),
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
