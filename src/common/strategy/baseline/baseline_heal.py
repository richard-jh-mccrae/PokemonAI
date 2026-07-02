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
                  "outranks a lethal (a KO is worth far more than a heal). Stands down when the Active "
                  "can ALREADY Knock Out the opponent's Active this turn (`board.active_can_ko`): there "
                  "is nothing to survive FOR — take the prize/win now, don't strip your own attacker's "
                  "Energy to heal-and-stall (`clutch_heal` bounces all Energy to hand, which would "
                  "forfeit the KO the deferred attack still scores highest — ep83037962 f78 missed win).",
        when=lambda c: c.option_type == _PLAY and "clutch_heal" in c.tags
        and c.board.active_doomed and not c.board.active_can_ko,
        weight=60, status="testing"),
    Hypothesis(
        id="dont-waste-clutch-heal",
        rationale="The negative complement of `hold-clutch-heal`: a `clutch_heal` (Wally's Compassion) "
                  "bounces ALL the healed Pokémon's Energy back to hand — a real cost the raw score "
                  "otherwise ignores. When the Active is NOT doomed there is nothing to survive FOR, so "
                  "playing it only strips your own Energy (wasting a fresh attach — the exact 'attach "
                  "then Wally's' blunder — and your turn's Supporter) for no gain. Penalize it below "
                  "End/develop so the initiative is kept. Gated on `not active_doomed`, the mirror of "
                  "the reward gate, so the two never fire together and this can NEVER touch a genuine "
                  "clutch save: when doomed, `hold-clutch-heal` (+60) or the stabilize-then-KO planner "
                  "line owns the heal; when not doomed, hold it (ep83054602 f32 — Wally's over End with "
                  "2 Energy on the Active; ep81904064 f29 human corrected Wally's -> develop).",
        when=lambda c: c.option_type == _PLAY and "clutch_heal" in c.tags
        and not c.board.active_doomed,
        weight=-40, status="testing"),
]
