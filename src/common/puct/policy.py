from common.decision import (
    ActionChoiceIdentity, ComponentContract, DecisionPolicyRequest, StatisticIdentity,
)
from common.decision.puct import PUCT_VISIT_STATISTIC, PuctEvidence


class PuctDecisionPolicy:
    identity = "puct-most-visits-v2"
    required_statistics: tuple[StatisticIdentity, ...] = (PUCT_VISIT_STATISTIC,)
    contract = ComponentContract(identity, "PolicyConfiguration")

    def choose(self, request: DecisionPolicyRequest) -> ActionChoiceIdentity:
        evidence = request.evidence
        if not isinstance(evidence, PuctEvidence):
            raise TypeError("PUCT policy requires PUCT evidence")
        available = tuple(edge for edge in evidence.root_edges
                          if edge.statistics.visits > 0)
        if not available:
            raise ValueError("PUCT initialization has no completed simulation evidence")
        visits = max(edge.statistics.visits for edge in available)
        tied = tuple(edge for edge in available if edge.statistics.visits == visits)
        return max(tied, key=lambda edge: edge.statistics.tie_break).choice


__all__ = ("PUCT_VISITS", "PuctDecisionPolicy")
