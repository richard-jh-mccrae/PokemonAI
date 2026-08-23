from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

from common.decision import (
    CandidateDisposition,
    CandidateRoster,
    ContinuationResult,
    BudgetController,
    DecisionChoice,
    DecisionDelta,
    DecisionFailure,
    DecisionFailureStage,
    DecisionReason,
    EvaluationStatus,
    EvaluationRequest,
    FailSafeRequest,
    SearchResult,
    SearchValue,
    StateValuation,
    ValuationCache,
    ValuedCandidate,
    safe_legal_selection,
)
from common.observation.provider import provider_payload
from common.strategy.context import _MAIN

from .decision import ledger_valuation_from_state, value_components
from .preview import price_actions


class DecisionExecutionError(RuntimeError):
    def __init__(self, failure: DecisionFailure):
        super().__init__(failure.message)
        self.failure = failure


@dataclass
class TransitionProviderSource:
    factory: object
    state: object
    kwargs: dict
    instance: object | None = None
    close_failure: DecisionFailure | None = None

    def open(self):
        if self.instance is None:
            self.instance = self.factory(self.state, **self.kwargs)
        return self.instance

    def close(self):
        close = getattr(self.instance, "close", None)
        if close is not None:
            try:
                close()
            except Exception as exc:
                self.close_failure = DecisionFailure.capture(DecisionFailureStage.PROVIDER, exc)


class UniformPolicyModel:
    identity = "uniform-policy-model-v1"

    def priors(self, state, actions):
        del state
        probability = 0.0 if not actions else 1.0 / len(actions)
        return tuple(probability for _action in actions)


class LedgerOnePlySearch:
    identity = "ledger-one-ply-v1"

    def search(self, request, evaluator, policy_model, provider, configuration):
        root = request.state
        board = getattr(root, "observation", root)
        cache = ValuationCache()

        def state_value(state):
            parent = request.parent_valuation if state is board else None
            delta = request.observation_delta if state is board else None
            return cache.evaluate(EvaluationRequest(
                state, request.evaluation_model, parent, delta), evaluator)

        def ledger_value(state):
            return ledger_valuation_from_state(state_value(state))

        try:
            baseline = state_value(board)
        except Exception as exc:
            raise DecisionExecutionError(DecisionFailure.capture(
                DecisionFailureStage.EVALUATION, exc)) from exc
        actions = tuple(root.legal_actions)
        if board.select is not None and len(actions) == 1:
            candidate = ValuedCandidate(
                actions[0],
                DecisionDelta(0.0, baseline.scale),
                CandidateDisposition.FORCED,
                EvaluationStatus.COMPLETE,
                search_value=SearchValue(baseline.total, baseline.scale),
                prior=1.0,
                policy_evidence=baseline.evidence,
            )
            return SearchResult(
                baseline,
                CandidateRoster((candidate,), forced=True),
                stop_reason="forced",
            )
        budget = BudgetController(configuration)
        try:
            provider = provider.open() if isinstance(provider, TransitionProviderSource) else provider
            if not getattr(provider, "available", True):
                raise RuntimeError(str(getattr(provider, "_error", "provider unavailable")))
        except Exception as exc:
            raise DecisionExecutionError(DecisionFailure.capture(
                DecisionFailureStage.PROVIDER, exc)) from exc
        try:
            prices = price_actions(
                root, board, baseline.total, provider, request.evaluation_model,
                configuration, budget, ledger_value, state_value)
        except Exception as exc:
            raise DecisionExecutionError(DecisionFailure.capture(
                DecisionFailureStage.SEARCH, exc)) from exc
        context_value = None if board.select is None else board.select.context
        forced = (_MAIN if context_value is None else int(context_value)) != _MAIN
        prior_values = policy_model.priors(board, tuple(price.action for price in prices))
        if len(prior_values) != len(prices):
            raise ValueError("policy model must return one prior per candidate")
        if (any(not math.isfinite(prior) or prior < 0.0 for prior in prior_values)
                or (prior_values and not math.isclose(sum(prior_values), 1.0,
                                                      rel_tol=1e-9, abs_tol=1e-9))):
            raise ValueError("policy priors must be a finite normalized distribution")
        candidates = []
        for price, prior in zip(prices, prior_values):
            disposition = (CandidateDisposition.FORCED if forced else
                           CandidateDisposition.ENDS_TURN if price.ends_turn else
                           CandidateDisposition.CONTINUES_TURN)
            components = value_components(price.footprint.contributions)
            delta = (None if price.status is EvaluationStatus.UNAVAILABLE else
                     DecisionDelta(price.swing, baseline.scale, components))
            footprint = price.footprint
            continuation = ContinuationResult(
                footprint.state_delta,
                footprint.action_opportunity,
                footprint.continues_turn,
                footprint.zones_created,
                footprint.zones_replaced,
                footprint.allowances_consumed,
                footprint.immediately_usable_outputs,
                footprint.opportunities_created,
                footprint.opportunities_preserved,
                footprint.opportunities_consumed,
            )
            successors = price.successors
            if any(successor.valuation.scale != baseline.scale for successor in successors):
                raise ValueError("search cannot mix value scales")
            candidates.append(ValuedCandidate(
                price.action, delta, disposition, price.status,
                successors, price.gaps, continuation,
                None if delta is None else SearchValue(
                    baseline.total + delta.total, baseline.scale),
                prior,
                (() if price.prize_map is None else price.prize_map.plan_rank_key()),
                price.prize_map))
        return SearchResult(
            baseline,
            CandidateRoster(tuple(candidates), forced),
            nodes_visited=budget.nodes,
            stop_reason=budget.stop_reason,
            frontier=tuple(budget.frontier),
        )


