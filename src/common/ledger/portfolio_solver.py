from __future__ import annotations

from collections import Counter, OrderedDict, deque
from dataclasses import dataclass, field

from .capabilities import OptionUnits


DEFAULT_TURN_PORTFOLIO_MEMO_ENTRIES = 1_024
EXECUTION_GUARD_CHECK_INTERVAL = 256
DOMINANCE_FRONTIER_ENTRIES = 1


@dataclass(frozen=True, slots=True)
class Fetch:
    eligible: tuple[int, ...]
    amount: float
    to_bench: bool
    zone: str
    field: str = "search"
    distinct_groups: tuple[tuple[int, int], ...] = ()
    consumes: bool = True
    target_resources: tuple[tuple[int, str], ...] = ()
    target_reservations: tuple[tuple[int, str], ...] = ()


@dataclass(frozen=True, slots=True)
class Opportunity:
    units: OptionUnits
    requirements: tuple[tuple[str, float], ...]
    discard_cost: int
    fetches: tuple[Fetch, ...] = ()
    discards_hand: bool = False
    entry_index: int = -1
    direct_worth: float = 0.0
    reservations: tuple[tuple[str, float], ...] = ()
    legacy_order: int = -1


@dataclass(frozen=True, slots=True)
class PortfolioProblem:
    capacities: tuple[tuple[str, float], ...]
    opportunities: tuple[Opportunity, ...]
    hand_size: int
    coefficients: tuple[float, ...]
    entry_count: int = field(compare=False, hash=False)
    class_count: int = field(compare=False, hash=False)


@dataclass(frozen=True, slots=True)
class PortfolioSelection:
    entry_index: int
    units: OptionUnits
    legacy_order: int


@dataclass(frozen=True, slots=True)
class PortfolioPlan:
    units: OptionUnits = OptionUnits()
    selections: tuple[PortfolioSelection, ...] = ()
    direct_worth: float = 0.0
    score: float = 0.0


@dataclass(frozen=True, slots=True)
class PortfolioSolveStatistics:
    entry_count: int = 0
    class_count: int = 0
    opportunity_count: int = 0
    states_visited: int = 0
    memo_hits: int = 0
    dominance_prunes: int = 0
    bound_prunes: int = 0
    turn_cache_hits: int = 0
    turn_cache_misses: int = 0


class TurnPortfolioMemo:
    def __init__(self, max_entries: int = DEFAULT_TURN_PORTFOLIO_MEMO_ENTRIES):
        if max_entries <= 0:
            raise ValueError("Portfolio Memo size must be positive")
        self.max_entries = int(max_entries)
        self._plans = OrderedDict()
        self.lookups = 0
        self.hits = 0
        self.evictions = 0

    def lookup(self, key):
        self.lookups += 1
        if key not in self._plans:
            return None
        self.hits += 1
        return self._plans[key]

    def store(self, key, plan: PortfolioPlan) -> None:
        if key in self._plans:
            self._plans[key] = plan
            return
        self._plans[key] = plan
        if len(self._plans) > self.max_entries:
            self._plans.popitem(last=False)
            self.evictions += 1

    def clear(self) -> None:
        self._plans.clear()
        self.lookups = 0
        self.hits = 0
        self.evictions = 0

    def metrics(self) -> dict[str, int]:
        return {
            "entries": len(self._plans),
            "lookups": self.lookups,
            "hits": self.hits,
            "misses": self.lookups - self.hits,
            "evictions": self.evictions,
        }

    def __len__(self) -> int:
        return len(self._plans)


@dataclass(frozen=True, slots=True)
class _SolverState:
    used: tuple[float, ...]
    reserved: tuple[float, ...]
    discards: int = 0
    exhausted: bool = False


@dataclass(frozen=True, slots=True)
class _FrontierState:
    used: tuple[float, ...]
    reserved: tuple[float, ...]
    discards: int
    score: float


def add_units(left: OptionUnits, right: OptionUnits) -> OptionUnits:
    return OptionUnits(**{
        name: getattr(left, name) + getattr(right, name)
        for name in OptionUnits.__dataclass_fields__
    })


def with_unit(units: OptionUnits, name: str, value: float) -> OptionUnits:
    return OptionUnits(**{
        field: value if field == name else getattr(units, field)
        for field in OptionUnits.__dataclass_fields__
    })


