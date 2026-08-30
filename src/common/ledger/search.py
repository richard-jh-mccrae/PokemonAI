from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from pathlib import Path

from common.decision import (
    CandidateDisposition,
    CandidateRoster,
    ContinuationResult,
    BudgetController,
    DecisionChoice,
    DecisionDelta,
    DecisionDeadlineExceeded,
    DecisionFailure,
    DecisionFailureStage,
    DecisionReason,
    EvaluationStatus,
    EvaluationRequest,
    FailSafeRequest,
    SearchResult,
    SearchValue,
    StateValuation,
    ValuedCandidate,
    neutral_lottery_choice,
    safe_legal_selection,
)
from common.observation.provider import provider_payload
from common.strategy.context import _MAIN

from .decision import (evaluator_semantics_identity, ledger_valuation_from_state,
                       value_components)
from .portfolio_solver import TurnPortfolioMemo
from .preview import price_actions


LOTTERY_DIGEST_BYTES = 8
SEARCH_SEMANTICS_IDENTITY = evaluator_semantics_identity((
    Path(__file__),
    Path(__file__).with_name("chance.py"),
    Path(__file__).with_name("preview.py"),
))


def _continuation_label(identity):
    if identity.kind == "decline":
        return "decline"
    if identity.kind != "card":
        return None
    card_ids = re.findall(r'"id":(\d+)', "".join(identity.parts))
    return f"card:{card_ids[-1]}" if len(set(card_ids)) == 1 else None


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
    identity = f"uniform-policy-model-v1:{SEARCH_SEMANTICS_IDENTITY}"

    def priors(self, state, actions):
        del state
        probability = 0.0 if not actions else 1.0 / len(actions)
        return tuple(probability for _action in actions)


