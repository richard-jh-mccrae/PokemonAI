"""The Ledger decider: spend the turn while something is worth doing, then end it best.

One rule (plan §4): while any turn-continuing option's swing clears the noise floor, take the
best of those; only when nothing is worth doing, take the best turn-ender — and ending the turn
is worth exactly zero, so a turn-ender must earn its damage. Forced menus (no End on offer) are
a straight argmax. Ties inside the noise floor use a seeded neutral lottery. Every decision
reports its option prices and coverage gaps
in `RootDecision.diagnostics`; a `gap_sink` callable receives one record per decision that met
a gap — the honest worklist, counted per decision affected."""
from __future__ import annotations

import hashlib

from common.api import RootDecision
from common.observation import KnownOwnPrizes, ObservationStateBuilder
from common.strategy.context import _MAIN

from .evaluate import evaluate
from .preview import OptionPrice, price_actions
from .seam import LedgerNativeProvider, PreviewState
from .worth import EvaluationModel

class LedgerUnavailable(RuntimeError):
    """The transition seam could not open for this observation."""


class LedgerDecider:
    def __init__(self, deck, deck_name: str, ctx: EvaluationModel, *,
                 provider_factory=LedgerNativeProvider, provider_kwargs=None, gap_sink=None):
        self.deck = tuple(int(card_id) for card_id in deck)
        self.deck_name = str(deck_name)
        self.ctx = ctx
        self.provider_factory = provider_factory
        #: Fact sources the engine adapters read mid-transition; a bare provider prices
        #: fact-needing options (bench damage, energy typing) at zero (ADR-0148).
        self.provider_kwargs = dict(provider_kwargs or {})
        self.gap_sink = gap_sink

    def decide(self, observation, *, opponent=None, knowledge=None, state=None) -> RootDecision:
        ctx = self.ctx.with_opponent(opponent)
        board = (ObservationStateBuilder(self.deck).root(observation, knowledge=knowledge)
                 if state is None else state)
        # The root is a PreviewState too: deck knowledge comes from ObservationState, so the Ledger
        # path constructs no DecisionState anywhere (pinned by tests/ledger/test_seam.py).
        state = PreviewState(observation, board, "root", deck=self.deck,
                             deck_counts=board.deck_counts or (),
                             prize_counts=(board.knowledge.own_prizes.cards
                                           if isinstance(board.knowledge.own_prizes,
                                                         KnownOwnPrizes) else ()))
        baseline = evaluate(board, ctx)
        provider = self.provider_factory(state, **self.provider_kwargs)
        if not getattr(provider, "available", True):
            _close_quietly(provider)               # a half-opened engine session must not leak
            raise LedgerUnavailable(str(getattr(provider, "_error", "provider unavailable")))
        try:
            prices = price_actions(state, board, baseline.total, provider, ctx)
        finally:
            # A close() failing on an already-broken session must not mask the pricing outcome.
            _close_quietly(provider)
        if not prices:
            raise LedgerUnavailable("no legal actions to price")

        context_value = None if board.select is None else board.select.context
        context = _MAIN if context_value is None else int(context_value)
        chosen = self._choose(prices, forced=context != _MAIN)
        indifference_ordinals = tuple(
            index for index, price in enumerate(prices)
            if abs(price.swing - chosen.swing) <= ctx.compute.noise_tolerance)
        gaps = tuple(gap for price in prices for gap in price.gaps) + baseline.gaps
        if gaps and self.gap_sink is not None:
            self.gap_sink({"context": context, "position_key": board.position_key,
                           "decision_key": board.decision_key, "gaps": sorted(set(gaps)),
                           "chosen": list(chosen.action.selection)})
        return RootDecision(
            chosen=tuple(chosen.action.selection), action=chosen.action.identity,
            value=chosen.swing, complete=True,
            diagnostics={
                "backend": "ledger", "deck": self.deck_name,
                "valuation": self.ctx.configuration.identity,
                "compute": self.ctx.compute.identity,
                "position_key": board.position_key,
                "decision_key": board.decision_key,
                **({"opponent_unknown_mass": opponent.unknown_mass}
                   if opponent is not None else {}),
                "baseline": baseline.total, "gaps": sorted(set(gaps)),
                "indifference_ordinals": indifference_ordinals,
                "prices": tuple({"action": str(price.action.identity),
                                 "selection": list(price.action.selection),
                                 "swing": price.swing, "ends_turn": price.ends_turn,
                                 "continuation": {
                                     "state_delta": price.footprint.state_delta,
                                     "action_opportunity": price.footprint.action_opportunity,
                                     "continues_turn": price.footprint.continues_turn,
                                     "zones_created": price.footprint.zones_created,
                                     "zones_replaced": price.footprint.zones_replaced,
                                     "allowances_consumed": price.footprint.allowances_consumed,
                                     "immediately_usable_outputs":
                                         price.footprint.immediately_usable_outputs,
                                     "opportunities_created":
                                         price.footprint.opportunities_created,
                                     "opportunities_preserved":
                                         price.footprint.opportunities_preserved,
                                     "opportunities_consumed":
                                         price.footprint.opportunities_consumed,
                                     "contributions": tuple({
                                         "feature": item.feature,
                                         "activation": item.activation,
                                         "coefficient": item.coefficient,
                                         "value": item.value,
                                     } for item in price.footprint.contributions),
                                 }}
                                for price in self._ranked(prices)),
            })

    def _choose(self, prices, *, forced: bool) -> OptionPrice:
        if forced:
            return self._ranked(prices)[0]
        threshold = self.ctx.compute.noise_tolerance
        continuing = [price for price in prices
                      if not price.ends_turn and price.swing > threshold]
        if continuing:
            return self._ranked(continuing)[0]
        enders = [price for price in prices if price.ends_turn]
        return self._ranked(enders or prices)[0]

    def _ranked(self, prices):
        tolerance = self.ctx.compute.noise_tolerance
        seed = self.ctx.compute.tie_seed
        remaining = list(enumerate(prices))
        ranked = []
        while remaining:
            best = max(price.swing for _index, price in remaining)
            tied = [(index, price) for index, price in remaining
                    if best - price.swing <= tolerance]
            tied.sort(key=lambda indexed: hashlib.blake2b(
                f"{seed}:{indexed[0]}".encode("utf-8"), digest_size=8).digest())
            ranked.extend(price for _index, price in tied)
            tied_indices = {index for index, _price in tied}
            remaining = [(index, price) for index, price in remaining
                         if index not in tied_indices]
        return ranked


def _close_quietly(provider) -> None:
    close = getattr(provider, "close", None)
    if close is None:
        return
    try:
        close()
    except Exception:
        pass


__all__ = ("LedgerDecider", "LedgerUnavailable")
