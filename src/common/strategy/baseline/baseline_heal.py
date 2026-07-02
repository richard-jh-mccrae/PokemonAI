"""BASELINE cluster: HEAL — defensive heal timing (ADR-0025). A clutch (energy-bouncing) heal is a
survival save, held until the Active is doomed. Pure data, no Mixin. (One rule for now — the cluster
grows as more heal mechanics land.)
"""
from common.strategy.context import _PLAY
from common.strategy.strategy import Hypothesis

HYPOTHESES = [
    Hypothesis(
        id="hold-clutch-heal",
        rationale="A `clutch_heal` (e.g. Wally's Compassion, which bounces all the healed Pokémon's "
                  "Energy to hand) is a defensive save, not a value heal — hold it until the Active is "
                  "doomed, then play it before the re-attach so it heals, re-powers, and still attacks "
                  "the same turn. Never outranks a lethal; stands down when the Active can already KO "
                  "this turn (`board.active_can_ko`) since stripping Energy would forfeit that KO for "
                  "no reason (ep83037962 f78 missed win).",
        when=lambda c: c.option_type == _PLAY and "clutch_heal" in c.tags
        and c.board.active_doomed and not c.board.active_can_ko,
        weight=60, status="testing"),
    Hypothesis(
        id="dont-waste-clutch-heal",
        rationale="Negative complement of `hold-clutch-heal`: when the Active is NOT doomed, playing a "
                  "`clutch_heal` (Wally's Compassion) only strips your own Energy and burns the "
                  "Supporter for no gain, so penalize it below End/develop. Gated on `not active_doomed` "
                  "(the mirror of the reward gate, so the two never fire together) — ep83054602 f32 "
                  "(Wally's over End with 2 Energy on the Active), ep81904064 f29 (Wally's -> develop).",
        when=lambda c: c.option_type == _PLAY and "clutch_heal" in c.tags
        and not c.board.active_doomed,
        weight=-40, status="testing"),
]
