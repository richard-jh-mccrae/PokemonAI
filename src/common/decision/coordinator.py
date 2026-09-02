from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace

from .contracts import (CandidateRoster, DecisionChoice, DecisionFailure,
                        DecisionFailureStage, DecisionReason, DecisionResult,
                        EvaluationRequest, SearchTrace)
from .configuration import DecisionDeadlineExceeded


LOTTERY_DIGEST_BYTES = 8


def neutral_lottery_choice(candidates, configuration):
    indexed = tuple(enumerate(candidates))
    if not indexed:
        raise ValueError("neutral lottery requires a candidate")
    seed = int(getattr(configuration, "tie_seed", 0))
    return min(indexed, key=lambda item: hashlib.blake2b(
        f"{seed}:{item[0]}".encode("utf-8"),
        digest_size=LOTTERY_DIGEST_BYTES).digest())[1]


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
    ledger_baseline_identity: str | None = None

    def decide(self, state, *, provider=None, parent_valuation=None,
               observation_delta=None, execution_guard=None,
               strict=False, failure=None) -> DecisionResult:
        request = EvaluationRequest(
            state, self.evaluation_model, parent_valuation, observation_delta,
            execution_guard=execution_guard,
            baseline_identity=self.ledger_baseline_identity)
        if failure is not None:
            if self.failure_handler is None:
                raise ValueError("decision failure requires a failure handler")
            result = self.failure_handler(request, failure)
        else:
            try:
                result = self.search.search(
                    request, self.evaluator, self.policy_model, provider,
                    self.search_configuration)
            except DecisionDeadlineExceeded:
                raise
            except Exception as exc:
                if strict or self.failure_handler is None:
                    raise
                failure = getattr(exc, "failure", None) or DecisionFailure.capture(
                    DecisionFailureStage.SEARCH, exc)
                result = self.failure_handler(request, failure)
        result = self._prove_roster(state, result)
        if not result.roster.candidates:
            return DecisionResult(None, result.baseline, result.roster, result,
                                  self._trace(result, None), DecisionReason.EMPTY_ROSTER,
                                  self.behavior_identity)
        use_fail_safe = result.failure is not None
        if use_fail_safe and self.fail_safe_policy is None:
            raise ValueError("failed search result requires a fail-safe policy")
        try:
            if use_fail_safe:
                result, choice = self._fail_safe_choice(state, result, result.failure)
            else:
                choice = self.decision_policy.choose(result.roster, self.policy_configuration)
        except Exception as exc:
            if strict or self.fail_safe_policy is None:
                raise
            failure = DecisionFailure.capture(DecisionFailureStage.POLICY, exc)
            result = replace(result, failure=failure, stop_reason=failure.stage.value)
            result, choice = self._fail_safe_choice(state, result, failure)
        chosen = getattr(choice, "action", choice)
        reason = getattr(choice, "reason", DecisionReason.POLICY)
        try:
            return DecisionResult(chosen, result.baseline, result.roster, result,
                                  self._trace(result, chosen), reason,
                                  self.behavior_identity)
        except Exception as exc:
            if strict or self.fail_safe_policy is None:
                raise
            failure = DecisionFailure.capture(DecisionFailureStage.POLICY, exc)
            return self.recover(state, result, failure)

    def recover(self, state, result, failure) -> DecisionResult:
        if self.fail_safe_policy is None:
            raise ValueError("decision recovery requires a fail-safe policy")
        result = replace(result, failure=failure, stop_reason=failure.stage.value)
        result, choice = self._fail_safe_choice(state, result, failure)
        chosen = getattr(choice, "action", choice)
        reason = getattr(choice, "reason", DecisionReason.POLICY)
        return DecisionResult(chosen, result.baseline, result.roster, result,
                              self._trace(result, chosen), reason,
                              self.behavior_identity)

    def _fail_safe_choice(self, state, result, failure):
        try:
            choice = self.fail_safe_policy.choose(
                result.roster, self.policy_configuration, state, failure)
            return result, choice
        except Exception as exc:
            policy_failure = DecisionFailure.capture(DecisionFailureStage.POLICY, exc)
            recovered = replace(
                result, failure=policy_failure, stop_reason=policy_failure.stage.value)
            candidate = neutral_lottery_choice(
                recovered.roster.candidates, self.policy_configuration)
            return recovered, DecisionChoice(
                candidate.action, DecisionReason.FAIL_SAFE_POLICY_FAILURE)

    @staticmethod
    def _prove_roster(state, result):
        legal_actions = getattr(state, "legal_actions", None)
        if legal_actions is None or result.roster.legal_actions_proven:
            return result
        roster = CandidateRoster.from_legal_actions(
            legal_actions, result.roster.candidates, forced=result.roster.forced)
        return result if roster == result.roster else replace(result, roster=roster)

    @staticmethod
    def _trace(result, chosen):
        candidate = next((item for item in result.roster.candidates
                          if item.action is chosen), None)
        paths = (() if candidate is None else
                 tuple(successor.action_path for successor in candidate.successors))
        return SearchTrace(
            result.nodes_visited, result.stop_reason, result.frontier, chosen, paths)


__all__ = ("DecisionCoordinator", "neutral_lottery_choice")
