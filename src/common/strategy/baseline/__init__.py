"""Deck-agnostic **baseline** rules, clustered by the decision-context they fire on (ADR-0025).
Pure-data General-Strategy Hypotheses, NO Pilot Mixin. The Pilot sums one flat score, so cluster
boundaries and order are runtime-irrelevant; this module also owns the combined roster.

**Five clusters are GONE, not empty** — HEAL, RETREAT, SEQUENCING and DISRUPTION (POC-T4/5,
Issue #386; their rungs are folded into `common.composer`'s sequence search) plus BENCH (ADR-0086,
ADR-0096 decision 2). Deleted rather than emptied: an empty tuple reads as a cluster that merely
lost its members. Per-rung fold map: `tools/rung_registry.py`, read by `tools/train/reviewed_audit.py`.

⚠️ **A tier keyed on a rung id dies with the rung, silently** — a retired id in a live string
literal reads as live to every instrument, so the KO-enabling-gust and wall-retreat branches of
`_finish_turn_last` were unreachable from the fold onward and nothing went red.
`tests/strategy/test_rung_id_literals_are_live.py` is the interlock that fails the next one.
"""
from common.strategy.baseline.baseline_energy import HYPOTHESES as ENERGY_HYPOTHESES
from common.strategy.baseline.baseline_evolution import HYPOTHESES as EVOLUTION_HYPOTHESES
from common.strategy.baseline.baseline_opening import HYPOTHESES as OPENING_HYPOTHESES
from common.strategy.baseline.baseline_phases import HYPOTHESES as PHASES_HYPOTHESES
from common.strategy.baseline.baseline_posture import HYPOTHESES as POSTURE_HYPOTHESES
from common.strategy.baseline.baseline_promote import HYPOTHESES as PROMOTE_HYPOTHESES
from common.strategy.baseline.baseline_snipe import HYPOTHESES as SNIPE_HYPOTHESES

# Full baseline roster, authored order; order is runtime-irrelevant (the Pilot sums scores).
BASELINE_HYPOTHESES = (
    ENERGY_HYPOTHESES + SNIPE_HYPOTHESES + PROMOTE_HYPOTHESES
    + EVOLUTION_HYPOTHESES + OPENING_HYPOTHESES + PHASES_HYPOTHESES
    + POSTURE_HYPOTHESES)

__all__ = [
    "BASELINE_HYPOTHESES",
    "ENERGY_HYPOTHESES", "SNIPE_HYPOTHESES", "PROMOTE_HYPOTHESES",
    "EVOLUTION_HYPOTHESES", "OPENING_HYPOTHESES", "PHASES_HYPOTHESES",
    "POSTURE_HYPOTHESES",
]