class GreedyDecisionPolicy:
    identity = "ledger-spend-then-end-v1"

    def choose(self, roster, configuration):
        candidates = tuple(candidate for candidate in roster.candidates
                           if candidate.delta is not None
                           and candidate.status.value in configuration.accepted_statuses)
        reason = DecisionReason.FORCED if roster.forced else DecisionReason.BEST_DELTA
        if not candidates:
            detail = tuple((str(candidate.action.identity), candidate.status.value, candidate.gaps)
                           for candidate in roster.candidates)
            raise ValueError(f"normal policy received no comparable candidates: {detail}")
        if not roster.forced:
            continuing = tuple(
                candidate for candidate in candidates
                if candidate.disposition is CandidateDisposition.CONTINUES_TURN
                and candidate.delta is not None
                and candidate.delta.total > configuration.noise_tolerance)
            if continuing:
                candidates = continuing
                reason = DecisionReason.POSITIVE_CONTINUATION
            else:
                enders = tuple(candidate for candidate in candidates
                               if candidate.disposition is CandidateDisposition.ENDS_TURN)
                if enders:
                    candidates = enders
                    reason = DecisionReason.BEST_TURN_ENDER
        return DecisionChoice(self._ranked(candidates, configuration)[0].action, reason)

    @staticmethod
    def _ranked(candidates, configuration):
        indexed = list(enumerate(candidates))

        def value(candidate):
            return float("-inf") if candidate.delta is None else candidate.delta.total

        ranked = []
        while indexed:
            best = max(value(candidate) for _index, candidate in indexed)
            tied = tuple(
                (index, candidate) for index, candidate in indexed
                if best == float("-inf")
                or best - value(candidate) <= configuration.noise_tolerance)
            exact = all(value(candidate) == best for _index, candidate in tied)
            tied = tuple(sorted(tied, key=lambda item: (
                item[1].policy_tie_break if exact else (),
                hashlib.blake2b(
                    f"{configuration.tie_seed}:{item[0]}".encode("utf-8"),
                    digest_size=8).digest())))
            ranked.extend(candidate for _index, candidate in tied)
            used = {index for index, _candidate in tied}
            indexed = [(index, candidate) for index, candidate in indexed
                       if index not in used]
        return tuple(ranked)


class FailSafeDecisionPolicy:
    identity = "ledger-fail-safe-v1"

    _REASONS = {
        DecisionFailureStage.EVALUATION: DecisionReason.FAIL_SAFE_EVALUATION_FAILURE,
        DecisionFailureStage.PROVIDER: DecisionReason.FAIL_SAFE_PROVIDER_FAILURE,
        DecisionFailureStage.SEARCH: DecisionReason.FAIL_SAFE_SEARCH_FAILURE,
        DecisionFailureStage.POLICY: DecisionReason.FAIL_SAFE_POLICY_FAILURE,
        DecisionFailureStage.RUNTIME: DecisionReason.FAIL_SAFE_RUNTIME_FAILURE,
    }

    def choose(self, roster, configuration, state, failure):
        del configuration
        payload = state.observation if isinstance(state, FailSafeRequest) else provider_payload(state)
        selection = tuple(safe_legal_selection(payload))
        candidate = next((item for item in roster.candidates
                          if selection in getattr(item.action, "equivalent_selections", ())), None)
        if candidate is None:
            candidate = min(roster.candidates, key=lambda item: item.action.selection)
        return DecisionChoice(candidate.action, self._REASONS[failure.stage])


def unavailable_ledger_result(request, failure):
    from .decision import LEDGER_VALUE_SCALE, LedgerValueEvaluator

    root = request.state
    fail_safe = isinstance(root, FailSafeRequest)
    board = None if fail_safe else getattr(root, "observation", root)
    baseline = StateValuation(
        root.state_key if fail_safe else board.position_key,
        0.0, LEDGER_VALUE_SCALE, root.seat if fail_safe else board.seat,
        LedgerValueEvaluator.identity, status=EvaluationStatus.UNAVAILABLE,
        gaps=(f"{failure.stage.value}:{failure.error_type}",),
    )
    actions = tuple(root.legal_actions)
    forced = len(actions) == 1
    candidates = tuple(ValuedCandidate(
        action, None,
        CandidateDisposition.FORCED if forced else
        CandidateDisposition.ENDS_TURN if action.identity.kind == "end" else
        CandidateDisposition.CONTINUES_TURN,
        EvaluationStatus.UNAVAILABLE,
        gaps=baseline.gaps,
    ) for action in actions)
    return SearchResult(
        baseline, CandidateRoster(candidates, forced), stop_reason=failure.stage.value,
        failure=failure)


__all__ = ("FailSafeDecisionPolicy", "GreedyDecisionPolicy", "LedgerOnePlySearch",
           "TransitionProviderSource", "UniformPolicyModel", "unavailable_ledger_result")
