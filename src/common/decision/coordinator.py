from __future__ import annotations

from dataclasses import dataclass

from .contracts import DecisionResult, EvaluationRequest, SearchTrace


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

    def decide(self, state, *, provider=None, parent_valuation=None,
               observation_delta=None) -> DecisionResult:
        request = EvaluationRequest(
            state, self.evaluation_model, parent_valuation, observation_delta)
        result = self.search.search(
            request, self.evaluator, self.policy_model, provider,
            self.search_configuration)
        if not result.roster.candidates:
            return DecisionResult(None, result.baseline, result.roster, result,
                                  self._trace(result, None), "empty_roster",
                                  self.behavior_identity)
        choice = self.decision_policy.choose(result.roster, self.policy_configuration)
        chosen = getattr(choice, "action", choice)
        reason = getattr(choice, "reason", self.decision_policy.identity)
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
