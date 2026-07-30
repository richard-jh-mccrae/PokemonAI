"""BASELINE cluster: BENCH — the empty-Bench reflex (ADR-0025, narrowed by ADR-0081).

Once held six rules about *what* to bench and *when*. The Deploy Marginal (`common.deploy_value`,
ADR-0081) prices that question as a value equation instead, so `dont-bench-multiprize`,
`pre-position-attacker`, `develop-a-basic-in-setup`, `develop-the-wincon-base-first`,
`dont-bench-onto-their-path` and `develop-the-accel-recipient` are gone — each is a leg of the
equation now (prize exposure, assignment relevance, the Prize-Path delta, the accel unlock).

`keep-a-bench` STAYS, and is the whole file: ADR-0081 decision 7 rules it a **sound rung**, not a
pricing question — an empty Bench with the Active Knocked Out loses on the spot, whatever the
marginal says. `Pilot._empty_bench_forced` promotes it to a post-setup order FILTER; the rung below
keeps scoring the same play so the two agree. Pure data, no Mixin; `_is_pokemon` lives here because
only this rule reads it.
"""
from common.strategy.context import _PLAY
from common.strategy.strategy import Hypothesis


def _is_pokemon(stat) -> bool:
    """A Pokémon (Trainers / Energy report hp 0) — so a PLAY of it develops the Bench."""
    return bool(stat and stat.is_pokemon)


HYPOTHESES = [
    Hypothesis(
        id="keep-a-bench",
        rationale="Never leave yourself with an empty Bench — if the Active is Knocked Out with no "
                  "Pokémon to promote, you lose on the spot, so develop a Basic.",
        when=lambda c: c.board.my_bench == 0 and c.option_type == _PLAY and _is_pokemon(c.stat),
        weight=60, status="assumed"),
]
