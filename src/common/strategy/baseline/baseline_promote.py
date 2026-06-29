"""BASELINE cluster: PROMOTE — which benched Pokémon to bring up after a Knock Out, at a TO_ACTIVE
select (ADR-0025). Ready wincon first; otherwise a disposable staller over a bare pre-evolution.
Pure data, no Mixin.
"""
from common.strategy.context import _TO_ACTIVE
from common.strategy.strategy import Hypothesis

HYPOTHESES = [
    Hypothesis(
        id="promote-the-ready-wincon",
        rationale="When your Active is Knocked Out and a benched win-condition is already powered up "
                  "enough to attack, promote IT — bring your live attacker to the front rather than a "
                  "pre-evolution or a staller.",
        when=lambda c: c.select_context == _TO_ACTIVE and c.card_is_wincon
        and c.board.bench_wincon_ready,
        weight=40, status="testing"),
    Hypothesis(
        id="promote-the-staller",
        rationale="When your Active is Knocked Out and you can NEITHER promote a powered win-condition "
                  "NOR evolve a pre-evolution this turn (the payoff isn't in hand), promote a "
                  "disposable opener / wall (Function Tag `opener`, e.g. Cinderace) instead of a bare "
                  "pre-evolution — it stalls, keeps the fragile pre-evolution safe on the Bench, can "
                  "be retreated for free once you draw the evolution, and can attack if you find "
                  "Energy.",
        when=lambda c: c.select_context == _TO_ACTIVE and "opener" in c.tags
        and not c.board.wincon_in_hand and not c.board.bench_wincon_ready,
        weight=20, status="testing"),
]
