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
from common.strategy.context import _MAIN

from .evaluate import evaluate
from .preview import NOISE_FLOOR, OptionPrice, price_actions
from .seam import LedgerNativeProvider, PreviewState
from .worth import LedgerContext


class LedgerUnavailable(RuntimeError):
    """The transition seam could not open for this observation."""


class LedgerDecider:
    def __init__(self, deck, deck_name: str, ctx: LedgerContext, *,
                 provider_factory=LedgerNativeProvider, gap_sink=None):
        self.deck = tuple(int(card_id) for card_id in deck)
        self.deck_name = str(deck_name)
        self.ctx = ctx
        self.provider_factory = provider_factory
        self.gap_sink = gap_sink

    def decide(self, observation) -> RootDecision:
        board = BoardState.root(observation, decklist=self.deck)
        # The root is a PreviewState too: deck knowledge comes from BoardState, so the Ledger
        # path constructs no DecisionState anywhere (pinned by tests/ledger/test_seam.py).
        state = PreviewState(observation, board.seat, "root", deck=self.deck,
                             deck_counts=board.deck_counts or (),
                             prize_counts=board.own_prizes or ())
        baseline = evaluate(board, self.ctx)
        provider = self.provider_factory(state)
        if not getattr(provider, "available", True):
            _close_quietly(provider)               # a half-opened engine session must not leak
            raise LedgerUnavailable(str(getattr(provider, "_error", "provider unavailable")))
        try:
            prices = price_actions(state, board, baseline.total, provider, self.ctx)
        finally:
            # A close() failing on an already-broken session must not mask the pricing outcome.
            _close_quietly(provider)
        if not prices:
            raise LedgerUnavailable("no legal actions to price")

        raw_context = (observation.get("select") or {}).get("context")
        context = _MAIN if raw_context is None else int(raw_context)
        chosen = self._choose(prices, forced=context != _MAIN)
        gaps = tuple(gap for price in prices for gap in price.gaps) + baseline.gaps
        if gaps and self.gap_sink is not None:
            self.gap_sink({"context": context, "board": board.key, "gaps": sorted(set(gaps)),
                           "chosen": list(chosen.action.selection)})
        return RootDecision(
            chosen=tuple(chosen.action.selection), action=chosen.action.identity,
            value=chosen.swing, complete=True,
            diagnostics={
                "backend": "ledger", "deck": self.deck_name,
                "weights": self.ctx.weights.identity,
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


def _close_quietly(provider) -> None:
    close = getattr(provider, "close", None)
    if close is None:
        return
    try:
        close()
    except Exception:
        pass


def _ranked(prices):
    """Best swing first; inside the noise floor the lowest engine selection wins, so the
    ordering is a total, replayable one."""
    return sorted(prices, key=lambda price: (-round(price.swing / NOISE_FLOOR) * NOISE_FLOOR,
                                             price.action.selection))


__all__ = ("LedgerDecider", "LedgerUnavailable")
