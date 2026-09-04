from __future__ import annotations

from time import monotonic
from contextlib import contextmanager

from common.decision.puct import PuctResourceUsage, PuctTiming, PuctWork
from common.decision.configuration import DecisionCancelled, DecisionDeadlineExceeded
from dataclasses import dataclass


class SearchBudgetExhausted(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class PreparationExhausted(Exception):
    pass


class SearchCancelled(Exception):
    pass


@dataclass
class _Grant:
    category: str
    units: int = 1
    states: int = 0
    attempted: int = 0
    completed: int = 0
    cancelled_unused: bool = False
    uncertain: bool = False
    settled: bool = False
    preparation_units: int = 0


class SearchBudget:
    def __init__(self, configuration, *, clock=monotonic, execution_guard=None):
        self.configuration = configuration
        self.clock = clock
        self.started = clock()
        seconds = configuration.time_limit_seconds
        if configuration.remaining_match_seconds is not None:
            seconds = min(seconds, configuration.remaining_match_seconds)
        self.deadline = self.started + max(0.0, seconds - configuration.cleanup_reserve_seconds)
        if execution_guard is not None and hasattr(execution_guard, "limit_seconds"):
            self.deadline = min(self.deadline, execution_guard.started + execution_guard.limit_seconds)
        self.execution_guard = execution_guard
        self.counts = dict(transitions=0, evaluations=0, chances=0, states=0)
        self.limits = dict(transitions=configuration.transition_limit,
                           evaluations=configuration.evaluation_limit,
                           chances=configuration.chance_limit, states=configuration.state_limit)
        self.preparing = False
        self.prior_total = self.prior_node = 0
        self.phase_name = "overhead"
        self.phase_started = self.started
        self.seconds = dict(overhead=0.0, search=0.0, prior=0.0)
        self.worker_seconds = dict(prior=0.0, search=0.0)
        self.grants = []
        self.active_grant = None
        self.cache_entries = 0
        self.admission_closed = None

    def stop_admission(self, reason):
        if self.admission_closed is None:
            self.admission_closed = reason

    def cache(self):
        if self.cache_entries >= self.configuration.cache_limit:
            raise SearchBudgetExhausted("cache_limit")
        self.cache_entries += 1

    def worker_timing(self, results, phase):
        if phase not in self.worker_seconds:
            return
        self.worker_seconds[phase] += sum(result.seconds for result in results)
        intervals = sorted((result.started_at, result.started_at + result.seconds) for result in results)
        covered, previous_end = 0.0, self.started
        for start, end in intervals:
            covered += max(0.0, end - max(start, previous_end))
            previous_end = max(previous_end, end)
        transferred = min(self.seconds["overhead"], covered)
        self.seconds["overhead"] -= transferred
        self.seconds[phase] += transferred

    def _switch(self, name):
        now = self.clock()
        self.seconds[self.phase_name] += now - self.phase_started
        self.phase_started, self.phase_name = now, name

    @contextmanager
    def phase(self, name):
        previous = self.phase_name
        self._switch(name)
        try:
            yield
        finally:
            self._switch(previous)

    def timing(self):
        self._switch(self.phase_name)
        return PuctTiming(self.seconds["prior"], self.seconds["search"], self.seconds["overhead"],
                          self.phase_started - self.started, self.worker_seconds["prior"],
                          self.worker_seconds["search"])

    @contextmanager
    def preparation(self):
        self.preparing = True
        self.prior_node = 0
        try:
            yield
        finally:
            self.preparing = False

    def _preparation_call(self, units):
        if not self.preparing:
            return 0
        if (self.prior_node + units > self.configuration.prior_node_operations
                or self.prior_total + units > self.configuration.prior_total_operations):
            raise PreparationExhausted()
        self.prior_node += units
        self.prior_total += units
        return units

    def prepare(self, units=1):
        self.check()
        return self._preparation_call(int(units))

    def check(self):
        if self.execution_guard is not None:
            try:
                self.execution_guard.check()
            except DecisionCancelled as exc:
                raise SearchCancelled() from exc
            except DecisionDeadlineExceeded as exc:
                raise SearchBudgetExhausted("outer_deadline") from exc
        if self.clock() >= self.deadline:
            raise SearchBudgetExhausted("time_limit")

    def cancellation_requested(self):
        if self.execution_guard is None:
            return False
        try:
            self.execution_guard.check()
        except DecisionCancelled:
            return True
        except DecisionDeadlineExceeded:
            return False
        return False

    def retain(self, amount=1):
        self.check()
        if self.counts["states"] + amount > self.limits["states"]:
            raise SearchBudgetExhausted("state_limit")
        self.counts["states"] += amount

    def release(self, amount=1):
        amount = int(amount)
        if not 0 <= amount <= self.counts["states"]:
            raise ValueError("released state capacity exceeds retained capacity")
        self.counts["states"] -= amount

    def reserve(self, operation, *, creates_state=False, units=1):
        self.check()
        units = int(units)
        if units < 1:
            raise ValueError("operation reservation must be positive")
        if self.admission_closed is not None:
            raise SearchBudgetExhausted(self.admission_closed)
        if self.counts[operation] + units > self.limits[operation]:
            reason = {"transitions": "transition_limit", "evaluations": "evaluation_limit",
                      "chances": "chance_limit"}[operation]
            raise SearchBudgetExhausted(reason)
        preparation_units = self._preparation_call(units)
        if creates_state:
            self.retain(int(creates_state))
        self.counts[operation] += units
        grant = _Grant(operation, units, int(creates_state), preparation_units=preparation_units)
        self.grants.append(grant)
        return grant

    def settle(self, grant, *, started, completed, dispatched=True,
               used_units=None, used_states=None):
        if grant.settled:
            raise RuntimeError("work grant settled twice")
        used_units = grant.units if used_units is None else int(used_units)
        used_states = grant.states if used_states is None else int(used_states)
        if not 0 <= used_units <= grant.units or not 0 <= used_states <= grant.states:
            raise RuntimeError("provider exceeded its reserved work capacity")
        grant.attempted = used_units if started else 0
        grant.completed = used_units if completed else 0
        grant.cancelled_unused = not dispatched
        grant.uncertain = dispatched and not started
        grant.settled = True
        if not dispatched:
            used_units = used_states = 0
        if completed or not dispatched:
            self.counts[grant.category] -= grant.units - used_units
            self.counts["states"] -= grant.states - used_states
            unused_preparation = grant.preparation_units - used_units
            self.prior_total -= max(0, unused_preparation)
            if self.preparing:
                self.prior_node -= max(0, unused_preparation)

    def begin_local(self, operation, *, creates_state=False):
        grant = self.reserve(operation, creates_state=creates_state)
        grant.attempted = grant.units

        def completed():
            self.settle(grant, started=True, completed=True)

        return completed

    def call(self, operation, function, *, creates_state=False, units=1):
        grant = self.reserve(operation, creates_state=creates_state, units=units)
        previous, self.active_grant = self.active_grant, grant
        completed = False
        try:
            result = function()
            completed = True
            self.check()
            return result
        finally:
            self.active_grant = previous
            if not grant.settled:
                self.settle(grant, started=True, completed=completed)

    def snapshot(self):
        counts = {category: sum(grant.attempted for grant in self.grants if grant.category == category)
                  for category in ("transitions", "evaluations", "chances")}
        return PuctWork(**counts, state_capacity_charged=self.counts["states"])

    def resources(self):
        return tuple(PuctResourceUsage(
            category, sum(grant.units for grant in grants), sum(grant.attempted for grant in grants),
            sum(grant.completed for grant in grants),
            sum(grant.units for grant in grants if grant.cancelled_unused),
            sum(grant.units for grant in grants if grant.uncertain))
            for category in ("transitions", "evaluations", "chances")
            for grants in ([grant for grant in self.grants if grant.category == category],))
