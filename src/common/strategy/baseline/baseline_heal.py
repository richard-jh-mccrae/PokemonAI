"""BASELINE cluster: HEAL — defensive heal timing (ADR-0025). A clutch (energy-bouncing) heal is a
survival save, held until the Active is doomed. Pure data, no Mixin. (One rule for now — the cluster
grows as more heal mechanics land.)
"""
from common.strategy.context import _PLAY
from common.strategy.strategy import Hypothesis

HYPOTHESES = [
    Hypothesis(
        id="hold-clutch-heal",
        rationale="A heal that bounces the healed Pokémon's Energy back to hand (Function Tag "
                  "`clutch_heal`, e.g. Wally's Compassion) is a defensive save, not a value heal — "
                  "hold it until your Active is about to be Knocked Out, then play it to survive. "
                  "Firing only when the Active is doomed keeps it off minor damage AND sequences it "
                  "ahead of the energy attach (so the bounce doesn't waste a fresh attachment): heal "
                  "first, then re-power the same turn — Ignition Energy refills the full cost in one "
                  "attach, or a single Energy is enough for a cheap attack — and still attack. Never "
                  "outranks a lethal (a KO is worth far more than a heal).",
        when=lambda c: c.option_type == _PLAY and "clutch_heal" in c.tags and c.board.active_doomed,
        weight=60, status="testing"),
]
