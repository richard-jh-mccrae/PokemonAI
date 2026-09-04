import time
import os
import pytest
from threading import Event, Thread

from common.puct.workers import BoundedWorkers, WorkItem


_AFFINITY_COUNTS = {}


def affinity_count(key):
    _AFFINITY_COUNTS[key] = _AFFINITY_COUNTS.get(key, 0) + 1
    return _AFFINITY_COUNTS[key]


def delayed_value(value, delay):
    time.sleep(delay)
    return value


def exit_worker():
    os._exit(7)


def test_worker_completion_races_preserve_numbered_results():
    with BoundedWorkers(2, outstanding_limit=3) as workers:
        result = workers.run_batch(
            (WorkItem(0, delayed_value, ("slow", 0.05)), WorkItem(1, delayed_value, ("fast", 0))),
            deadline=time.monotonic() + 10)
        assert tuple(item.task_id for item in result) == (0, 1)
        assert tuple(item.value for item in result) == ("slow", "fast")
        assert len({item.process_id for item in result}) == 2
    assert not workers.alive


def test_hung_work_is_terminated_within_cleanup_allowance():
    workers = BoundedWorkers(1, outstanding_limit=1)
    started = time.monotonic()
    result = workers.run_batch((WorkItem(0, delayed_value, ("late", 60)),), deadline=started + 1)
    workers.close()
    assert time.monotonic() - started < 4
    assert result == ()
    assert not workers.alive


def test_dead_worker_returns_typed_failures_without_losing_batch_results():
    workers = BoundedWorkers(1, outstanding_limit=1)
    try:
        first = workers.run_batch((WorkItem(0, exit_worker, ()),), deadline=time.monotonic() + 10)
        second = workers.run_batch((WorkItem(1, delayed_value, ("unused", 0)),),
                                   deadline=time.monotonic() + 10)

        assert len(first) == 1 and first[0].error_type is not None
        assert len(second) == 1 and second[0].error_type is not None
    finally:
        workers.close()


def test_cancellation_hard_stops_running_work():
    workers = BoundedWorkers(1, outstanding_limit=1)
    cancelled = Event()
    timer = Thread(target=lambda: (time.sleep(0.2), cancelled.set()), daemon=True)
    started = time.monotonic()
    timer.start()
    try:
        result = workers.run_batch(
            (WorkItem(0, delayed_value, ("late", 60)),),
            deadline=started + 20, cancelled=cancelled.is_set)
    finally:
        workers.close()

    assert time.monotonic() - started < 3
    assert result == ()
    assert workers.interrupted
    assert not workers.alive


def test_outstanding_task_cap_rejects_a_larger_batch_before_dispatch():
    workers = BoundedWorkers(1, outstanding_limit=1)
    try:
        with pytest.raises(ValueError, match="outstanding"):
            workers.run_batch((
                WorkItem(0, delayed_value, ("a", 0)),
                WorkItem(1, delayed_value, ("b", 0)),
            ), deadline=time.monotonic() + 10)
        assert not workers.alive
    finally:
        workers.close()


def test_affinity_routes_followup_work_to_the_owning_worker():
    with BoundedWorkers(2, outstanding_limit=2) as workers:
        first = workers.run_batch((
            WorkItem(0, affinity_count, ("a",), "a"),
            WorkItem(1, affinity_count, ("b",), "b"),
        ), deadline=time.monotonic() + 10)
        second = workers.run_batch((
            WorkItem(2, affinity_count, ("b",), "b"),
            WorkItem(3, affinity_count, ("a",), "a"),
        ), deadline=time.monotonic() + 10)

    first_pid = {item.task_id: item.process_id for item in first}
    second_pid = {item.task_id: item.process_id for item in second}
    assert first_pid[0] == second_pid[3]
    assert first_pid[1] == second_pid[2]
    assert tuple(item.value for item in second) == (2, 2)
