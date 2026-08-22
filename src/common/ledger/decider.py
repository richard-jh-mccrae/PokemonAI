"""The Ledger decider: spend the turn while something is worth doing, then end it best.

One rule (plan §4): while any turn-continuing option's swing clears the noise floor, take the
best of those; only when nothing is worth doing, take the best turn-ender — and ending the turn
is worth exactly zero, so a turn-ender must earn its damage. Forced menus (no End on offer) are
a straight argmax. Ties inside the noise floor use a seeded neutral lottery. Every decision
reports its option prices and coverage gaps
in `RootDecision.diagnostics`; a `gap_sink` callable receives one record per decision that met
a gap — the honest worklist, counted per decision affected."""
from __future__ import annotations

from common.api import RootDecision
from common.decision import DecisionCoordinator
from common.observation import (KnownOwnPrizes, ObservationStateBuilder, OpponentBelief,
                                reduce_knowledge)
from common.strategy.context import _MAIN

from .decision import LedgerValueEvaluator
from .configuration import BehaviorIdentity
from .search import GreedyDecisionPolicy, LedgerOnePlySearch, UniformPolicyModel
from .seam import LedgerNativeProvider, PreviewState
from .worth import EvaluationModel

class LedgerUnavailable(RuntimeError):
    """The transition seam could not open for this observation."""


