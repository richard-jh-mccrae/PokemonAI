"""The `common.strategy` package — the deck-facing data layer (Strategy/Hypothesis/Plan/Line/Ready),
the engine `context` vocabulary, the deck-agnostic `general_strategy`, and one module per
card-archetype **doctrine** under `doctrines/` (`doctrine_gust`, `doctrine_fetch`,
`doctrine_shuffle_refresh`). Each doctrine
module owns BOTH its positional Hypotheses and the Pilot-side closed-form code (a `*Mixin` the Pilot
inherits) — so a doctrine is one file, end to end (ADR-0008/0022/0023/0024).

Re-exports the declarative data API so the historical `from common.strategy import Strategy, ...`
imports keep working after `strategy.py` moved into this package.
"""
from common.strategy.strategy import Hypothesis, Line, Plan, Ready, Strategy

__all__ = ["Hypothesis", "Line", "Plan", "Ready", "Strategy"]
