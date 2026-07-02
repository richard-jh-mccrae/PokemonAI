"""BASELINE cluster: OPENING — opening-hand / mulligan / game-start decisions (ADR-0025). Don't
redraw a hand you can already start; open with the piece your deck's Roles nominate. Pure data,
no Mixin.
"""
from common.strategy.context import _IS_FIRST, _MULLIGAN, _NO, _SETUP_ACTIVE, _YES
from common.strategy.strategy import Hypothesis, Plan

HYPOTHESES = [
    Hypothesis(
        id="keep-a-startable-hand",
        rationale="Don't mulligan away a hand you can already start — if a Pokémon in hand can "
                  "take the Active Spot (a Basic, or one whose Ability lets it open, like "
                  "Explosiveness), keep it rather than redraw and give the opponent a free card.",
        when=lambda c: c.select_context == _MULLIGAN and c.option_type == _YES
        and c.board.hand_startable,
        weight=-40, status="assumed"),
    Hypothesis(
        id="honor-preferred-start",
        rationale="At the coin toss, honor the deck's declared tempo: "
                  "`Strategy.params['preferred_start']` = 'first' | 'second'. A turbo deck that "
                  "sprints its attacker online wants SECOND (the player going first cannot attack "
                  "on turn 1, and an end-of-turn burst Energy would be wasted); a setup-heavy deck "
                  "wants FIRST (a free development turn). The judgment is the deck's — this "
                  "selector just penalises the coin-toss option that CONTRADICTS the declaration; "
                  "undeclared decks are untouched. Folded from mega_starmie `prefer-going-second` "
                  "(same firing for that deck: -30 on YES with preferred_start='second').",
        when=lambda c: c.select_context == _IS_FIRST and (
            (c.option_type == _YES and c.params.get("preferred_start") == "second")
            or (c.option_type == _NO and c.params.get("preferred_start") == "first")),
        weight=-30, status="assumed"),
    Hypothesis(
        id="open-the-accelerator",
        rationale="At the Set-Up Active pick, prefer an `accel_source`-Role opener: an accelerator "
                  "in the Active Spot turns its acceleration on from turn one (e.g. Cinderace — "
                  "Explosiveness opens the Spot, Turbo Flare then loads the Bench). Role-keyed, so "
                  "a deck opts in by assigning the Role to the piece it means to open with. Folded "
                  "from mega_starmie `open-cinderace` (same trigger + weight).",
        when=lambda c: c.plan == Plan.SETUP and c.select_context == _SETUP_ACTIVE
        and "accel_source" in c.roles,
        weight=40, status="assumed"),
]
