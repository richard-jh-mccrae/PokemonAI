"""General Strategy — the deck-agnostic doctrine the Pilot applies beneath every deck's own Strategy
(docs/general-strategy.md, ADR-0008). ASSEMBLY-ONLY (ADR-0025): the baseline clusters live in
`common.strategy.baseline` and the card-archetype doctrines in `common.strategy.doctrines`.

The Pilot scores `GENERAL_STRATEGY.hypotheses` as one flat list — order is irrelevant, the score is a
sum — so the clustering is purely for authoring. The MAIN-phase positional families the roster lost at
POC-T4/5 (Issue #386) are now priced by differencing in `common.composer`.
"""
from common.strategy.baseline import BASELINE_HYPOTHESES
from common.strategy.doctrines import FETCH_HYPOTHESES, GUST_HYPOTHESES, REFRESH_HYPOTHESES
from common.strategy.strategy import Strategy

# Full deck-agnostic strategy = baseline clusters + the surviving doctrines (one flat scored list;
# ADR-0008/0025).
GENERAL_STRATEGY = Strategy(
    name="general",
    hypotheses=BASELINE_HYPOTHESES + GUST_HYPOTHESES + FETCH_HYPOTHESES + REFRESH_HYPOTHESES)
