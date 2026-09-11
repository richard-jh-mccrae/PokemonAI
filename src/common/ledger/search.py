from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from common.decision import (
    ActionChoiceIdentity,
    BudgetController,
    CollaboratorKind,
    ComponentContract,
    ContinuationOpportunity,
    DecisionDeadlineExceeded,
    DecisionFailure,
    DecisionFailureStage,
    DecisionPolicyRequest,
    DecisionRequirements,
    EvidenceIdentity,
    EvaluationRequest,
    IdentifiedConfiguration,
    FailSafePolicyRequest,
    PolicyActionEvidence,
    PolicyDistribution,
    PolicyFallbackReason,
    PolicyModelRequest,
    PolicySourceIdentity,
    RealizedOutcome,
    SearchCoverage,
    SearchOutcome,
    SearchOutcomeStatus,
    SearchResult,
    SearchProvider,
    SearchTermination,
    StatisticCoverage,
    StateValuation,
    validate_state_valuation,
    neutral_lottery_choice,
    safe_legal_selection,
)
from common.decision.components import PolicyModel, ValueEvaluator
from common.decision.configuration import SearchConfiguration
from common.decision.results import CandidateDisposition, CandidateResult, CandidateRoster
from common.decision.statistics import DECISION_DELTA, DecisionDeltaStatistic
from common.decision.values import ContinuationResult, DecisionDelta, EvaluationStatus
from common.options import LegalAction
from common.observation.provider import provider_payload
from common.observation.provider import ProviderState
from common.strategy.context import _MAIN

from .decision import (evaluator_semantics_identity, ledger_valuation_from_state,
                       value_components)
from .evidence import (
    LedgerCandidateEvidence, LedgerDecisionReason, LedgerEvidence,
    LedgerPolicyDecisionEvidence,
)
from .evaluate import EvaluationSnapshot
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
    card_ids = re.findall(r'"id":(\d+)', "".join(map(str, identity.parts)))
    return f"card:{card_ids[-1]}" if len(set(card_ids)) == 1 else None


class DecisionExecutionError(RuntimeError):
    def __init__(self, failure: DecisionFailure):
        super().__init__(failure.message)
        self.failure = failure


