from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path

from common.decision import (
    CandidateDisposition,
    CandidateRoster,
    ContinuationOpportunity,
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
    PolicyActionEvidence,
    PolicyDistribution,
    PolicyFallbackReason,
    PolicyRequest,
    PolicySourceIdentity,
    RealizedOutcome,
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
MIN_COMPARATIVE_RETREAT_ATTACHMENTS = 2
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

    def priors(self, request: PolicyRequest) -> PolicyDistribution:
        probability = 1.0 / len(request.roster.candidates)
        reason = PolicyFallbackReason.REQUESTED_UNIFORM
        actions = tuple(PolicyActionEvidence(
            identity,
            None if candidate.delta is None else candidate.delta.total,
            probability,
            probability,
            candidate.status,
            reason,
        ) for identity, candidate in zip(
            request.roster.policy_action_identities, request.roster.candidates))
        return PolicyDistribution(
            self.identity,
            self.identity,
            request.source,
            actions,
            None,
            1.0,
            probability,
            reason,
        )


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
        validate_source = getattr(policy_model, "validate_source", None)

        if validate_source is not None:
            value_scale = getattr(evaluator, "value_scale", None)
            if value_scale is None:
                raise ValueError("Ledger policy evaluator lacks a Value Scale")
            validate_source(PolicySourceIdentity(
                request.baseline_identity,
                evaluator.identity,
                request.evaluation_model.identity,
                value_scale.identity,
            ))

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
                self._portfolio_memo, request.execution_guard,
                request.baseline_identity)
            key = evaluation_key(observed)
            if key not in state_values:
                check_guard()
                if hasattr(evaluator, "evaluate_with_state"):
                    value, evaluation_state = evaluator.evaluate_with_state(
                        child_request, reusable_parent)
                    evaluation_states[key] = evaluation_state
                else:
                    value = evaluator.evaluate(child_request)
                if validate_source is not None:
                    validate_source(PolicySourceIdentity(
                        value.baseline_identity,
                        value.evaluator_identity,
                        value.evaluation_model_identity,
                        value.scale.identity,
                    ))
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
        policy_source = PolicySourceIdentity(
            request.baseline_identity,
            evaluator.identity,
            request.evaluation_model.identity,
            baseline.scale.identity,
        )
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
                gaps=("forced action not priced",))
            roster = CandidateRoster.from_legal_actions(
                actions, (candidate,), forced=True)
            roster = _apply_policy(
                board, roster, policy_source, policy_model)
            return SearchResult(
                baseline,
                roster,
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
        candidates = []
        self._last_continuation_policies = {
            price.action.identity: price.continuation_policy for price in prices}
        for price in prices:
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
                value_components(footprint.policy_contributions),
                footprint.realized_outcomes,
                footprint.executed_opportunity,
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
                None,
                (-sum(component.value for component in continuation.policy_components
                      if component.key == "action.evolution_target_commitment"),
                 *(() if price.prize_map is None else price.prize_map.plan_rank_key())),
                price.prize_map))
        legal_actions = (actions if getattr(provider, "requires_observation_roster", False)
                         else tuple(price.action for price in prices))
        priced_roster = CandidateRoster.from_legal_actions(
            legal_actions, tuple(candidates), forced=forced)
        if not priced_roster.candidates:
            return SearchResult(
                baseline,
                priced_roster,
                nodes_visited=budget.nodes,
                stop_reason=("cached_continuation"
                             if cached_identity is not None else budget.stop_reason),
                frontier=tuple(budget.frontier),
            )
        priced_roster = _apply_policy(
            board, priced_roster, policy_source, policy_model)
        return SearchResult(
            baseline,
            priced_roster,
            nodes_visited=budget.nodes,
            stop_reason=("cached_continuation"
                         if cached_identity is not None else budget.stop_reason),
            frontier=tuple(budget.frontier),
        )


def _apply_policy(board, roster, source, policy_model):
    distribution = policy_model.priors(PolicyRequest(board, roster, source))
    if not isinstance(distribution, PolicyDistribution):
        raise TypeError("policy model must return a Policy Distribution")
    priors = distribution.priors_for(roster)
    return roster.with_priors(priors)


