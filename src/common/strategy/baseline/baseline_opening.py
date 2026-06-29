"""BASELINE cluster: OPENING — opening-hand / mulligan decisions (ADR-0025). Don't redraw a hand you
can already start. Pure data, no Mixin. (One rule for now — opening-turn reflexes grow here.)
"""
from common.strategy.context import _MULLIGAN, _YES
from common.strategy.strategy import Hypothesis

HYPOTHESES = [
    Hypothesis(
        id="keep-a-startable-hand",
        rationale="Don't mulligan away a hand you can already start — if a Pokémon in hand can "
                  "take the Active Spot (a Basic, or one whose Ability lets it open, like "
                  "Explosiveness), keep it rather than redraw and give the opponent a free card.",
        when=lambda c: c.select_context == _MULLIGAN and c.option_type == _YES
        and c.board.hand_startable,
        weight=-40, status="assumed"),
]
