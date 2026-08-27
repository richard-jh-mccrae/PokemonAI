"""The Ledger decider: spend the turn while something is worth doing, then end it best.

One rule (plan §4): while any turn-continuing option's swing clears the noise floor, take the
best of those; only when nothing is worth doing, take the best turn-ender — and ending the turn
is worth exactly zero, so a turn-ender must earn its damage. Forced menus (no End on offer) are
a straight argmax. Ties inside the noise floor use a seeded neutral lottery. Every decision
reports its option prices and coverage gaps
in `RootDecision.diagnostics`; a `gap_sink` callable receives one record per decision that met
a gap — the honest worklist, counted per decision affected."""
from __future__ import annotations

import os
import sys
import hashlib
import json
from collections.abc import Mapping

from common.api import RootDecision
from common.decision import (DecisionCoordinator, DecisionFailure, DecisionFailureStage,
                             FailSafeRequest, fail_safe_request)
from common.observation import (KnownOwnPrizes, ObservationStateBuilder, OpponentBelief,
                                reduce_knowledge)
from common.strategy.context import _MAIN

from .decision import LedgerValueEvaluator
from .configuration import BehaviorIdentity
from .search import (FailSafeDecisionPolicy, GreedyDecisionPolicy, LedgerOnePlySearch,
                     TransitionProviderSource, UniformPolicyModel, unavailable_ledger_result)
from .seam import LedgerNativeProvider, PreviewState
from .worth import EvaluationModel


PROVIDER_ID_DIGEST_BYTES = 16

class LedgerUnavailable(RuntimeError):
    """The transition seam could not open for this observation."""


class DecisionPostprocessingError(RuntimeError):
    coordinator_entered = True


def _provider_descriptor(factory, kwargs) -> dict:
    target = getattr(factory, "func", factory)
    factory_name = f"{target.__module__}.{target.__qualname__}"
    return {
        "backend": getattr(target, "backend", None) or f"python:{factory_name}",
        "factory": factory_name,
        "version": getattr(target, "version", None),
        "kwargs": _identity_input(kwargs),
        "factory_kwargs": _identity_input(getattr(factory, "keywords", None) or {}),
    }


