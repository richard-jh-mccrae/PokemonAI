from __future__ import annotations

from itertools import product
from random import Random

from common.ledger.capabilities import OptionUnits
from common.ledger.portfolio_solver import Opportunity, PortfolioProblem, solve_portfolio


def _coefficients(draw, search):
    values = {"draw": draw, "search": search}
    return tuple(values.get(field, 0.0) for field in OptionUnits.__dataclass_fields__)


def _oracle(problem):
    capacities = dict(problem.capacities)
    bounds = tuple(
        range(int(capacities[f"copy:{opportunity.entry_index}"]) + 1)
        for opportunity in problem.opportunities)
    best = 0.0
    for counts in product(*bounds):
        usage = {}
        discards = 0
        score = 0.0
        feasible = True
        for count, opportunity in zip(counts, problem.opportunities):
            discards += count * opportunity.discard_cost
            score += count * (
                sum(getattr(opportunity.units, field) * coefficient
                    for field, coefficient in zip(
                        OptionUnits.__dataclass_fields__, problem.coefficients))
                + opportunity.direct_worth)
            for resource, amount in opportunity.requirements:
                usage[resource] = usage.get(resource, 0.0) + count * amount
                if usage[resource] > capacities.get(resource, 0.0):
                    feasible = False
        for entry_index in {item.entry_index for item in problem.opportunities}:
            if sum(count for count, item in zip(counts, problem.opportunities)
                   if item.entry_index == entry_index) > capacities[f"copy:{entry_index}"]:
                feasible = False
        hand_used = sum(amount for name, amount in usage.items()
                        if name.startswith("hand:"))
        if hand_used + discards > problem.hand_size:
            feasible = False
        if feasible:
            best = max(best, score)
    return best


def test_exact_solver_matches_random_small_exhaustive_problems():
    random = Random(636)
    for _case in range(100):
        capacities = {
            "copy:0": float(random.randint(1, 2)),
            "copy:1": float(random.randint(1, 2)),
            "resource:0": float(random.randint(1, 3)),
            "resource:1": float(random.randint(1, 3)),
        }
        opportunities = []
        for index in range(4):
            entry_index = index // 2
            resource = f"resource:{random.randint(0, 1)}"
            opportunities.append(Opportunity(
                OptionUnits(draw=random.randint(0, 3), search=random.randint(0, 2)),
                ((f"copy:{entry_index}", 1.0), (resource, 1.0)),
                random.randint(0, 1),
                entry_index=entry_index,
                direct_worth=float(random.randint(-2, 2)),
                legacy_order=index,
            ))
        problem = PortfolioProblem(
            tuple(sorted(capacities.items())), tuple(opportunities),
            random.randint(2, 5),
            _coefficients(random.randint(-2, 3), random.randint(-2, 3)),
            sum(int(capacities[f"copy:{index}"]) for index in range(2)),
            2,
        )

        plan, _statistics = solve_portfolio(problem)

        assert plan.score == _oracle(problem)
