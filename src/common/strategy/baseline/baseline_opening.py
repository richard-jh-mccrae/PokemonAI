"""BASELINE cluster: OPENING — opening-hand / mulligan / game-start decisions (ADR-0025). Don't
redraw a hand you can already start; open with the piece your deck's Roles nominate. Pure data,
no Mixin.
"""
from common.strategy.context import _IS_FIRST, _MULLIGAN, _NO, _SETUP_ACTIVE, _YES
from common.strategy.strategy import Hypothesis, Plan

HYPOTHESES = [
    Hypothesis(
        id="keep-a-startable-hand",
        rationale="Don't mulligan away a hand you can already start — if a Pokémon in hand can take "
                  "the Active Spot (a Basic, or via an opening Ability like Explosiveness), keep it "
                  "rather than redraw and give the opponent a free card.",
        when=lambda c: c.select_context == _MULLIGAN and c.option_type == _YES
        and c.board.hand_startable,
        weight=-40, status="assumed"),
    Hypothesis(
        id="honor-preferred-start",
        rationale="At the coin toss, honor the deck's declared tempo "
                  "(`Strategy.params['preferred_start']` = 'first'|'second'): a turbo deck wants SECOND "
                  "(going first can't attack turn 1, wasting burst Energy), a setup-heavy deck wants "
                  "FIRST. This selector only penalises the option that contradicts the declaration; "
                  "undeclared decks are untouched. Folded from mega_starmie `prefer-going-second`.",
        when=lambda c: c.select_context == _IS_FIRST and (
            (c.option_type == _YES and c.params.get("preferred_start") == "second")
            or (c.option_type == _NO and c.params.get("preferred_start") == "first")),
        weight=-30, status="assumed"),
    Hypothesis(
        id="open-the-accelerator",
        rationale="At the Set-Up Active pick, prefer an `accel_source`-Role opener — it turns its "
                  "acceleration on from turn one (e.g. Cinderace: Explosiveness opens the Spot, Turbo "
                  "Flare loads the Bench). Role-keyed opt-in; folded from mega_starmie `open-cinderace`.",
        when=lambda c: c.select_context == _SETUP_ACTIVE   # pregame pick: the line can't be ready yet
        and "accel_source" in c.roles,
        weight=40, status="assumed"),
]