def _provider_identity(factory, kwargs) -> str:
    descriptor = _provider_descriptor(factory, kwargs)
    blob = json.dumps(descriptor, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.blake2b(blob, digest_size=PROVIDER_ID_DIGEST_BYTES).hexdigest()


def _identity_input(value):
    if isinstance(value, Mapping):
        return {str(key): _identity_input(child)
                for key, child in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (tuple, list)):
        return [_identity_input(child) for child in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_identity_input(child) for child in value), key=repr)
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    identity = getattr(value, "identity", None)
    if identity is not None:
        return {"type": f"{type(value).__module__}.{type(value).__qualname__}",
                "identity": str(identity)}
    if callable(value):
        return {"callable": f"{value.__module__}.{value.__qualname__}"}
    raise TypeError(
        f"provider identity input {type(value).__module__}.{type(value).__qualname__} "
        "must expose an identity")


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
        descriptor = _provider_descriptor(self.provider_factory, self.provider_kwargs)
        self._provider_configuration = {
            "identity": _provider_identity(self.provider_factory, self.provider_kwargs),
            **descriptor,
        }
        self._behavior_identity = None
        self.gap_sink = gap_sink
        self.parity_oracle = parity_oracle
        self._search = LedgerOnePlySearch()
        self.coordinator = self._build_coordinator()
        self.last_valuation = None

    def reset_turn(self) -> None:
        self.last_valuation = None
        self._search.reset()

    @property
    def provider_configuration(self) -> dict:
        return dict(self._provider_configuration)

    @property
    def behavior_identity(self) -> BehaviorIdentity:
        if self._behavior_identity is None:
            self._behavior_identity = BehaviorIdentity(
                LedgerValueEvaluator.identity,
                self.ctx.identity,
                LedgerOnePlySearch.identity,
                UniformPolicyModel.identity,
                GreedyDecisionPolicy.identity,
                FailSafeDecisionPolicy.identity,
                self._provider_configuration["identity"],
                self.compute.identity,
                self.ctx.prize_plan.identity,
            )
        return self._behavior_identity

    def decide(self, observation, *, opponent=None, knowledge=None, state=None,
               parent_valuation=None, observation_delta=None) -> RootDecision:
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
        provider = TransitionProviderSource(self.provider_factory, state, self.provider_kwargs)
        coordinator_entered = False
        try:
            try:
                coordinator_entered = True
                result = self.coordinator.decide(
                    state, provider=provider,
                    parent_valuation=parent_valuation,
                    observation_delta=observation_delta,
                    strict=os.environ.get("AGENT_BRAIN_STRICT") == "1")
                self.last_valuation = result.baseline
                search_configuration, policy_configuration = self._configurations(self.compute)
                if self.parity_oracle is not None and provider.instance is not None:
                    self.parity_oracle(
                        state=state, board=board, provider=provider.instance,
                        evaluation_model=ctx, result=result,
                        search_configuration=search_configuration,
                        policy_configuration=policy_configuration)
            finally:
                provider.close()
            try:
                return self._root_decision(
                    result, board, opponent, policy_configuration,
                    decision_parity=(self.parity_oracle is not None
                                     and provider.instance is not None),
                    cleanup_failure=provider.close_failure)
            except LedgerUnavailable:
                raise
            except Exception as exc:
                failure = DecisionFailure.capture(DecisionFailureStage.PRESENTATION, exc)
                result = self.coordinator.recover(state, result.search, failure)
                self.gap_sink = None
                try:
                    return self._root_decision(
                        result, board, opponent, policy_configuration,
                        decision_parity=False, cleanup_failure=provider.close_failure)
                except Exception:
                    return self._emergency_projection(result)
        except Exception as exc:
            if isinstance(exc, LedgerUnavailable):
                raise
            if coordinator_entered:
                raise DecisionPostprocessingError(str(exc)) from exc
            raise

    def fail_safe(self, observation, failure, *, opponent=None, knowledge=None, state=None):
        if state is None:
            try:
                board = ObservationStateBuilder(self.deck).root(
                    observation, knowledge=knowledge)
            except Exception:
                board = None
        else:
            board = state
        request = fail_safe_request(observation) if board is None else None
        root = (request if request is not None else
                PreviewState(observation, board, "root", deck=self.deck,
                             deck_counts=board.deck_counts or (),
                             prize_counts=(board.knowledge.own_prizes.cards
                                           if isinstance(board.knowledge.own_prizes,
                                                         KnownOwnPrizes) else ())))
        result = self.coordinator.decide(root, failure=failure)
        _search, policy_configuration = self._configurations(self.compute)
        return self._root_decision(
            result, board, opponent, policy_configuration, decision_parity=False,
            fail_safe_request=request)

    def _build_coordinator(self):
        search_configuration, policy_configuration = self._configurations(self.compute)
        return DecisionCoordinator(
            evaluator=LedgerValueEvaluator(),
            evaluation_model=self.ctx,
            search=self._search,
            search_configuration=search_configuration,
            policy_model=UniformPolicyModel(),
            decision_policy=GreedyDecisionPolicy(),
            policy_configuration=policy_configuration,
            behavior_identity=self.behavior_identity,
            fail_safe_policy=FailSafeDecisionPolicy(),
            failure_handler=unavailable_ledger_result,
        )

    @staticmethod
    def _emergency_projection(result):
        chosen = result.chosen_candidate
        if chosen is None:
            raise LedgerUnavailable("no chosen candidate")
        value = None if chosen.delta is None else chosen.delta.total
        failure = result.search.failure
        return RootDecision(
            chosen=tuple(chosen.action.selection), action=chosen.action.identity,
            value=0.0 if value is None else value, complete=value is not None,
            diagnostics={
                "backend": "ledger", "behavior": result.behavior_identity,
                "policy_reason": getattr(result.policy_reason, "value", result.policy_reason),
                "failure": None if failure is None else {
                    "stage": failure.stage.value, "error_type": failure.error_type,
                    "message": failure.message, "traceback_tail": failure.traceback_tail,
                },
            },
            decision_result=result,
        )

    def _root_decision(self, result, board, opponent, policy_configuration, *,
                       decision_parity, cleanup_failure=None,
                       fail_safe_request: FailSafeRequest | None = None):
        if not result.roster.candidates:
            raise LedgerUnavailable("no legal actions to price")
        failure = result.search.failure
        if failure is not None:
            print(
                f"LEDGER-CRASH stage={failure.stage.value} "
                f"{failure.error_type}: {failure.message}\n{failure.traceback_tail}",
                file=sys.stderr, flush=True,
            )
        if cleanup_failure is not None:
            print(
                f"LEDGER-CRASH stage=provider cleanup {cleanup_failure.error_type}: "
                f"{cleanup_failure.message}\n{cleanup_failure.traceback_tail}",
                file=sys.stderr, flush=True,
            )

        candidates = result.roster.candidates
        chosen = result.chosen_candidate
        if chosen is None:
            raise LedgerUnavailable("no chosen candidate")
        context_value = (fail_safe_request.context if fail_safe_request is not None else
                         None if board.select is None else board.select.context)
        context = _MAIN if context_value is None else int(context_value)
        chosen_value = None if chosen.delta is None else chosen.delta.total
        indifference_ordinals = tuple(
            index for index, candidate in enumerate(candidates)
            if chosen_value is not None and candidate.delta is not None
            and abs(candidate.delta.total - chosen_value) <= policy_configuration.noise_tolerance)
        gaps = (tuple(gap for candidate in candidates for gap in candidate.gaps)
                + result.baseline.gaps)
        if gaps and self.gap_sink is not None:
            self.gap_sink({"context": context,
                           "position_key": (fail_safe_request.state_key
                                            if fail_safe_request is not None
                                            else board.position_key),
                           "decision_key": (fail_safe_request.decision_key
                                            if fail_safe_request is not None
                                            else board.decision_key),
                           "gaps": sorted(set(gaps)),
                           "chosen": list(chosen.action.selection)})
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
                "policy_reason": getattr(result.policy_reason, "value", result.policy_reason),
                "decision_parity": decision_parity,
                "search": {
                    "nodes_visited": result.trace.nodes_visited,
                    "stop_reason": result.trace.stop_reason,
                    "frontier": result.trace.frontier,
                },
                "position_key": (fail_safe_request.state_key
                                 if fail_safe_request is not None else board.position_key),
                "decision_key": (fail_safe_request.decision_key
                                 if fail_safe_request is not None else board.decision_key),
                "prize_map": (chosen.policy_evidence.as_dict()
                              if chosen.policy_evidence is not None else None),
                **({"opponent_unknown_mass": opponent.unknown_mass}
                   if opponent is not None else {}),
                "baseline": result.baseline.total, "gaps": sorted(set(gaps)),
                **({"failure": {
                    "stage": result.search.failure.stage.value,
                    "error_type": result.search.failure.error_type,
                    "message": result.search.failure.message,
                    "traceback_tail": result.search.failure.traceback_tail,
                }} if result.search.failure is not None else {}),
                **({"cleanup_failure": {
                    "stage": cleanup_failure.stage.value,
                    "error_type": cleanup_failure.error_type,
                    "message": cleanup_failure.message,
                    "traceback_tail": cleanup_failure.traceback_tail,
                }} if cleanup_failure is not None else {}),
                "indifference_ordinals": indifference_ordinals,
                "prices": tuple({"action": str(candidate.action.identity),
                                 "selection": list(candidate.action.selection),
                                 "swing": (None if candidate.delta is None
                                           else candidate.delta.total),
                                 "ends_turn": (False if candidate.continuation is None else
                                               not candidate.continuation.continues_turn),
                                 "status": candidate.status.value,
                                 "continuation": (None if candidate.continuation is None else {
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
                                 })}
                                for candidate in candidates),
            },
            decision_result=result,
        )

    @staticmethod
    def _configurations(compute):
        return compute.search, compute.policy

__all__ = ("DecisionPostprocessingError", "LedgerDecider", "LedgerUnavailable")
