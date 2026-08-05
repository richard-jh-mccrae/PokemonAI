"""General Strategy — the deck-agnostic doctrine the Pilot applies beneath every deck's own Strategy
(see docs/general-strategy.md, ADR-0008). Pure data: weighted, status-tracked, rationale-carrying
Hypotheses keyed on universal Function Tags + engine card stats. Weights are seeds on the
docs/weights.md scale, ladder-tuned and overridable by id (ADR-0009).

This module is now ASSEMBLY-ONLY (ADR-0025). The deck-agnostic baseline rules live one level down in
`common.strategy.baseline`, clustered by the decision-context they fire on — pure-data Hypotheses,
no Pilot code (`baseline_energy` / `baseline_snipe` / `baseline_promote` / `baseline_retreat` /
`baseline_evolution` / `baseline_heal` / `baseline_opening` /
`baseline_sequencing` / `baseline_disruption`). The four card-archetype doctrines each own their
Hypotheses AND their Pilot-side `*Mixin` together in `common.strategy.doctrines`:
  • Gust (Boss's Orders)  doctrines/doctrine_gust             ADR-0022
  • Fetch (Search)        doctrines/doctrine_fetch            ADR-0023
  • Shuffle-Refresh       doctrines/doctrine_shuffle_refresh  ADR-0024
  • Tool (Pokémon Tool)   doctrines/doctrine_tool            ADR-0028
The Pilot scores `GENERAL_STRATEGY.hypotheses` as one flat list (order is irrelevant — the score is a
sum); grouping into clusters/doctrines is purely for authoring/legibility.
"""
from common.strategy.baseline import BASELINE_HYPOTHESES
from common.strategy.doctrines import (FETCH_HYPOTHESES, GUST_HYPOTHESES, REFRESH_HYPOTHESES,
                                       TOOL_HYPOTHESES)
from common.strategy.strategy import Strategy

# Full deck-agnostic strategy = baseline clusters + four doctrines (one flat scored list;
# ADR-0008/0025).
GENERAL_STRATEGY = Strategy(
    name="general",
    hypotheses=BASELINE_HYPOTHESES + GUST_HYPOTHESES + FETCH_HYPOTHESES + REFRESH_HYPOTHESES
    + TOOL_HYPOTHESES)
