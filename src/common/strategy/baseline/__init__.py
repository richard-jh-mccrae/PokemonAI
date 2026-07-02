"""Deck-agnostic **baseline** rules, clustered by the **decision-context** they fire on (ADR-0025).
Each `baseline_*` module is pure-data General-Strategy Hypotheses — NO Pilot Mixin (the contrast with
a `doctrines/` doctrine, which owns closed-form code). A findability split only: the Pilot scores
everything as one flat sum, so cluster boundaries and order are runtime-irrelevant.

Mirrors the `doctrines/__init__` idiom — re-export each cluster's `HYPOTHESES` under an aliased name —
and, because there are 10 clusters (vs. 4 doctrines), additionally owns the combined
`BASELINE_HYPOTHESES` roster so `general_strategy` stays a clean baseline + doctrines assembly.
(The 11th cluster, Tool, was promoted to the Tool DOCTRINE — `doctrines/doctrine_tool.py`, ADR-0028.)
"""
from common.strategy.baseline.baseline_bench import HYPOTHESES as BENCH_HYPOTHESES
from common.strategy.baseline.baseline_disruption import HYPOTHESES as DISRUPTION_HYPOTHESES
from common.strategy.baseline.baseline_energy import HYPOTHESES as ENERGY_HYPOTHESES
from common.strategy.baseline.baseline_evolution import HYPOTHESES as EVOLUTION_HYPOTHESES
from common.strategy.baseline.baseline_heal import HYPOTHESES as HEAL_HYPOTHESES
from common.strategy.baseline.baseline_opening import HYPOTHESES as OPENING_HYPOTHESES
from common.strategy.baseline.baseline_promote import HYPOTHESES as PROMOTE_HYPOTHESES
from common.strategy.baseline.baseline_retreat import HYPOTHESES as RETREAT_HYPOTHESES
from common.strategy.baseline.baseline_sequencing import HYPOTHESES as SEQUENCING_HYPOTHESES
from common.strategy.baseline.baseline_snipe import HYPOTHESES as SNIPE_HYPOTHESES

# Full baseline roster, authored order; order runtime-irrelevant (Pilot sums scores), kept stable for
# legibility. (Tool rules promoted to Tool DOCTRINE `doctrines/doctrine_tool.py` once needing board-math; ADR-0028.)
BASELINE_HYPOTHESES = (
    ENERGY_HYPOTHESES + SNIPE_HYPOTHESES + BENCH_HYPOTHESES + PROMOTE_HYPOTHESES
    + RETREAT_HYPOTHESES + EVOLUTION_HYPOTHESES + HEAL_HYPOTHESES
    + OPENING_HYPOTHESES + SEQUENCING_HYPOTHESES + DISRUPTION_HYPOTHESES)

__all__ = [
    "BASELINE_HYPOTHESES",
    "ENERGY_HYPOTHESES", "SNIPE_HYPOTHESES", "BENCH_HYPOTHESES", "PROMOTE_HYPOTHESES",
    "RETREAT_HYPOTHESES", "EVOLUTION_HYPOTHESES", "HEAL_HYPOTHESES",
    "OPENING_HYPOTHESES", "SEQUENCING_HYPOTHESES", "DISRUPTION_HYPOTHESES",
]