class LedgerOnePlySearch:
    identity = f"ledger-one-ply-v3:{SEARCH_SEMANTICS_IDENTITY}"

    def __init__(self):
        self._previous_evaluation_state = None
        self._previous_evaluator_identity = None
        self._active_continuation_policy = {}
        self._last_continuation_policies = {}
        self._served_cached_continuation = False
        self._portfolio_memo = TurnPortfolioMemo()

    def reset(self):
        self._previous_evaluation_state = None
        self._previous_evaluator_identity = None
        self._active_continuation_policy = {}
        self._last_continuation_policies = {}
        self._served_cached_continuation = False
        self._portfolio_memo.clear()

    def commit(self, action):
        if self._served_cached_continuation:
            self._served_cached_continuation = False
            return
        identity = getattr(action, "identity", action)
        self._active_continuation_policy = dict(
            self._last_continuation_policies.get(identity, ()))

    @property
    def portfolio_metrics(self):
        return self._portfolio_memo.metrics()

    def _cached_continuation(self, actions):
        menu = tuple(action.identity for action in actions)
        chosen_identity = self._active_continuation_policy.pop(menu, None)
        if chosen_identity is None:
            offered = set(menu)
            compatible = [
                (len(offered & set(cached_menu)), cached_menu, cached_choice)
                for cached_menu, cached_choice in self._active_continuation_policy.items()
                if cached_choice in offered
                and (set(cached_menu) <= offered or offered <= set(cached_menu))]
            if compatible:
                _overlap, cached_menu, chosen_identity = max(
                    compatible, key=lambda row: row[0])
                del self._active_continuation_policy[cached_menu]
        if chosen_identity is None:
            labels = {_continuation_label(action.identity): action.identity
                      for action in actions}
            offered = set(labels) - {None}
            compatible = [
                (len(offered & set(cached_menu)), cached_menu, cached_choice)
                for cached_menu, cached_choice in self._active_continuation_policy.items()
                if isinstance(cached_choice, str) and cached_choice in offered
                and (set(cached_menu) <= offered or offered <= set(cached_menu))]
            if compatible:
                _overlap, cached_menu, cached_choice = max(
                    compatible, key=lambda row: row[0])
                del self._active_continuation_policy[cached_menu]
                chosen_identity = labels[cached_choice]
        if chosen_identity is None:
            return None
        self._served_cached_continuation = True
        return chosen_identity

    def search(self, request, evaluator, policy_model, provider, configuration):
        root = request.state
        board = getattr(root, "observation", root)
        state_values = {}
        evaluation_states = {}

        def check_guard():
            if request.execution_guard is not None:
                request.execution_guard.check()

        check_guard()

        def evaluation_key(observed):
            return (evaluator.identity, request.evaluation_model.identity,
                    observed.seat, observed.valuation_key)

        def state_value(state):
            parent = request.parent_valuation if state is board else None
            delta = request.observation_delta if state is board else None
            reusable_parent = (
                self._previous_evaluation_state
                if state is board and parent is not None
                and self._previous_evaluation_state is not None
                and self._previous_evaluator_identity == evaluator.identity
                and getattr(parent, "cache_key", None)
                == self._previous_evaluation_state.valuation_key
                else None)
            observed = getattr(state, "observation", state)
            lineage = getattr(provider, "_preview_lineage", {}).get(
                observed.valuation_key)
            if lineage is not None:
                parent_board, delta = lineage
                parent = state_value(parent_board)
                reusable_parent = evaluation_states.get(evaluation_key(parent_board))
            child_request = EvaluationRequest(
                state, request.evaluation_model, parent, delta,
                self._portfolio_memo, request.execution_guard)
            key = evaluation_key(observed)
            if key not in state_values:
                check_guard()
                if hasattr(evaluator, "evaluate_with_state"):
                    value, evaluation_state = evaluator.evaluate_with_state(
                        child_request, reusable_parent)
                    evaluation_states[key] = evaluation_state
                else:
                    value = evaluator.evaluate(child_request)
                state_values[key] = value
                check_guard()
            return state_values[key]

        def ledger_value(state):
            return ledger_valuation_from_state(state_value(state))

        try:
            baseline = state_value(board)
        except DecisionDeadlineExceeded:
            raise
        except Exception as exc:
            raise DecisionExecutionError(DecisionFailure.capture(
                DecisionFailureStage.EVALUATION, exc)) from exc
        self._previous_evaluation_state = evaluation_states.get(evaluation_key(board))
        self._previous_evaluator_identity = evaluator.identity
        actions = tuple(root.legal_actions)
        cached_identity = self._cached_continuation(actions)
        if cached_identity is None:
            self._active_continuation_policy = {}
        budget = BudgetController(configuration)
        if hasattr(budget, "check"):
            budget.check()
        if (cached_identity is None and len(actions) == 1
                and actions[0].identity.kind == "end"
                and isinstance(provider, TransitionProviderSource)):
            candidate = ValuedCandidate(
                actions[0], None, CandidateDisposition.FORCED,
                EvaluationStatus.UNAVAILABLE,
                gaps=("forced action not priced",), prior=1.0)
            return SearchResult(
                baseline,
                CandidateRoster.from_legal_actions(
                    actions, (candidate,), forced=True),
                nodes_visited=budget.nodes,
                stop_reason=budget.stop_reason,
                frontier=tuple(budget.frontier),
            )
        try:
            check_guard()
            provider = provider.open() if isinstance(provider, TransitionProviderSource) else provider
            if not getattr(provider, "available", True):
                raise RuntimeError(str(getattr(provider, "_error", "provider unavailable")))
            check_guard()
        except DecisionDeadlineExceeded:
            raise
        except Exception as exc:
            raise DecisionExecutionError(DecisionFailure.capture(
                DecisionFailureStage.PROVIDER, exc)) from exc
        try:
            prices = price_actions(
                root, board, baseline.total, provider, request.evaluation_model,
                configuration, None if cached_identity is not None else budget,
                ledger_value, state_value)
            check_guard()
        except DecisionDeadlineExceeded:
            raise
        except Exception as exc:
            raise DecisionExecutionError(DecisionFailure.capture(
                DecisionFailureStage.SEARCH, exc)) from exc
        context_value = None if board.select is None else board.select.context
        forced = (cached_identity is not None
                  or (_MAIN if context_value is None else int(context_value)) != _MAIN)
        prior_values = policy_model.priors(board, tuple(price.action for price in prices))
        if len(prior_values) != len(prices):
            raise ValueError("policy model must return one prior per candidate")
        if (any(not math.isfinite(prior) or prior < 0.0 for prior in prior_values)
                or (prior_values and not math.isclose(sum(prior_values), 1.0,
                                                      rel_tol=configuration.noise_tolerance,
                                                      abs_tol=configuration.noise_tolerance))):
            raise ValueError("policy priors must be a finite normalized distribution")
        candidates = []
        self._last_continuation_policies = {
            price.action.identity: price.continuation_policy for price in prices}
        for price, prior in zip(prices, prior_values):
            rejected_by_cache = (cached_identity is not None
                                 and price.action.identity != cached_identity)
            disposition = (CandidateDisposition.FORCED if forced else
                           CandidateDisposition.ENDS_TURN if price.ends_turn else
                           CandidateDisposition.CONTINUES_TURN)
            components = value_components(price.footprint.contributions)
            status = (EvaluationStatus.UNAVAILABLE if rejected_by_cache else price.status)
            delta = (None if status is EvaluationStatus.UNAVAILABLE else
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
                price.action, delta, disposition, status,
                (() if rejected_by_cache else successors),
                ((*price.gaps, "not selected by cached compound policy")
                 if rejected_by_cache else price.gaps), continuation,
                None if delta is None else SearchValue(
                    baseline.total + delta.total, baseline.scale),
                prior,
                (() if price.prize_map is None else price.prize_map.plan_rank_key()),
                price.prize_map))
        legal_actions = (actions if getattr(provider, "requires_observation_roster", False)
                         else tuple(price.action for price in prices))
        return SearchResult(
            baseline,
            CandidateRoster.from_legal_actions(
                legal_actions, tuple(candidates), forced=forced),
            nodes_visited=budget.nodes,
            stop_reason=("cached_continuation"
                         if cached_identity is not None else budget.stop_reason),
            frontier=tuple(budget.frontier),
        )