@dataclass
class TransitionProviderSource:
    factory: Callable[..., object]
    state: ProviderState
    kwargs: dict[str, object]
    identity: str = "transition-provider-source-v1"
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
    contract = ComponentContract(identity, identity)

    def priors(self, request: PolicyModelRequest) -> PolicyDistribution:
        probability = 1.0 / len(request.roster.actions)
        reason = PolicyFallbackReason.REQUESTED_UNIFORM
        actions = tuple(PolicyActionEvidence(
            identity,
            None if candidate.delta is None else candidate.delta.total,
            probability,
            probability,
            candidate.delta_status,
            reason,
        ) for identity, candidate in zip(
            request.roster.identities, request.candidates))
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
    required_collaborators = (
        CollaboratorKind.POLICY_MODEL,
        CollaboratorKind.PROVIDER,
    )
    optional_collaborators: tuple[CollaboratorKind, ...] = ()
    contract = ComponentContract(
        identity,
        "SearchConfiguration",
        produced_statistics=frozenset((DECISION_DELTA,)),
        required_collaborators=frozenset(required_collaborators),
    )

    def __init__(self) -> None:
        self._previous_evaluation_state: EvaluationSnapshot | None = None
        self._previous_evaluator_identity: str | None = None
        self._active_continuation_policy: dict[tuple[object, ...], object] = {}
        self._last_continuation_policies: dict[
            object, tuple[tuple[tuple[object, ...], object], ...]] = {}
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

    def search(
            self,
            request: EvaluationRequest,
            evaluator: ValueEvaluator,
            configuration: IdentifiedConfiguration | str,
            *,
            policy_model: PolicyModel,
            provider: SearchProvider,
    ) -> SearchResult:
        if not isinstance(configuration, SearchConfiguration):
            raise TypeError("Ledger search requires SearchConfiguration")
        if not isinstance(provider, TransitionProviderSource):
            raise TypeError("Ledger search requires TransitionProviderSource")
        board = request.state
        root = (provider.state if isinstance(provider, TransitionProviderSource)
                else request.state)
        state_values = {}
        evaluation_states: dict[tuple[object, ...], object] = {}
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
                state=observed,
                evaluation_model=request.evaluation_model,
                root_perspective=request.root_perspective,
                parent_valuation=parent,
                observation_delta=delta,
                reuse=self._portfolio_memo,
                execution_guard=request.execution_guard,
                baseline_identity=request.baseline_identity,
            )
            key = evaluation_key(observed)
            if key not in state_values:
                check_guard()
                if hasattr(evaluator, "evaluate_with_state"):
                    value, evaluation_state = evaluator.evaluate_with_state(
                        child_request, reusable_parent)
                    evaluation_states[key] = evaluation_state
                else:
                    value = evaluator.evaluate(child_request)
                validate_state_valuation(child_request, observed, evaluator, value)
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
        if baseline.evaluation_model_identity is None:
            raise ValueError(
                f"Ledger baseline lost model identity {request.evaluation_model.identity!r}")
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
            roster = CandidateRoster(actions, board.decision_key, forced=True)
            forced_candidates = (CandidateResult(
                roster.identities[0], CandidateDisposition.FORCED,
                delta_gaps=("forced action not priced",)),)
            distribution = _apply_policy(
                board, roster, forced_candidates, policy_source, policy_model)
            forced_evidence = (LedgerCandidateEvidence(roster.identities[0]),)
            return _ledger_result(
                baseline, roster, forced_candidates, budget.nodes, budget.stop_reason,
                tuple(budget.frontier), distribution, forced_evidence)
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
        candidates: list[CandidateResult] = []
        evidence_candidates: list[LedgerCandidateEvidence] = []
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
                     DecisionDelta(
                         price.swing, baseline.scale, components,
                         perspective=baseline.perspective))
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
            choice = ActionChoiceIdentity.from_action(price.action)
            candidates.append(CandidateResult(
                choice=choice,
                disposition=disposition,
                delta=delta,
                delta_status=status,
                delta_gaps=(
                    (*price.gaps, "not selected by cached compound policy")
                    if rejected_by_cache else price.gaps),
                successors=(() if rejected_by_cache else successors),
                continuation=(None if status is EvaluationStatus.UNAVAILABLE
                              else continuation),
                continuation_status=status,
                continuation_gaps=(price.gaps if status is not EvaluationStatus.UNAVAILABLE
                                   else ()),
            ))
            evidence_candidates.append(LedgerCandidateEvidence(
                choice,
                (-sum(component.value for component in continuation.policy_components
                      if component.key == "action.evolution_target_commitment"),
                 *(() if price.prize_map is None else price.prize_map.plan_rank_key())),
                price.prize_map))
        legal_actions = (actions if getattr(provider, "requires_observation_roster", False)
                         else tuple(price.action for price in prices))
        priced_roster = CandidateRoster(
            legal_actions, board.decision_key, forced=forced)
        stop_reason = ("cached_continuation"
                       if cached_identity is not None else budget.stop_reason)
        if not priced_roster.actions:
            return _ledger_result(
                baseline, priced_roster, tuple(candidates), budget.nodes,
                stop_reason, tuple(budget.frontier), None,
                tuple(evidence_candidates))
        distribution = _apply_policy(
            board, priced_roster, tuple(candidates), policy_source, policy_model)
        return _ledger_result(
            baseline, priced_roster, tuple(candidates), budget.nodes,
            stop_reason, tuple(budget.frontier), distribution,
            tuple(evidence_candidates))


def _apply_policy(board, roster, candidates, source, policy_model):
    statistics = tuple(DecisionDeltaStatistic(
        candidate.choice, candidate.delta, candidate.delta_status)
        for candidate in candidates)
    required = tuple(policy_model.contract.required_statistics)
    request = PolicyModelRequest(
        board, roster, candidates, statistics, source,
        DecisionRequirements(required))
    distribution = policy_model.priors(request)
    if not isinstance(distribution, PolicyDistribution):
        raise TypeError("policy model must return a Policy Distribution")
    expected = roster.identities
    actual = tuple(item.choice for item in distribution.actions)
    if actual != expected:
        raise ValueError("policy distribution does not match priced candidates")
    return distribution


def _ledger_evidence(nodes_visited, frontier, candidates, distribution):
    return LedgerEvidence(
        1,
        nodes_visited,
        tuple(str(item) for item in frontier),
        distribution,
        tuple(candidates),
    )


