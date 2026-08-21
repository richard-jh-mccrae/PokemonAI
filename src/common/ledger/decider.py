"""The Ledger decider: spend the turn while something is worth doing, then end it best.

One rule (plan §4): while any turn-continuing option's swing clears the noise floor, take the
best of those; only when nothing is worth doing, take the best turn-ender — and ending the turn
is worth exactly zero, so a turn-ender must earn its damage. Forced menus (no End on offer) are
a straight argmax. Ties inside the noise floor break to the lowest engine selection, so a
replayed frame answers identically. Every decision reports its option prices and coverage gaps
in `RootDecision.diagnostics`; a `gap_sink` callable receives one record per decision that met
a gap — the honest worklist, counted per decision affected."""
from __future__ import annotations

import json
from dataclasses import replace

from common.api import RootDecision
from common.observation import KnownOwnPrizes, ObservationStateBuilder
from common.strategy.context import _MAIN

from .evaluate import evaluate
from .preview import NOISE_FLOOR, OptionPrice, price_actions
from .seam import LedgerNativeProvider, PreviewState
from .worth import EvaluationModel

#: Plays whose whole yield is hand cards a pending shuffle would discard: they queue BEHIND
#: it (ADR-0148). Kept narrow — a broad fetch/draw set was measured and lost frames.
_RESTOCK_TAGS = frozenset({"recycle", "recycle_line"})


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
        if context == _MAIN:
            prices = tuple(
                replace(price, restocks=True) if self._restocks_hand(price)
                else price for price in prices)
        chosen = self._choose(prices, forced=context != _MAIN)
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
                "weights": self.ctx.weights.identity,
                "evaluation_model": self.ctx.version,
                "position_key": board.position_key,
                "decision_key": board.decision_key,
                **({"opponent_gamma": round(opponent.gamma, 4)}
                   if opponent is not None else {}),
                "baseline": baseline.total, "gaps": sorted(set(gaps)),
                "prices": tuple({"action": str(price.action.identity),
                                 "selection": list(price.action.selection),
                                 "swing": price.swing, "ends_turn": price.ends_turn}
                                for price in _ranked(prices)),
            })

    def _restocks_hand(self, price) -> bool:
        identity = price.action.identity
        if identity.kind != "play":
            return False
        # Raw select options reference hand cards by POSITION; the resolved card ids live in
        # the canonical identity parts, so the played card is read from there.
        for part in identity.parts:
            try:
                payload = json.loads(part)
            except (TypeError, ValueError):
                continue
            for card_id in _card_ids(payload):
                facts = self.ctx.facts(card_id)
                if facts is not None and _RESTOCK_TAGS.intersection(
                        getattr(facts, "tags", ()) or ()):
                    return True
        return False

    def _choose(self, prices, *, forced: bool) -> OptionPrice:
        if forced:
            return _ranked(prices)[0]
        threshold = max(NOISE_FLOOR, self.ctx.weights.act_threshold)
        continuing = [price for price in prices
                      if not price.ends_turn and price.swing > threshold]
        refreshes = [price for price in continuing if price.refresh]
        if refreshes:
            # A hand-shuffle is a hand-ender (ADR-0148): spends go first (they survive it),
            # the shuffle next, recycle plays behind it — their yield would be shuffled away.
            holders = [price for price in continuing
                       if not price.refresh and not price.restocks]
            return _ranked(holders or refreshes)[0]
        if continuing:
            return _ranked(continuing)[0]
        enders = [price for price in prices if price.ends_turn]
        return _ranked(enders or prices)[0]


def _card_ids(node):
    """Card ids referenced inside one raw select option: dicts with an `id` and no board-body
    shape (`hp`) are card refs, wherever the option nests them."""
    if isinstance(node, dict):
        if node.get("id") is not None and "hp" not in node:
            yield int(node["id"])
        for value in node.values():
            yield from _card_ids(value)
    elif isinstance(node, (list, tuple)):
        for value in node:
            yield from _card_ids(value)


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
