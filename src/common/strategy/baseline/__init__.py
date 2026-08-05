"""Deck-agnostic **baseline** rules, clustered by the **decision-context** they fire on (ADR-0025).
Each `baseline_*` module is pure-data General-Strategy Hypotheses — NO Pilot Mixin (the contrast with
a `doctrines/` doctrine, which owns closed-form code). A findability split only: the Pilot scores
everything as one flat sum, so cluster boundaries and order are runtime-irrelevant.

Mirrors the `doctrines/__init__` idiom — re-export each cluster's `HYPOTHESES` under an aliased name —
and, because there are many clusters (vs. 4 doctrines), additionally owns the combined
`BASELINE_HYPOTHESES` roster so `general_strategy` stays a clean baseline + doctrines assembly.
(The Tool cluster was promoted to the Tool DOCTRINE — `doctrines/doctrine_tool.py`, ADR-0028.)

The BENCH cluster is GONE, not empty (Issue #261 item 2d). ADR-0086 deleted nine of its ten rules
into the Deploy Marginal; ADR-0096 decision 2 deleted the tenth, `keep-a-bench` (+60) — it guarded
nothing `Pilot._empty_bench_forced` does not already guarantee (the filter runs AFTER
`_finish_turn_last`, so it wins outright), and it WAS the spare-body cliff: a body priced 1.96 on a
non-empty Bench against 61.96 on an empty one, the entire gap being that rung. The escalating slot
price that replaces the cliff is T3's `development` term family (`state_value.REGISTRY`), not a
rung. A module holding an empty tuple would read as a cluster that merely lost its members.
"""
from common.strategy.baseline.baseline_disruption import HYPOTHESES as DISRUPTION_HYPOTHESES
from common.strategy.baseline.baseline_energy import HYPOTHESES as ENERGY_HYPOTHESES
from common.strategy.baseline.baseline_evolution import HYPOTHESES as EVOLUTION_HYPOTHESES
from common.strategy.baseline.baseline_heal import HYPOTHESES as HEAL_HYPOTHESES
from common.strategy.baseline.baseline_opening import HYPOTHESES as OPENING_HYPOTHESES
from common.strategy.baseline.baseline_phases import HYPOTHESES as PHASES_HYPOTHESES
from common.strategy.baseline.baseline_posture import HYPOTHESES as POSTURE_HYPOTHESES
from common.strategy.baseline.baseline_promote import HYPOTHESES as PROMOTE_HYPOTHESES
from common.strategy.baseline.baseline_retreat import HYPOTHESES as RETREAT_HYPOTHESES
from common.strategy.baseline.baseline_sequencing import HYPOTHESES as SEQUENCING_HYPOTHESES
from common.strategy.baseline.baseline_snipe import HYPOTHESES as SNIPE_HYPOTHESES

# Full baseline roster, authored order; order runtime-irrelevant (Pilot sums scores), kept stable for
# legibility. (Tool rules promoted to Tool DOCTRINE `doctrines/doctrine_tool.py` once needing board-math; ADR-0028.)
BASELINE_HYPOTHESES = (
    ENERGY_HYPOTHESES + SNIPE_HYPOTHESES + PROMOTE_HYPOTHESES
    + RETREAT_HYPOTHESES + EVOLUTION_HYPOTHESES + HEAL_HYPOTHESES
    + OPENING_HYPOTHESES + SEQUENCING_HYPOTHESES + DISRUPTION_HYPOTHESES + PHASES_HYPOTHESES
    + POSTURE_HYPOTHESES)

__all__ = [
    "BASELINE_HYPOTHESES",
    "ENERGY_HYPOTHESES", "SNIPE_HYPOTHESES", "PROMOTE_HYPOTHESES",
    "RETREAT_HYPOTHESES", "EVOLUTION_HYPOTHESES", "HEAL_HYPOTHESES",
    "OPENING_HYPOTHESES", "SEQUENCING_HYPOTHESES", "DISRUPTION_HYPOTHESES", "PHASES_HYPOTHESES",
    "POSTURE_HYPOTHESES",
]
