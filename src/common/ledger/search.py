from __future__ import annotations

import hashlib
import math

from common.decision import (
    CandidateDisposition,
    CandidateRoster,
    ContinuationResult,
    BudgetController,
    DecisionChoice,
    DecisionDelta,
    EvaluationStatus,
    EvaluationRequest,
    SearchResult,
    SearchValue,
    ValuationCache,
    ValuedCandidate,
)
from common.strategy.context import _MAIN

from .decision import ledger_valuation_from_state, value_components
from .preview import price_actions


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

        baseline = state_value(board)
        budget = BudgetController(configuration)
        prices = price_actions(
            root, board, baseline.total, provider, request.evaluation_model,
            configuration, budget, ledger_value, state_value)
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
        reason = "forced" if roster.forced else "best_delta"
        if not candidates:
            candidates = roster.candidates
            reason = f"unavailable_{configuration.unavailable_fallback}"
        if not candidates:
            raise ValueError("cannot choose from an empty candidate roster")
        if not roster.forced:
            continuing = tuple(
                candidate for candidate in candidates
                if candidate.disposition is CandidateDisposition.CONTINUES_TURN
                and candidate.delta is not None
                and candidate.delta.total > configuration.noise_tolerance)
            if continuing:
                candidates = continuing
                reason = "positive_continuation"
            else:
                enders = tuple(candidate for candidate in candidates
                               if candidate.disposition is CandidateDisposition.ENDS_TURN)
                if enders:
                    candidates = enders
                    reason = "best_turn_ender"
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


__all__ = ("GreedyDecisionPolicy", "LedgerOnePlySearch", "UniformPolicyModel")