class LedgerDecider:
    def __init__(self, deck, deck_name: str, ctx: EvaluationModel, *,
                 provider_factory=LedgerNativeProvider, provider_kwargs=None, gap_sink=None,
                 compute=None, parity_oracle=None):
        self.deck = tuple(int(card_id) for card_id in deck)
        self.deck_name = str(deck_name)
        self.ctx = ctx
        from common.decision import ComputeConfiguration
        self.compute = compute or ComputeConfiguration()
        self.provider_factory = provider_factory
        #: Fact sources the engine adapters read mid-transition; a bare provider prices
        #: fact-needing options (bench damage, energy typing) at zero (ADR-0148).
        self.provider_kwargs = dict(provider_kwargs or {})
        self.gap_sink = gap_sink
        self.parity_oracle = parity_oracle

    @property
    def behavior_identity(self) -> BehaviorIdentity:
        provider = self.provider_factory
        target = getattr(provider, "func", provider)
        provider_name = (getattr(provider, "backend", None)
                         or f"{target.__module__}.{target.__qualname__}")
        return BehaviorIdentity(
            LedgerValueEvaluator.identity,
            self.ctx.identity,
            LedgerOnePlySearch.identity,
            UniformPolicyModel.identity,
            GreedyDecisionPolicy.identity,
            provider_name,
            self.compute.identity,
            self.ctx.prize_plan.identity,
        )

    def decide(self, observation, *, opponent=None, knowledge=None, state=None) -> RootDecision:
        ctx = self.ctx
        known = knowledge if state is None else state.knowledge
        if opponent is not None and (known is None
                                     or known.opponent.decision_evidence is None):
            known = reduce_knowledge(
                known or ObservationStateBuilder(self.deck).root(observation).knowledge,
                opponent=OpponentBelief.from_snapshot(opponent))
            knowledge, state = known, None
        board = (ObservationStateBuilder(self.deck).root(observation, knowledge=knowledge)
                 if state is None else state)
        # The root is a PreviewState too: deck knowledge comes from ObservationState, so the Ledger
        # path constructs no DecisionState anywhere (pinned by tests/ledger/test_seam.py).
        state = PreviewState(observation, board, "root", deck=self.deck,
                             deck_counts=board.deck_counts or (),
                             prize_counts=(board.knowledge.own_prizes.cards
                                           if isinstance(board.knowledge.own_prizes,
                                                         KnownOwnPrizes) else ()))
        provider = self.provider_factory(state, **self.provider_kwargs)
        if not getattr(provider, "available", True):
            _close_quietly(provider)               # a half-opened engine session must not leak
            raise LedgerUnavailable(str(getattr(provider, "_error", "provider unavailable")))
        try:
            search_configuration, policy_configuration = self._configurations(self.compute)
            coordinator = DecisionCoordinator(
                evaluator=LedgerValueEvaluator(),
                evaluation_model=ctx,
                search=LedgerOnePlySearch(),
                search_configuration=search_configuration,
                policy_model=UniformPolicyModel(),
                decision_policy=GreedyDecisionPolicy(),
                policy_configuration=policy_configuration,
                behavior_identity=self.behavior_identity,
            )
            result = coordinator.decide(state, provider=provider)
            if self.parity_oracle is not None:
                self.parity_oracle(
                    state=state, board=board, provider=provider, evaluation_model=ctx,
                    result=result, search_configuration=search_configuration,
                    policy_configuration=policy_configuration)
        finally:
            # A close() failing on an already-broken session must not mask the pricing outcome.
            _close_quietly(provider)
        if not result.roster.candidates:
            raise LedgerUnavailable("no legal actions to price")

        candidates = result.roster.candidates
        chosen = next(candidate for candidate in candidates
                      if candidate.action is result.chosen)
        context_value = None if board.select is None else board.select.context
        context = _MAIN if context_value is None else int(context_value)
        chosen_value = None if chosen.delta is None else chosen.delta.total
        indifference_ordinals = tuple(
            index for index, candidate in enumerate(candidates)
            if chosen_value is not None and candidate.delta is not None
            and abs(candidate.delta.total - chosen_value) <= policy_configuration.noise_tolerance)
        gaps = (tuple(gap for candidate in candidates for gap in candidate.gaps)
                + result.baseline.gaps)
        if gaps and self.gap_sink is not None:
            self.gap_sink({"context": context, "position_key": board.position_key,
                           "decision_key": board.decision_key, "gaps": sorted(set(gaps)),
                           "chosen": list(chosen.action.selection)})
        ranked = GreedyDecisionPolicy._ranked(candidates, policy_configuration)
        return RootDecision(
            chosen=tuple(chosen.action.selection), action=chosen.action.identity,
            value=0.0 if chosen_value is None else chosen_value,
            complete=chosen_value is not None,
            diagnostics={
                "backend": "ledger", "deck": self.deck_name,
                "valuation": self.ctx.configuration.identity,
                "compute": self.compute.identity,
                "prize_plan": self.ctx.prize_plan.identity,
                "behavior": self.behavior_identity,
                "policy_reason": result.policy_reason,
                "decision_parity": self.parity_oracle is not None,
                "search": {
                    "nodes_visited": result.trace.nodes_visited,
                    "stop_reason": result.trace.stop_reason,
                    "frontier": result.trace.frontier,
                },
                "position_key": board.position_key,
                "decision_key": board.decision_key,
                "prize_map": (chosen.policy_evidence.as_dict()
                              if chosen.policy_evidence is not None else None),
                **({"opponent_unknown_mass": opponent.unknown_mass}
                   if opponent is not None else {}),
                "baseline": result.baseline.total, "gaps": sorted(set(gaps)),
                "indifference_ordinals": indifference_ordinals,
                "prices": tuple({"action": str(candidate.action.identity),
                                 "selection": list(candidate.action.selection),
                                 "swing": (None if candidate.delta is None
                                           else candidate.delta.total),
                                 "ends_turn": not candidate.continuation.continues_turn,
                                 "status": candidate.status.value,
                                 "continuation": {
                                     "state_delta": candidate.continuation.state_delta,
                                     "action_opportunity": candidate.continuation.action_opportunity,
                                     "continues_turn": candidate.continuation.continues_turn,
                                     "zones_created": candidate.continuation.zones_created,
                                     "zones_replaced": candidate.continuation.zones_replaced,
                                     "allowances_consumed": candidate.continuation.allowances_consumed,
                                     "immediately_usable_outputs":
                                         candidate.continuation.immediately_usable_outputs,
                                     "opportunities_created":
                                         candidate.continuation.opportunities_created,
                                     "opportunities_preserved":
                                         candidate.continuation.opportunities_preserved,
                                     "opportunities_consumed":
                                         candidate.continuation.opportunities_consumed,
                                     "contributions": tuple({
                                         "feature": item.key,
                                         "activation": item.activation,
                                         "coefficient": item.coefficient,
                                         "value": item.value,
                                     } for item in (() if candidate.delta is None
                                                   else candidate.delta.components)),
                                 }}
                                for candidate in ranked),
            })

    @staticmethod
    def _configurations(compute):
        return compute.search, compute.policy

def _close_quietly(provider) -> None:
    close = getattr(provider, "close", None)
    if close is None:
        return
    try:
        close()
    except Exception:
        pass


__all__ = ("LedgerDecider", "LedgerUnavailable")
