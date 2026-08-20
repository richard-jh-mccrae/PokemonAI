"""The Ledger decider: spend the turn while something is worth doing, then end it best.

One rule (plan §4): while any turn-continuing option's swing clears the noise floor, take the
best of those; only when nothing is worth doing, take the best turn-ender — and ending the turn
is worth exactly zero, so a turn-ender must earn its damage. Forced menus (no End on offer) are
a straight argmax. Ties inside the noise floor break to the lowest engine selection, so a
replayed frame answers identically. Every decision reports its option prices and coverage gaps
in `RootDecision.diagnostics`; a `gap_sink` callable receives one record per decision that met
a gap — the honest worklist, counted per decision affected."""
from __future__ import annotations

from common.api import RootDecision
from common.board import BoardState
from common.native_engine import NativeCgTransitionProvider
from common.solver import MAIN_DECISION_CONTEXT
from common.state import DecisionState

from .evaluate import evaluate
from .preview import NOISE_FLOOR, OptionPrice, price_actions
from .worth import LedgerContext


class LedgerUnavailable(RuntimeError):
    """The transition seam could not open for this observation."""


class LedgerDecider:
    def __init__(self, deck, deck_name: str, ctx: LedgerContext, *,
                 provider_factory=NativeCgTransitionProvider, gap_sink=None):
        self.deck = tuple(int(card_id) for card_id in deck)
        self.deck_name = str(deck_name)
        self.ctx = ctx
        self.provider_factory = provider_factory
        self.gap_sink = gap_sink

    def decide(self, observation) -> RootDecision:
        state = DecisionState.from_observation(
            observation, deck=self.deck, deck_name=self.deck_name,
            value_registry_identity=f"ledger:{self.ctx.weights.identity}")
        board = BoardState.root(observation, decklist=self.deck)
        baseline = evaluate(board, self.ctx)
        provider = self.provider_factory(state)
        if not getattr(provider, "available", True):
            raise LedgerUnavailable(str(getattr(provider, "_error", "provider unavailable")))
        try:
            prices = price_actions(state, board, baseline.total, provider, self.ctx)
        finally:
            close = getattr(provider, "close", None)
            if close is not None:
                close()
        if not prices:
            raise LedgerUnavailable("no legal actions to price")

        context = int(((observation.get("select") or {}).get("context",
                                                             MAIN_DECISION_CONTEXT)))
        chosen = self._choose(prices, forced=context != MAIN_DECISION_CONTEXT)
        gaps = tuple(gap for price in prices for gap in price.gaps) + baseline.gaps
        if gaps and self.gap_sink is not None:
            self.gap_sink({"context": context, "board": board.key, "gaps": sorted(set(gaps)),
                           "chosen": list(chosen.action.selection)})
        return RootDecision(
            chosen=tuple(chosen.action.selection), action=chosen.action.identity,
            value=chosen.swing, complete=True,
            diagnostics={
                "backend": "ledger", "weights": self.ctx.weights.identity,
                "baseline": baseline.total, "gaps": sorted(set(gaps)),
                "prices": tuple({"action": str(price.action.identity),
                                 "selection": list(price.action.selection),
                                 "swing": price.swing, "ends_turn": price.ends_turn}
                                for price in _ranked(prices)),
            })

    def _choose(self, prices, *, forced: bool) -> OptionPrice:
        if forced:
            return _ranked(prices)[0]
        continuing = [price for price in prices
                      if not price.ends_turn and price.swing > NOISE_FLOOR]
        if continuing:
            return _ranked(continuing)[0]
        enders = [price for price in prices if price.ends_turn]
        return _ranked(enders or prices)[0]


def _ranked(prices):
    """Best swing first; inside the noise floor the lowest engine selection wins, so the
    ordering is a total, replayable one."""
    return sorted(prices, key=lambda price: (-round(price.swing / NOISE_FLOOR) * NOISE_FLOOR,
                                             price.action.selection))


__all__ = ("LedgerDecider", "LedgerUnavailable")
