"""Card-archetype **doctrines** — one module per archetype, each owning BOTH its positional Hypotheses
and its Pilot-side `*Mixin`, so a doctrine is one file end to end (ADR-0008).

The **Tool doctrine is GONE** (Issue #386), Mixin and all — the composer prices what a Tool buys as the
`survival` delta on the end board. Deleted rather than emptied.
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
