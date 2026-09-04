from common.decision import DecisionChoice, DecisionReason


class PuctDecisionPolicy:
    identity = "puct-most-visits-v1"

    def choose(self, roster, configuration):
        if roster.forced and len(roster.candidates) == 1:
            return DecisionChoice(roster.candidates[0].action, DecisionReason.FORCED)
        available = tuple(candidate for candidate in roster.candidates
                          if candidate.puct is not None and candidate.puct.visits > 0)
        if not available:
            raise ValueError("PUCT initialization has no completed simulation evidence")
        visits = max(candidate.puct.visits for candidate in available)
        tied = tuple(candidate for candidate in available if candidate.puct.visits == visits)
        return DecisionChoice(max(tied, key=lambda item: item.puct.tie_break).action, DecisionReason.POLICY)