def _opportunity_sources_match(left, right, kind):
    left = tuple(value for value in left if str(value) == kind)
    right = tuple(value for value in right if str(value) == kind)
    if not left:
        return False
    if not right:
        return any(getattr(value, "source", None) is None for value in left)
    left_sources = {getattr(value, "source", None) for value in left}
    right_sources = {getattr(value, "source", None) for value in right}
    if None in left_sources or None in right_sources:
        return True
    return bool(left_sources.intersection(right_sources))


def _attachment_target_value(continuation):
    components = getattr(
        continuation, "policy_components",
        getattr(continuation, "policy_contributions", ()))
    return sum(
        component.value for component in components
        if getattr(component, "key", getattr(component, "feature", None))
        == "action.attachment_target_fit")


def preservation_frontier(candidates, noise_tolerance=0.0):
    compare_attachment_targets = all(
        candidate.action.identity.kind == "attach" for candidate in candidates)

    def value(candidate):
        continuation = (getattr(candidate, "continuation", None)
                        or getattr(candidate, "footprint", None))
        return candidate.delta.total + (
            0.0 if continuation is None else
            getattr(continuation, "action_opportunity", 0.0)
            - (0.0 if compare_attachment_targets else
               _attachment_target_value(continuation)))

    def policy_features(candidate):
        continuation = (getattr(candidate, "continuation", None)
                        or getattr(candidate, "footprint", None))
        components = getattr(
            continuation, "policy_components",
            getattr(continuation, "policy_contributions", ()))
        return {getattr(component, "key", getattr(component, "feature", None))
                for component in components}

    def realized_source_value(candidate):
        continuation = (getattr(candidate, "continuation", None)
                        or getattr(candidate, "footprint", None))
        components = getattr(
            continuation, "policy_components",
            getattr(continuation, "policy_contributions", ()))
        return sum(
            max(0.0, component.value) for component in components
            if getattr(component, "provenance", ())[:1]
            == ("action.realized_portfolio",))

    def destructive_spend(candidate):
        continuation = (getattr(candidate, "continuation", None)
                        or getattr(candidate, "footprint", None))
        components = getattr(
            continuation, "policy_components",
            getattr(continuation, "policy_contributions", ()))
        return any(
            component.value < -noise_tolerance
            and getattr(component, "provenance", ())[:1] in {
                ("action.compound_discard_spend",), ("action.discard_spend",)}
            for component in components)

    def realized_recovery(candidate):
        continuation = (getattr(candidate, "continuation", None)
                        or getattr(candidate, "footprint", None))
        components = getattr(
            continuation, "policy_components",
            getattr(continuation, "policy_contributions", ()))
        return any(
            component.value > noise_tolerance
            and "action.recovery" in getattr(component, "provenance", ())
            for component in components)

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
            immediately_usable_outputs = getattr(
                other_continuation, "immediately_usable_outputs", ())
            other_allowances_consumed = getattr(
                other_continuation, "allowances_consumed", ())
            same_exclusive_spend = (
                consumed
                and consumed == set(getattr(
                    other_continuation, "opportunities_consumed", ()))
                and candidate.action.identity.kind == other.action.identity.kind
                and "action.survival_tool_target" in {
                    *policy_features(candidate), *policy_features(other)}
                and value(other) > value(candidate) + noise_tolerance)
            if same_exclusive_spend:
                deferred.add(id(candidate))
                break
            spare_scarce_attachment = (
                candidate.action.identity.kind == "attach"
                and other.action.identity.kind == "attach"
                and consumed == set(getattr(
                    other_continuation, "opportunities_consumed", ()))
                and getattr(continuation, "opportunities_created", ())
                == getattr(other_continuation, "opportunities_created", ())
                and getattr(continuation, "opportunities_preserved", ())
                == getattr(other_continuation, "opportunities_preserved", ())
                and realized_source_value(candidate)
                > realized_source_value(other) + noise_tolerance)
            if spare_scarce_attachment:
                deferred.add(id(candidate))
                break
            recover_before_destructive_search = (
                candidate.action.identity.kind == "play"
                and other.action.identity.kind == "play"
                and destructive_spend(candidate)
                and realized_recovery(other)
                and "play" in preserved)
            if recover_before_destructive_search:
                deferred.add(id(candidate))
                break
            refresh_after_preparation = (
                "supporter_played" in allowances_consumed
                and "hand" in zones_replaced
                and "hand" in getattr(
                    continuation, "immediately_usable_outputs", ())
                and (bool(opportunities_created)
                     or "in_play" in immediately_usable_outputs)
                and "play" in preserved
                and "supporter_played" not in other_allowances_consumed)
            if refresh_after_preparation:
                deferred.add(id(candidate))
                break
            deploy_before_transient_play = (
                candidate.action.identity.kind == "play"
                and "in_play" not in getattr(
                    continuation, "immediately_usable_outputs", ())
                and "in_play" in immediately_usable_outputs
                and "play" in preserved)
            if deploy_before_transient_play:
                deferred.add(id(candidate))
                break
            create_before_plain_play = (
                candidate.action.identity.kind == "play"
                and other.action.identity.kind == "play"
                and bool(opportunities_created)
                and not getattr(continuation, "opportunities_created", ())
                and "in_play" in immediately_usable_outputs
                and "play" in preserved)
            if create_before_plain_play:
                deferred.add(id(candidate))
                break
            dependency_refresh = (
                ContinuationOpportunity.DEPENDENCY_REACH in getattr(
                    continuation, "opportunities_created", ())
                and value(candidate) > value(other) + noise_tolerance)
            if dependency_refresh:
                continue
            prepare_before_retreat = (
                candidate.action.identity.kind == "retreat"
                and (((value(other) > noise_tolerance
                       or "attack" in opportunities_created)
                      and bool(opportunities_created))
                     or (other.action.identity.kind == "evolve"
                         and "ready_attacker" in immediately_usable_outputs))
                and "retreat" in preserved)
            if prepare_before_retreat:
                deferred.add(id(candidate))
                break
            live_attachment_before_optional_body = (
                candidate.action.identity.kind == "play"
                and "in_play" in getattr(
                    continuation, "immediately_usable_outputs", ())
                and other.action.identity.kind == "attach"
                and ("option.energy" in policy_features(other)
                     or "retreat" in opportunities_created)
                and "play" in preserved
                and "discard" not in getattr(
                    continuation, "immediately_usable_outputs", ())
                and "attach" in getattr(
                    continuation, "opportunities_preserved", ()))
            if live_attachment_before_optional_body:
                deferred.add(id(candidate))
                break
            compound_development_before_attachment = (
                candidate.action.identity.kind == "attach"
                and other.action.identity.kind == "play"
                and "discard" in immediately_usable_outputs
                and "in_play" in immediately_usable_outputs
                and "attach" in opportunities_created
                and "attach" in preserved)
            if compound_development_before_attachment:
                deferred.add(id(candidate))
                break
            if not consumed:
                continue
            live_attachment = (
                candidate.action.identity.kind == "attach"
                and ("retreat" in getattr(
                    continuation, "opportunities_created", ())
                     or "option.energy" in policy_features(candidate)))
            create_before_consume = (
                candidate.action.identity.kind in opportunities_created
                and candidate.action.identity.kind in preserved
                and _opportunity_sources_match(
                    consumed, opportunities_created,
                    candidate.action.identity.kind)
                and not live_attachment)
            if create_before_consume:
                deferred.add(id(candidate))
                break
            use_expiring_ability = (
                other.action.identity.kind == "ability"
                and candidate.action.identity.kind == "evolve"
                and other.delta.total > noise_tolerance
                and _opportunity_sources_match(
                    consumed,
                    getattr(other_continuation,
                            "opportunities_consumed", ()),
                    "ability"))
            if use_expiring_ability:
                deferred.add(id(candidate))
                break
            if other.delta.total + noise_tolerance < candidate.delta.total:
                continue
            other_kind = other.action.identity.kind
            consumed_inventory = Counter(
                (str(opportunity), getattr(opportunity, "source", None))
                for opportunity in consumed if str(opportunity) == other_kind)
            executed = getattr(other_continuation, "executed_opportunity", None)
            executed_key = (
                other_kind,
                (getattr(executed, "source", None)
                 if executed is not None and str(executed) == other_kind else None))
            at_risk = Counter({executed_key: consumed_inventory[executed_key]})
            created_inventory = Counter(
                (str(opportunity), getattr(opportunity, "source", None))
                for opportunity in getattr(
                    continuation, "opportunities_created", ())
                if str(opportunity) == other_kind)
            consumed_count = sum(at_risk.values())
            replacement_count = sum((created_inventory & at_risk).values())
            if (other_kind in consumed
                    and replacement_count < consumed_count
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
            def policy_value(candidate):
                continuation = candidate.continuation
                return candidate.delta.total + (
                    0.0 if continuation is None else
                    continuation.action_opportunity
                    - _attachment_target_value(continuation))

            enders = tuple(
                candidate for candidate in candidates
                if candidate.disposition is CandidateDisposition.ENDS_TURN)
            explicit_end = any(
                candidate.continuation is not None
                and RealizedOutcome.EXPLICIT_TURN_END in
                candidate.continuation.realized_outcomes
                for candidate in enders)
            only_explicit_end = bool(enders) and all(
                candidate.continuation is not None
                and RealizedOutcome.EXPLICIT_TURN_END in
                candidate.continuation.realized_outcomes
                for candidate in enders)
            best_ender_value = max((candidate.delta.total for candidate in enders),
                                   default=float("-inf"))
            ready_knockout_enders = tuple(
                candidate for candidate in enders
                if candidate.continuation is not None
                and {RealizedOutcome.OPPONENT_ACTIVE_KNOCKOUT,
                     RealizedOutcome.OPPONENT_BODY_KNOCKOUT}.intersection(
                         candidate.continuation.realized_outcomes))
            ready_winning_enders = tuple(
                candidate for candidate in ready_knockout_enders
                if candidate.continuation is not None
                and (RealizedOutcome.GAME_WIN in
                     candidate.continuation.realized_outcomes
                     or any(component.key in {"result.win", "active.terminal_liability"}
                            and component.value > 0
                            for component in candidate.delta.components)))
            continuation_threshold = (
                0.0 if explicit_end or ready_knockout_enders
                else min(0.0, best_ender_value))

            def meaningful(candidate):
                return (policy_value(candidate)
                        > continuation_threshold + configuration.noise_tolerance)

            def continuation_components(continuation):
                return getattr(
                    continuation, "policy_components",
                    getattr(continuation, "policy_contributions", ()))

            def eligible_attachment(candidate):
                if candidate.action.identity.kind != "attach":
                    return True
                components = continuation_components(candidate.continuation)
                if any(
                        component.provenance[:1] == ("action.realized_portfolio",)
                        and component.key.startswith("function.cost_reduction")
                        for component in components):
                    return False
                immediate = {"attack", "retreat"}.intersection(
                    candidate.continuation.opportunities_created)
                return (candidate.delta.total
                        > best_ender_value + configuration.noise_tolerance
                        or candidate.delta.total > configuration.noise_tolerance
                        or bool(immediate))

            def repays_action_cost(candidate):
                continuation = candidate.continuation
                components = continuation_components(continuation)
                cost = -sum(component.value for component in components
                            if getattr(component, "key", getattr(
                                component, "feature", None)) == "action.opportunity_cost")
                return continuation.action_opportunity > cost + configuration.noise_tolerance

            def worth_before_knockout(candidate):
                if not meaningful(candidate):
                    return False
                continuation = candidate.continuation
                refresh = ("supporter_played" in continuation.allowances_consumed
                           and "hand" in continuation.zones_replaced)
                transient_play = (
                    candidate.action.identity.kind == "play"
                    and "in_play" not in continuation.immediately_usable_outputs)
                if not refresh and not transient_play:
                    return True
                knockout_value = max(
                    ready.delta.total for ready in ready_knockout_enders)
                return policy_value(candidate) > knockout_value + configuration.noise_tolerance

            continuing = tuple(
                candidate for candidate in candidates
                if candidate.disposition is CandidateDisposition.CONTINUES_TURN
                and candidate.delta is not None
                and meaningful(candidate)
                and eligible_attachment(candidate))
            ability_would_be_consumed = any(
                candidate.disposition is CandidateDisposition.CONTINUES_TURN
                and candidate.continuation is not None
                and "ability" in candidate.continuation.opportunities_consumed
                for candidate in candidates)
            recycling_draws = tuple(
                candidate for candidate in candidates
                if candidate.disposition is CandidateDisposition.CONTINUES_TURN
                and candidate.action.identity.kind == "ability"
                and candidate.continuation is not None
                and not candidate.continuation.allowances_consumed
                and "attach" not in candidate.continuation.opportunities_consumed
                and {"deck", "hand"}.issubset(
                    candidate.continuation.zones_replaced)
                and ("in_play" in candidate.continuation.zones_replaced
                     or ability_would_be_consumed)
                and "hand" in candidate.continuation.immediately_usable_outputs
                and {"end", "play"}.issubset(
                    candidate.continuation.opportunities_preserved))
            continuing_ids = {id(candidate) for candidate in continuing}
            continuing = (*continuing, *(candidate for candidate in recycling_draws
                                          if id(candidate) not in continuing_ids))
            durable_development = tuple(
                candidate for candidate in candidates
                if candidate.disposition is CandidateDisposition.CONTINUES_TURN
                and candidate.continuation is not None
                and repays_action_cost(candidate)
                and "in_play" in candidate.continuation.immediately_usable_outputs
                and ((candidate.action.identity.kind == "play")
                     or (candidate.action.identity.kind == "evolve"
                         and "ready_attacker" in
                         candidate.continuation.immediately_usable_outputs))
                and {"end", "play"}.issubset(
                    candidate.continuation.opportunities_preserved))
            continuing_ids = {id(candidate) for candidate in continuing}
            continuing = (*continuing, *(candidate for candidate in durable_development
                                          if id(candidate) not in continuing_ids))
            lethal_preparation = tuple(
                candidate for candidate in candidates
                if candidate.disposition is CandidateDisposition.CONTINUES_TURN
                and candidate.continuation is not None
                and ContinuationOpportunity.LETHAL_ATTACK in
                candidate.continuation.opportunities_created
                and "attack" in {
                    *candidate.continuation.opportunities_created,
                    *candidate.continuation.opportunities_preserved})
            continuing_ids = {id(candidate) for candidate in continuing}
            continuing = (*continuing, *(candidate for candidate in lethal_preparation
                                          if id(candidate) not in continuing_ids))
            attack_preparation = tuple(
                candidate for candidate in candidates
                if candidate.disposition is CandidateDisposition.CONTINUES_TURN
                and candidate.continuation is not None
                and "attack" in candidate.continuation.opportunities_created
                and "retreat" in {
                    *candidate.continuation.opportunities_created,
                    *candidate.continuation.opportunities_preserved})
            continuing_ids = {id(candidate) for candidate in continuing}
            continuing = (*continuing, *(candidate for candidate in attack_preparation
                                          if id(candidate) not in continuing_ids))
            realized_attachments = tuple(
                candidate for candidate in candidates
                if candidate.disposition is CandidateDisposition.CONTINUES_TURN
                and candidate.continuation is not None
                and candidate.action.identity.kind == "attach"
                and ({"end", "play"}.issubset(
                    candidate.continuation.opportunities_preserved)
                     or only_explicit_end)
                and any(
                    component.value > configuration.noise_tolerance
                    and component.key == "option.energy"
                    and component.provenance[:1] == ("action.realized_portfolio",)
                    for component in continuation_components(candidate.continuation)))
            continuing_ids = {id(candidate) for candidate in continuing}
            continuing = (*continuing, *(candidate for candidate in realized_attachments
                                          if id(candidate) not in continuing_ids))
            def has_policy_provenance(candidate, marker, *, negative=False):
                continuation = candidate.continuation
                return continuation is not None and any(
                    (component.value < -configuration.noise_tolerance
                     if negative else component.value > configuration.noise_tolerance)
                    and marker in component.provenance
                    for component in continuation_components(continuation))

            destructive_play_available = any(
                candidate.action.identity.kind == "play"
                and (has_policy_provenance(
                    candidate, "action.compound_discard_spend", negative=True)
                     or has_policy_provenance(
                         candidate, "action.discard_spend", negative=True))
                for candidate in candidates)
            realized_plays = tuple(
                candidate for candidate in candidates
                if candidate.disposition is CandidateDisposition.CONTINUES_TURN
                and candidate.continuation is not None
                and candidate.action.identity.kind == "play"
                and (policy_value(candidate) > (
                        min(0.0, best_ender_value) + configuration.noise_tolerance)
                     or (destructive_play_available
                         and has_policy_provenance(
                             candidate, "action.recovery")))
                and "in_play" not in
                    candidate.continuation.immediately_usable_outputs
                and {"end", "play"}.issubset(
                    candidate.continuation.opportunities_preserved)
                and any(
                    component.value > configuration.noise_tolerance
                    and component.provenance[:1]
                    == ("action.realized_portfolio",)
                    for component in continuation_components(candidate.continuation)))
            continuing_ids = {id(candidate) for candidate in continuing}
            continuing = (*continuing, *(candidate for candidate in realized_plays
                                          if id(candidate) not in continuing_ids))
            retreat_attachments = tuple(
                candidate for candidate in candidates
                if candidate.disposition is CandidateDisposition.CONTINUES_TURN
                and candidate.continuation is not None
                and candidate.action.identity.kind == "attach"
                and "retreat" in candidate.continuation.opportunities_created
                and {"end", "play"}.issubset(
                    candidate.continuation.opportunities_preserved))
            retreat_attachments = tuple(
                candidate for candidate in retreat_attachments
                if not any(
                    component.provenance[:1] == ("action.realized_portfolio",)
                    and component.key.startswith("function.cost_reduction")
                    for component in continuation_components(candidate.continuation)))
            if (len(retreat_attachments) < MIN_COMPARATIVE_RETREAT_ATTACHMENTS
                    or not any(any(
                        component.key == "option.energy"
                        and component.value > configuration.noise_tolerance
                        and component.provenance[:1]
                        == ("action.realized_portfolio",)
                        for component in continuation_components(candidate.continuation))
                        for candidate in retreat_attachments)):
                retreat_attachments = ()
            accelerating_attachments = tuple(
                candidate for candidate in candidates
                if candidate.disposition is CandidateDisposition.CONTINUES_TURN
                and candidate.continuation is not None
                and candidate.action.identity.kind == "attach"
                and candidate.delta is not None
                and candidate.delta.total > configuration.noise_tolerance
                and {"attack", "retreat"}.intersection(
                    candidate.continuation.opportunities_created))
            continuing_ids = {id(candidate) for candidate in continuing}
            continuing = (*continuing, *(candidate for candidate in retreat_attachments
                                          if id(candidate) not in continuing_ids))
            if accelerating_attachments:
                continuing = tuple(
                    candidate for candidate in continuing
                    if candidate.action.identity.kind != "attach"
                    or candidate in accelerating_attachments)
            winning_preparation = tuple(
                candidate for candidate in candidates
                if candidate.disposition is CandidateDisposition.CONTINUES_TURN
                and candidate.continuation is not None
                and ContinuationOpportunity.WINNING_ATTACK in
                candidate.continuation.opportunities_created
                and "attack" in {
                    *candidate.continuation.opportunities_created,
                    *candidate.continuation.opportunities_preserved})
            positive_refresh = tuple(
                candidate for candidate in candidates
                if candidate.disposition is CandidateDisposition.CONTINUES_TURN
                and candidate.continuation is not None
                and policy_value(candidate) > configuration.noise_tolerance
                and "supporter_played" in candidate.continuation.allowances_consumed
                and "hand" in candidate.continuation.zones_replaced
                and "hand" in candidate.continuation.immediately_usable_outputs)
            continuing_ids = {id(candidate) for candidate in continuing}
            continuing = (*continuing, *(candidate for candidate in positive_refresh
                                          if id(candidate) not in continuing_ids))
            refresh_available = any(
                candidate.continuation is not None
                and "supporter_played" in candidate.continuation.allowances_consumed
                and "hand" in candidate.continuation.zones_replaced
                for candidate in continuing)
            if refresh_available:
                durable_preparation = tuple(
                    candidate for candidate in candidates
                    if candidate.disposition is CandidateDisposition.CONTINUES_TURN
                    and candidate.continuation is not None
                and "in_play" in candidate.continuation.immediately_usable_outputs
                and (candidate.continuation.opportunities_created
                     or candidate.action.identity.kind == "evolve"
                     or meaningful(candidate))
                    and "play" in candidate.continuation.opportunities_preserved
                    and candidate not in continuing)
                continuing = (*continuing, *durable_preparation)
            if ready_winning_enders:
                continuing = ()
            elif winning_preparation:
                continuing = winning_preparation
            elif ready_knockout_enders:
                continuing = tuple(
                    candidate for candidate in continuing
                    if ((candidate.action.identity.kind != "attach"
                         or not accelerating_attachments
                         or candidate in accelerating_attachments)
                        and (worth_before_knockout(candidate)
                             or candidate in lethal_preparation)))
            elif retreat_attachments:
                continuing = retreat_attachments
            if continuing:
                candidates = preservation_frontier(
                    continuing, configuration.noise_tolerance)
                reason = DecisionReason.POSITIVE_CONTINUATION
            else:
                if enders:
                    if ready_winning_enders:
                        candidates = ready_winning_enders
                    elif ready_knockout_enders:
                        active_knockouts = tuple(
                            candidate for candidate in ready_knockout_enders
                            if RealizedOutcome.OPPONENT_ACTIVE_KNOCKOUT in
                            candidate.continuation.realized_outcomes)
                        candidates = tuple(
                            candidate for candidate in enders
                            if candidate.continuation is not None
                            and RealizedOutcome.ACTION_ENDED_TURN in
                            candidate.continuation.realized_outcomes
                            and (not active_knockouts
                                 or candidate in active_knockouts
                                 or not candidate.delta.components))
                    else:
                        candidates = enders
                    reason = DecisionReason.BEST_TURN_ENDER
        return DecisionChoice(self._ranked(
            candidates, configuration,
            include_action_opportunity=(
                roster.forced or reason is DecisionReason.POSITIVE_CONTINUATION),
            include_dependency_opportunity=(
                reason is DecisionReason.POSITIVE_CONTINUATION))[
                    0].action,
            reason)

    @staticmethod
    def _ranked(candidates, configuration, *, include_action_opportunity=False,
                include_dependency_opportunity=False):
        compare_attachment_targets = all(
            candidate.action.identity.kind == "attach" for candidate in candidates)
        dependency_roster = (
            include_dependency_opportunity
            and any(candidate.continuation is not None
                    and ContinuationOpportunity.DEPENDENCY_REACH in
                    candidate.continuation.opportunities_created
                    for candidate in candidates))

        def value(candidate):
            if candidate.delta is None:
                return float("-inf")
            include = include_action_opportunity or dependency_roster
            opportunity = (
                candidate.continuation.action_opportunity
                - (0.0 if compare_attachment_targets else
                   _attachment_target_value(candidate.continuation))
                if include and candidate.continuation is not None else 0.0)
            return candidate.delta.total + opportunity

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
                    f"{configuration.tie_seed}:{item[1].action.identity}".encode("utf-8"),
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
