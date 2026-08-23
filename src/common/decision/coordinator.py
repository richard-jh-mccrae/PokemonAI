from __future__ import annotations

from dataclasses import dataclass, replace

from .contracts import (DecisionFailure, DecisionFailureStage, DecisionReason, DecisionResult,
                        EvaluationRequest, SearchTrace)


@dataclass(frozen=True, slots=True)
class DecisionCoordinator:
    evaluator: object
    evaluation_model: object
    search: object
    search_configuration: object
    policy_model: object
    decision_policy: object
    policy_configuration: object
    behavior_identity: object | None = None
    fail_safe_policy: object | None = None
    failure_handler: object | None = None

    def decide(self, state, *, provider=None, parent_valuation=None,
               observation_delta=None, strict=False, failure=None) -> DecisionResult:
        request = EvaluationRequest(
            state, self.evaluation_model, parent_valuation, observation_delta)
        if failure is not None:
            if self.failure_handler is None:
                raise ValueError("decision failure requires a failure handler")
            result = self.failure_handler(request, failure)
        else:
            try:
                result = self.search.search(
                    request, self.evaluator, self.policy_model, provider,
                    self.search_configuration)
            except Exception as exc:
                if strict or self.failure_handler is None:
                    raise
                failure = getattr(exc, "failure", None) or DecisionFailure.capture(
                    DecisionFailureStage.SEARCH, exc)
                result = self.failure_handler(request, failure)
        if not result.roster.candidates:
            return DecisionResult(None, result.baseline, result.roster, result,
                                  self._trace(result, None), DecisionReason.EMPTY_ROSTER,
                                  self.behavior_identity)
        use_fail_safe = result.failure is not None
        if use_fail_safe and self.fail_safe_policy is None:
            raise ValueError("failed search result requires a fail-safe policy")
        try:
            if use_fail_safe:
                choice = self.fail_safe_policy.choose(
                    result.roster, self.policy_configuration, state, result.failure)
            else:
                choice = self.decision_policy.choose(result.roster, self.policy_configuration)
        except Exception as exc:
            if strict or self.fail_safe_policy is None:
                raise
            failure = DecisionFailure.capture(DecisionFailureStage.POLICY, exc)
            result = replace(result, failure=failure, stop_reason=failure.stage.value)
            choice = self.fail_safe_policy.choose(
                result.roster, self.policy_configuration, state, failure)
        chosen = getattr(choice, "action", choice)
        reason = getattr(choice, "reason", DecisionReason.POLICY)
        return DecisionResult(chosen, result.baseline, result.roster, result,
                              self._trace(result, chosen), reason, self.behavior_identity)

    @staticmethod
    def _trace(result, chosen):
        candidate = next((item for item in result.roster.candidates
                          if item.action is chosen), None)
        paths = (() if candidate is None else
                 tuple(successor.action_path for successor in candidate.successors))
        return SearchTrace(
            result.nodes_visited, result.stop_reason, result.frontier, chosen, paths)


__all__ = ("DecisionCoordinator",)