def _ledger_result(
        baseline, roster, candidates, nodes_visited, stop_reason, frontier,
        distribution, evidence_candidates, failure=None):
    statistics = tuple(DecisionDeltaStatistic(
        candidate.choice, candidate.delta, candidate.delta_status)
        for candidate in candidates)
    covered = frozenset(
        candidate.choice for candidate in candidates if candidate.delta is not None)
    if failure is not None:
        status = SearchOutcomeStatus.HARD_FAILURE
    elif stop_reason in {"node_budget", "time_budget"}:
        status = (SearchOutcomeStatus.BUDGET_LIMITED if covered else
                  SearchOutcomeStatus.INSUFFICIENT_INITIALIZATION)
    elif not covered and not (roster.forced and len(roster.actions) == 1):
        status = SearchOutcomeStatus.INSUFFICIENT_INITIALIZATION
    else:
        status = SearchOutcomeStatus.COMPLETE
    return SearchResult(
        baseline,
        roster,
        candidates,
        SearchOutcome(
            status,
            SearchCoverage((StatisticCoverage(
                DECISION_DELTA, covered),)),
            SearchTermination("ledger", stop_reason or status.value, 1),
            failure,
        ),
        statistics,
        _ledger_evidence(
            nodes_visited, frontier, evidence_candidates, distribution),
    )


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


@dataclass(frozen=True, slots=True)
class _LedgerPolicyCandidate:
    action: LegalAction
    delta: DecisionDelta | None
    disposition: CandidateDisposition
    status: EvaluationStatus
    gaps: tuple[str, ...]
    continuation: ContinuationResult | None
    policy_tie_break: tuple[int | float | str, ...]


@dataclass(frozen=True, slots=True)
class _LedgerPolicyRoster:
    candidates: tuple[_LedgerPolicyCandidate, ...]
    forced: bool


