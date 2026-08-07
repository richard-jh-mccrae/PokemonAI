"""Card-archetype **doctrines** — one module per archetype, each owning BOTH its positional
Hypotheses and its Pilot-side closed-form code (a `*Mixin` the Pilot inherits), so a doctrine is one
file end to end (ADR-0008). The deck-agnostic baseline rules live in `common.strategy.baseline`
(clustered by decision-context; ADR-0025) and the final assembly in `common.strategy.general_strategy`.

The **Tool doctrine is GONE** (POC-T4/5, Issue #386), Mixin and all. Its five equip rungs and the
`_tool_deploy_slot` survival-turns picker that fed them were one mechanism, and the composer prices
what a Tool buys as the `survival` delta on the end board — which is what ADR-0028's survival-turns
math always was (Issue #263 § *The families this prices*). Deleted rather than emptied: a doctrine
module holding an empty roster and a picker nobody reads would read as a doctrine that merely lost
its rungs.

  • doctrine_gust              Gust (Boss's Orders)  — ADR-0022 — `GustMixin`
  • doctrine_fetch             Fetch (Search)        — ADR-0023 — `FetchMixin`
  • doctrine_shuffle_refresh   Shuffle-Refresh       — ADR-0024 — `ShuffleRefreshMixin`

Re-exported here so callers can `from common.strategy.doctrines import GustMixin, FETCH_HYPOTHESES, …`.
"""
from common.strategy.doctrines.doctrine_fetch import HYPOTHESES as FETCH_HYPOTHESES
from common.strategy.doctrines.doctrine_fetch import FetchMixin
from common.strategy.doctrines.doctrine_gust import HYPOTHESES as GUST_HYPOTHESES
from common.strategy.doctrines.doctrine_gust import GustMixin
from common.strategy.doctrines.doctrine_shuffle_refresh import HYPOTHESES as REFRESH_HYPOTHESES
from common.strategy.doctrines.doctrine_shuffle_refresh import ShuffleRefreshMixin

__all__ = [
    "GustMixin", "GUST_HYPOTHESES",
    "FetchMixin", "FETCH_HYPOTHESES",
    "ShuffleRefreshMixin", "REFRESH_HYPOTHESES",
]