def preservation_frontier(candidates, noise_tolerance=0.0):
    deferred = set()
    for candidate in candidates:
        continuation = (getattr(candidate, "continuation", None)
                        or getattr(candidate, "footprint", None))
        consumed = set(() if continuation is None else
                       continuation.opportunities_consumed)
        for other in candidates:
            if other is candidate:
                continue
            if other.delta is None or candidate.delta is None:
                continue
            other_continuation = (getattr(other, "continuation", None)
                                  or getattr(other, "footprint", None))
            preserved = (() if other_continuation is None else
                         other_continuation.opportunities_preserved)
            allowances_consumed = getattr(
                continuation, "allowances_consumed", ())
            zones_replaced = getattr(continuation, "zones_replaced", ())
            opportunities_created = getattr(
                other_continuation, "opportunities_created", ())
            other_allowances_consumed = getattr(
                other_continuation, "allowances_consumed", ())
            refresh_after_preparation = (
                "supporter_played" in allowances_consumed
                and "hand" in zones_replaced
                and other.delta.total > noise_tolerance
                and bool(opportunities_created)
                and "play" in preserved
                and "supporter_played" not in other_allowances_consumed)
            if refresh_after_preparation:
                deferred.add(id(candidate))
                break
            prepare_before_retreat = (
                candidate.action.identity.kind == "retreat"
                and other.delta.total > noise_tolerance
                and bool(opportunities_created)
                and "retreat" in preserved)
            if prepare_before_retreat:
                deferred.add(id(candidate))
                break
            use_free_ability = (
                other.action.identity.kind == "ability"
                and other.delta.total > noise_tolerance
                and candidate.action.identity.kind == "play"
                and candidate.action.identity.kind in preserved)
            if use_free_ability:
                deferred.add(id(candidate))
                break
            if not consumed:
                continue
            use_expiring_ability = (
                other.action.identity.kind == "ability"
                and candidate.action.identity.kind == "evolve"
                and other.delta.total > noise_tolerance)
            if (not use_expiring_ability
                    and other.delta.total + noise_tolerance < candidate.delta.total):
                continue
            if (other.action.identity.kind in consumed
                    and candidate.action.identity.kind in preserved):
                deferred.add(id(candidate))
                break
    return tuple(candidate for candidate in candidates
                 if id(candidate) not in deferred) or tuple(candidates)