class GreedyDecisionPolicy:
    identity = f"ledger-spend-then-end-v1:{SEARCH_SEMANTICS_IDENTITY}"
    required_statistics = (DECISION_DELTA,)
    contract = ComponentContract(
        identity, "PolicyConfiguration",
        required_statistics=frozenset(required_statistics))

    def choose(self, request: DecisionPolicyRequest):
        return self.choose_with_evidence(request).choice

    def choose_with_evidence(self, request: DecisionPolicyRequest):
        evidence = request.evidence
        if not isinstance(evidence, LedgerEvidence):
            raise TypeError("Ledger policy requires Ledger evidence")
        evidence_by_choice = {item.choice: item for item in evidence.candidates}
        if set(evidence_by_choice) != set(request.roster.identities):
            raise ValueError("Ledger evidence does not match Candidate Roster")
        roster = _LedgerPolicyRoster(
            tuple(_LedgerPolicyCandidate(
                action,
                candidate.delta,
                candidate.disposition,
                candidate.delta_status,
                candidate.delta_gaps,
                candidate.continuation,
                evidence_by_choice[candidate.choice].policy_tie_break,
            ) for action, candidate in zip(
                request.roster.actions, request.candidates)),
            request.roster.forced,
        )
        configuration = request.configuration
        if roster.forced and len(roster.candidates) == 1:
            return LedgerPolicyDecisionEvidence(
                1,
                ActionChoiceIdentity.from_action(roster.candidates[0].action),
                LedgerDecisionReason.FORCED.value,
            )
        candidates = tuple(candidate for candidate in roster.candidates
                           if candidate.delta is not None
                           and candidate.status.value in configuration.accepted_statuses)
        reason = (LedgerDecisionReason.FORCED if roster.forced
                  else LedgerDecisionReason.BEST_DELTA)
        if not candidates:
            detail = tuple((str(candidate.action.identity), candidate.status.value, candidate.gaps)
                           for candidate in roster.candidates)
            raise ValueError(f"normal policy received no comparable candidates: {detail}")

        def required_delta(candidate: _LedgerPolicyCandidate) -> DecisionDelta:
            if candidate.delta is None:
                raise ValueError("comparable Ledger candidate lacks a Decision Delta")
            return candidate.delta

        def required_continuation(candidate: _LedgerPolicyCandidate) -> ContinuationResult:
            if candidate.continuation is None:
                raise ValueError("Ledger candidate lacks continuation evidence")
            return candidate.continuation

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
            best_ender_value = max((required_delta(candidate).total for candidate in enders),
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
                            for component in required_delta(candidate).components)))
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
                    required_delta(ready).total for ready in ready_knockout_enders)
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
                reason = LedgerDecisionReason.POSITIVE_CONTINUATION
            else:
                if enders:
                    if ready_winning_enders:
                        candidates = ready_winning_enders
                    elif ready_knockout_enders:
                        active_knockouts = tuple(
                            candidate for candidate in ready_knockout_enders
                            if RealizedOutcome.OPPONENT_ACTIVE_KNOCKOUT in
                            required_continuation(candidate).realized_outcomes)
                        candidates = tuple(
                            candidate for candidate in enders
                            if candidate.continuation is not None
                            and RealizedOutcome.ACTION_ENDED_TURN in
                            candidate.continuation.realized_outcomes
                            and (not active_knockouts
                                 or candidate in active_knockouts
                                 or not required_delta(candidate).components))
                    else:
                        candidates = enders
                    reason = LedgerDecisionReason.BEST_TURN_ENDER
        chosen = self._ranked(
            candidates, configuration,
            include_action_opportunity=(
                roster.forced or reason is LedgerDecisionReason.POSITIVE_CONTINUATION),
            include_dependency_opportunity=(
                reason is LedgerDecisionReason.POSITIVE_CONTINUATION))[
                    0].action
        return LedgerPolicyDecisionEvidence(
            1, ActionChoiceIdentity.from_action(chosen), reason.value)

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
        ranked: list = []
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
    contract = ComponentContract(
        identity,
        "PolicyConfiguration",
        accepted_outcomes=frozenset((SearchOutcomeStatus.HARD_FAILURE,)),
        accepted_evidence=frozenset((EvidenceIdentity("ledger", 1),)),
    )

    _REASONS = {
        DecisionFailureStage.EVALUATION: LedgerDecisionReason.FAIL_SAFE_EVALUATION_FAILURE,
        DecisionFailureStage.PROVIDER: LedgerDecisionReason.FAIL_SAFE_PROVIDER_FAILURE,
        DecisionFailureStage.SEARCH: LedgerDecisionReason.FAIL_SAFE_SEARCH_FAILURE,
        DecisionFailureStage.POLICY: LedgerDecisionReason.FAIL_SAFE_POLICY_FAILURE,
        DecisionFailureStage.PRESENTATION: LedgerDecisionReason.FAIL_SAFE_PRESENTATION_FAILURE,
        DecisionFailureStage.RUNTIME: LedgerDecisionReason.FAIL_SAFE_RUNTIME_FAILURE,
    }

    def choose(self, request: FailSafePolicyRequest):
        return self.choose_with_evidence(request).choice

    def choose_with_evidence(self, request: FailSafePolicyRequest):
        state = request.observation
        failure = request.failure
        payload = (None if request.context is None
                   else provider_payload(request.context))
        selection = (() if payload is None
                     else tuple(safe_legal_selection(payload)))
        action = next((item for item in request.roster.actions
                       if selection in getattr(item, "equivalent_selections", ())), None)
        if action is None:
            choice = neutral_lottery_choice(
                request.roster.identities, request.configuration)
            return LedgerPolicyDecisionEvidence(
                1, choice, self._REASONS[failure.stage].value)
        return LedgerPolicyDecisionEvidence(
            1, ActionChoiceIdentity.from_action(action),
            self._REASONS[failure.stage].value)


def unavailable_ledger_result(request, failure):
    from .decision import LEDGER_VALUE_SCALE, LedgerValueEvaluator

    root = request.state
    board = getattr(root, "observation", root)
    baseline = StateValuation(
        board.position_key,
        0.0, LEDGER_VALUE_SCALE, board.seat,
        LedgerValueEvaluator.identity, status=EvaluationStatus.UNAVAILABLE,
        gaps=(f"{failure.stage.value}:{failure.error_type}",),
        evaluation_model_identity=request.evaluation_model.identity,
    )
    actions = tuple(root.legal_actions)
    forced = len(actions) == 1
    roster = CandidateRoster(actions, board.decision_key, forced=forced)
    candidates = tuple(CandidateResult(
        choice,
        CandidateDisposition.FORCED if forced else
        CandidateDisposition.ENDS_TURN if action.identity.kind == "end" else
        CandidateDisposition.CONTINUES_TURN,
        delta_gaps=baseline.gaps,
    ) for action, choice in zip(actions, roster.identities))
    evidence_candidates = tuple(LedgerCandidateEvidence(choice)
                                for choice in roster.identities)
    return _ledger_result(
        baseline, roster, candidates, 0, failure.stage.value, (), None,
        evidence_candidates, failure)


__all__ = ("FailSafeDecisionPolicy", "GreedyDecisionPolicy", "LedgerOnePlySearch",
           "TransitionProviderSource", "UniformPolicyModel", "unavailable_ledger_result")