def _score_units(units: OptionUnits, coefficients: tuple[float, ...]) -> float:
    return sum(
        getattr(units, field) * coefficient
        for field, coefficient in zip(OptionUnits.__dataclass_fields__, coefficients)
    )


def _realize_fetches(opportunity: Opportunity, usage, capacities):
    if not opportunity.fetches:
        return (), (), opportunity.units
    requirements = []
    reservations = []
    claimed = Counter()
    bench_claim = 0
    local_usage = dict(usage)
    used_groups = set()
    bench_available = capacities.get("bench", 0.0) - usage.get("bench", 0.0)
    for fetch in sorted(opportunity.fetches, key=lambda item: len(item.eligible)):
        wanted = min(fetch.amount, int(bench_available) if fetch.to_bench else fetch.amount)
        for card_id in fetch.eligible:
            group = next((value for target, value in fetch.distinct_groups
                          if target == card_id), None)
            if group is not None and group in used_groups:
                continue
            source_key = f"{fetch.zone}:{card_id}"
            available = capacities.get(source_key, 0.0) - local_usage.get(source_key, 0.0)
            target_keys = tuple(key for target, key in fetch.target_resources
                                if target == card_id)
            reservation_keys = tuple(
                key for target, key in fetch.target_reservations
                if target == card_id)
            for target_key in target_keys:
                available = min(
                    available,
                    capacities.get(target_key, 0.0) - local_usage.get(target_key, 0.0))
            for reservation_key in reservation_keys:
                available = min(available, capacities.get(reservation_key, 0.0))
            take = min(wanted, available)
            if group is not None:
                take = min(take, 1.0)
            if take:
                if fetch.consumes:
                    requirements.append((source_key, float(take)))
                    local_usage[source_key] = local_usage.get(source_key, 0.0) + take
                for target_key in target_keys:
                    requirements.append((target_key, float(take)))
                    local_usage[target_key] = local_usage.get(target_key, 0.0) + take
                reservations.extend(
                    (reservation_key, float(take))
                    for reservation_key in reservation_keys)
                wanted -= take
                claimed[fetch.field] += take
                if group is not None:
                    used_groups.add(group)
                if fetch.to_bench:
                    bench_available -= take
                    bench_claim += take
            if not wanted:
                break
    if bench_claim:
        requirements.append(("bench", float(bench_claim)))
    realized = opportunity.units
    for field in {fetch.field for fetch in opportunity.fetches}:
        amount = claimed.get(field, 0.0)
        realized = with_unit(
            realized, field, min(getattr(realized, field), float(amount)))
    return tuple(requirements), tuple(reservations), realized


def _advance(problem: PortfolioProblem, state: _SolverState,
             opportunity: Opportunity, keys: tuple[str, ...], capacities: dict[str, float]):
    if state.exhausted:
        return None
    usage = dict(zip(keys, state.used))
    reservation = dict(zip(keys, state.reserved))
    fetch_requirements, fetch_reservations, realized_units = _realize_fetches(
        opportunity, usage, capacities)
    for requirement, amount in (*opportunity.requirements, *fetch_requirements):
        if usage.get(requirement, 0.0) + amount > capacities.get(requirement, 0.0):
            return None
        usage[requirement] = usage.get(requirement, 0.0) + amount
    for requirement, amount in (*opportunity.reservations, *fetch_reservations):
        reserved_amount = reservation.get(requirement, 0.0) + amount
        if reserved_amount > capacities.get(requirement, 0.0):
            return None
        reservation[requirement] = reserved_amount
    hand_resources_used = sum(
        max(amount, reservation.get(name, 0.0))
        for name, amount in usage.items() if name.startswith("hand:"))
    next_discards = (
        max(state.discards, problem.hand_size - hand_resources_used)
        if opportunity.discards_hand else state.discards + opportunity.discard_cost)
    if hand_resources_used + next_discards > problem.hand_size:
        return None
    return (
        _SolverState(
            tuple(usage.get(name, 0.0) for name in keys),
            tuple(reservation.get(name, 0.0) for name in keys),
            next_discards,
            opportunity.discards_hand,
        ),
        realized_units,
    )


def _uses_no_more(left: tuple[float, ...], right: tuple[float, ...]) -> bool:
    return all(first <= second for first, second in zip(left, right))


def _tie_key(selections: tuple[PortfolioSelection, ...]):
    return len(selections), tuple(item.legacy_order for item in selections)


