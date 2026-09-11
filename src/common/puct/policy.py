from dataclasses import dataclass

from common.decision.components import ComponentContract, DecisionPolicyRequest
from common.decision.identity import ActionChoiceIdentity
from common.decision.statistics import StatisticIdentity
from common.decision.puct import PUCT_VISIT_STATISTIC, PuctRootEdge


@dataclass(frozen=True, slots=True)
class PuctDecisionEvidence:
    choice: ActionChoiceIdentity
    reason: str = "most_visits"
    owner: str = "puct"
    schema_version: int = 1


class PuctDecisionPolicy:
    identity = "puct-most-visits-v2"
    required_statistics: tuple[StatisticIdentity, ...] = (PUCT_VISIT_STATISTIC,)
    contract = ComponentContract(
        identity, "PolicyConfiguration",
        required_statistics=frozenset(required_statistics))

    def choose(self, request: DecisionPolicyRequest) -> ActionChoiceIdentity:
        available = tuple(
            statistic for statistic in request.statistics
            if isinstance(statistic, PuctRootEdge) and statistic.statistics.visits > 0)
        if not available:
            raise ValueError("PUCT initialization has no completed simulation evidence")
        visits = max(edge.statistics.visits for edge in available)
        tied = tuple(edge for edge in available if edge.statistics.visits == visits)
        return max(tied, key=lambda edge: edge.statistics.tie_break).choice

    def choose_with_evidence(self, request: DecisionPolicyRequest) -> PuctDecisionEvidence:
        return PuctDecisionEvidence(self.choose(request))


__all__ = ("PuctDecisionEvidence", "PuctDecisionPolicy")
