"""The three C10 rule guards retained after Issue #459's shared-rung retirement."""
from common.strategy.context import _IS_FIRST, _MULLIGAN, _NO, _YES
from common.strategy.strategy import Hypothesis

HYPOTHESES = [
    Hypothesis(
        id="keep-a-startable-hand",
        rationale="Do not mulligan away a hand that can legally provide an Active Pokémon.",
        when=lambda c: c.select_context == _MULLIGAN and c.option_type == _YES and c.board.hand_startable,
        weight=-40, status="assumed"),
    Hypothesis(
        id="honor-preferred-start",
        rationale="At the coin toss, reject only the start order that conflicts with the deck declaration.",
        when=lambda c: c.select_context == _IS_FIRST and (
            (c.option_type == _YES and c.params.get("preferred_start") == "second")
            or (c.option_type == _NO and c.params.get("preferred_start") == "first")),
        weight=-30, status="assumed"),
]