def solve_portfolio(problem: PortfolioProblem, *, execution_guard=None
                    ) -> tuple[PortfolioPlan, PortfolioSolveStatistics]:
    capacities = dict(problem.capacities)
    keys = tuple(name for name, _amount in problem.capacities)
    initial = _SolverState(tuple(0.0 for _key in keys), tuple(0.0 for _key in keys))
    opportunities = problem.opportunities
    upper = [0.0] * (len(opportunities) + 1)
    for index in range(len(opportunities) - 1, -1, -1):
        opportunity = opportunities[index]
        optimistic = sum(
            max(0.0, getattr(opportunity.units, field) * coefficient)
            for field, coefficient in zip(
                OptionUnits.__dataclass_fields__, problem.coefficients))
        optimistic += max(0.0, opportunity.direct_worth)
        copies = int(capacities.get(f"copy:{opportunity.entry_index}", 1.0))
        upper[index] = upper[index + 1] + optimistic * copies

    best: PortfolioPlan | None = None
    best_prefix = {}
    frontiers: dict[tuple[int, bool], deque[_FrontierState]] = {}
    states_visited = memo_hits = dominance_prunes = bound_prunes = 0

    def candidate_is_better(candidate: PortfolioPlan, incumbent: PortfolioPlan | None) -> bool:
        if incumbent is None or candidate.score > incumbent.score:
            return True
        return candidate.score == incumbent.score and _tie_key(
            candidate.selections) < _tie_key(incumbent.selections)

    def visit(index: int, state: _SolverState, units: OptionUnits,
              direct_worth: float, score: float,
              selections: tuple[PortfolioSelection, ...]):
        nonlocal best, states_visited, memo_hits, dominance_prunes, bound_prunes
        states_visited += 1
        if execution_guard is not None and (
                states_visited == 1
                or states_visited % EXECUTION_GUARD_CHECK_INTERVAL == 0):
            execution_guard.check()
        if best is not None and score + upper[index] < best.score:
            bound_prunes += 1
            return
        state_key = (index, state)
        tie = _tie_key(selections)
        incumbent_prefix = best_prefix.get(state_key)
        if incumbent_prefix is not None:
            incumbent_score, incumbent_tie = incumbent_prefix
            if incumbent_score > score or (
                    incumbent_score == score and incumbent_tie <= tie):
                memo_hits += 1
                return
        best_prefix[state_key] = (score, tie)

        frontier_key = (index, state.exhausted)
        frontier = frontiers.setdefault(
            frontier_key, deque(maxlen=DOMINANCE_FRONTIER_ENTRIES))
        if any(
                item.score > score
                and item.discards <= state.discards
                and _uses_no_more(item.used, state.used)
                and _uses_no_more(item.reserved, state.reserved)
                for item in frontier):
            dominance_prunes += 1
            return
        frontier.append(_FrontierState(state.used, state.reserved, state.discards, score))

        if state.exhausted or index >= len(opportunities):
            candidate = PortfolioPlan(units, selections, direct_worth, score)
            if candidate_is_better(candidate, best):
                best = candidate
            return

        opportunity = opportunities[index]
        next_state = state
        next_units = units
        next_direct = direct_worth
        next_score = score
        next_selections = selections
        while True:
            advanced = _advance(problem, next_state, opportunity, keys, capacities)
            if advanced is None:
                break
            next_state, realized = advanced
            next_units = add_units(next_units, realized)
            next_direct += opportunity.direct_worth
            next_score += _score_units(realized, problem.coefficients) + opportunity.direct_worth
            next_selections = (*next_selections, PortfolioSelection(
                opportunity.entry_index, realized, opportunity.legacy_order))
            visit(index + 1, next_state, next_units, next_direct, next_score, next_selections)
            if next_state.exhausted:
                break
        visit(index + 1, state, units, direct_worth, score, selections)

    visit(0, initial, OptionUnits(), 0.0, 0.0, ())
    statistics = PortfolioSolveStatistics(
        problem.entry_count,
        problem.class_count,
        len(problem.opportunities),
        states_visited,
        memo_hits,
        dominance_prunes,
        bound_prunes,
    )
    return best or PortfolioPlan(), statistics


__all__ = (
    "Fetch", "Opportunity", "PortfolioPlan", "PortfolioProblem", "PortfolioSelection",
    "PortfolioSolveStatistics", "TurnPortfolioMemo", "add_units", "solve_portfolio",
    "with_unit",
)