class GreedyDecisionPolicy:
    identity = f"ledger-spend-then-end-v1:{SEARCH_SEMANTICS_IDENTITY}"

    def choose(self, roster, configuration):
        if roster.forced and len(roster.candidates) == 1:
            return DecisionChoice(roster.candidates[0].action, DecisionReason.FORCED)
        candidates = tuple(candidate for candidate in roster.candidates
                           if candidate.delta is not None
                           and candidate.status.value in configuration.accepted_statuses)
        reason = DecisionReason.FORCED if roster.forced else DecisionReason.BEST_DELTA
        if not candidates:
            detail = tuple((str(candidate.action.identity), candidate.status.value, candidate.gaps)
                           for candidate in roster.candidates)
            raise ValueError(f"normal policy received no comparable candidates: {detail}")
        if not roster.forced:
            knockouts = tuple(candidate for candidate in candidates
                              if candidate.disposition is CandidateDisposition.ENDS_TURN
                              and any(component.key in {"prize.race", "result.win"}
                                      and component.activation > 0
                                      for component in candidate.delta.components))
            meaningful_continuation = any(
                candidate.disposition is CandidateDisposition.CONTINUES_TURN
                and candidate.delta.total > configuration.noise_tolerance
                for candidate in candidates)
            if knockouts and not meaningful_continuation:
                return DecisionChoice(
                    self._ranked(knockouts, configuration)[0].action,
                    DecisionReason.BEST_TURN_ENDER)
            continuing = tuple(
                candidate for candidate in candidates
                if candidate.disposition is CandidateDisposition.CONTINUES_TURN
                and candidate.delta is not None
                and candidate.delta.total > configuration.noise_tolerance)
            if continuing:
                candidates = preservation_frontier(
                    continuing, configuration.noise_tolerance)
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
        def value(candidate):
            return float("-inf") if candidate.delta is None else candidate.delta.total

        indexed = sorted(enumerate(candidates), key=lambda item: value(item[1]), reverse=True)
        ranked = []
        start = 0
        while start < len(indexed):
            best = value(indexed[start][1])
            stop = start + 1
            while (stop < len(indexed)
                   and (best == float("-inf")
                        or best - value(indexed[stop][1]) <= configuration.noise_tolerance)):
                stop += 1
            tied = tuple(indexed[start:stop])
            exact = all(value(candidate) == best for _index, candidate in tied)
            tied = tuple(sorted(tied, key=lambda item: (
                item[1].policy_tie_break if exact else (),
                hashlib.blake2b(
                    f"{configuration.tie_seed}:{item[0]}".encode("utf-8"),
                    digest_size=LOTTERY_DIGEST_BYTES).digest())))
            ranked.extend(candidate for _index, candidate in tied)
            start = stop
        return tuple(ranked)


class FailSafeDecisionPolicy:
    identity = f"ledger-fail-safe-v1:{SEARCH_SEMANTICS_IDENTITY}"

    _REASONS = {
        DecisionFailureStage.EVALUATION: DecisionReason.FAIL_SAFE_EVALUATION_FAILURE,
        DecisionFailureStage.PROVIDER: DecisionReason.FAIL_SAFE_PROVIDER_FAILURE,
        DecisionFailureStage.SEARCH: DecisionReason.FAIL_SAFE_SEARCH_FAILURE,
        DecisionFailureStage.POLICY: DecisionReason.FAIL_SAFE_POLICY_FAILURE,
        DecisionFailureStage.PRESENTATION: DecisionReason.FAIL_SAFE_PRESENTATION_FAILURE,
        DecisionFailureStage.RUNTIME: DecisionReason.FAIL_SAFE_RUNTIME_FAILURE,
    }

    def choose(self, roster, configuration, state, failure):
        payload = state.observation if isinstance(state, FailSafeRequest) else provider_payload(state)
        selection = tuple(safe_legal_selection(payload))
        candidate = next((item for item in roster.candidates
                          if selection in getattr(item.action, "equivalent_selections", ())), None)
        if candidate is None:
            candidate = neutral_lottery_choice(roster.candidates, configuration)
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
        baseline, CandidateRoster.from_legal_actions(actions, candidates, forced=forced),
        stop_reason=failure.stage.value,
        failure=failure)


__all__ = ("FailSafeDecisionPolicy", "GreedyDecisionPolicy", "LedgerOnePlySearch",
           "TransitionProviderSource", "UniformPolicyModel", "unavailable_ledger_result")
