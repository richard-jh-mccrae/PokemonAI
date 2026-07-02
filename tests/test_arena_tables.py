"""Arena Table manager: capped live-match slots over worker subprocesses.

Uses the protocol-faithful fake worker (tests/fixtures/arena/fake_worker.py), so
these tests are env-free and fast; the real worker is covered by test_arena_worker.
"""
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from arena import tables as tables_mod  # noqa: E402
from arena.tables import TableFull, TableManager  # noqa: E402

req = pytest.mark.req("REQ-ARENA-0005")

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "arena"
FAKE_WORKER = FIXTURES / "fake_worker.py"
DEAF_WORKER = FIXTURES / "fake_worker_deaf.py"


def _manager(tmp_path, **kw):
    kw.setdefault("worker_cmd", [sys.executable, str(FAKE_WORKER)])
    kw.setdefault("replay_dir", tmp_path)
    return TableManager(**kw)


def _create(mgr, visitor="V"):
    return mgr.create(visitor=visitor, deck=[3] * 60,
                      agent_name="mega_starmie", agent_dir="ignored")


def _wait(table, seen, timeout=30):
    snap = table.wait_change(seen, timeout=timeout)
    assert snap is not None, "no table change within timeout"
    return snap


@req
def test_match_flows_to_completion_and_frees_the_table(tmp_path):
    mgr = _manager(tmp_path, cap=1)
    table = _create(mgr)
    try:
        snap = _wait(table, 0)
        assert snap["state"] == "acting" and snap["obs"]["select"]
        assert mgr.choose(table.id, [0]) is True
        snap = _wait(table, snap["seq"])
        assert snap["state"] == "acting"
        assert mgr.choose(table.id, [0]) is True
        snap = _wait(table, snap["seq"])
        assert snap["state"] == "over" and snap["end"]["kind"] == "end"
        assert Path(table.replay_path).exists()
        assert mgr.live_count() == 0                   # slot freed for the next Visitor
    finally:
        mgr.shutdown()


@req
def test_late_click_after_the_end_is_dropped_and_leaks_no_slot(tmp_path):
    mgr = _manager(tmp_path, cap=1)
    table = _create(mgr)
    try:
        snap = _wait(table, 0)
        mgr.concede(table.id)
        snap = _wait(table, snap["seq"])
        assert snap["state"] == "over"
        assert mgr.choose(table.id, [0]) is False      # dropped, not applied
        assert table.state == "over"                   # a click can't resurrect it
        assert mgr.live_count() == 0
        _create(mgr)                                   # the slot is really free
    finally:
        mgr.shutdown()


@req
def test_cap_rejects_the_fifth_visitor(tmp_path):
    mgr = _manager(tmp_path, cap=4)
    try:
        for _ in range(4):
            _create(mgr)
        with pytest.raises(TableFull):
            _create(mgr)
    finally:
        mgr.shutdown()


@req
def test_idle_table_is_forfeited_by_the_sweep(tmp_path):
    now = [1000.0]
    mgr = _manager(tmp_path, cap=1, idle_timeout=600, clock=lambda: now[0])
    table = _create(mgr)
    try:
        snap = _wait(table, 0)
        now[0] += 599
        mgr.sweep()
        assert table.state != "over"                   # not yet
        now[0] += 2
        mgr.sweep()
        snap = _wait(table, snap["seq"])
        assert snap["state"] == "over" and table.forfeit == "timeout"
        assert mgr.live_count() == 0
    finally:
        mgr.shutdown()


@req
def test_deaf_worker_is_force_killed_after_the_grace(tmp_path):
    now = [1000.0]
    mgr = _manager(tmp_path, cap=1, idle_timeout=600, clock=lambda: now[0],
                   worker_cmd=[sys.executable, str(DEAF_WORKER)])
    table = _create(mgr)
    try:
        snap = _wait(table, 0)
        now[0] += 601
        mgr.sweep()                                    # sends forfeit; worker ignores it
        assert table.state != "over"
        now[0] += tables_mod._FORFEIT_GRACE + 1
        mgr.sweep()                                    # grace over: kill
        snap = _wait(table, snap["seq"])
        assert snap["state"] == "over" and snap["end"]["kind"] == "died"
        assert mgr.live_count() == 0
    finally:
        mgr.shutdown()


@req
def test_finished_tables_are_evicted_after_the_rating_window(tmp_path):
    now = [1000.0]
    mgr = _manager(tmp_path, cap=1, clock=lambda: now[0])
    table = _create(mgr)
    try:
        snap = _wait(table, 0)
        mgr.concede(table.id)
        _wait(table, snap["seq"])
        assert mgr.get(table.id) is table              # rating window: still there
        now[0] += tables_mod._OVER_RETENTION + 1
        mgr.sweep()
        with pytest.raises(KeyError):
            mgr.get(table.id)
    finally:
        mgr.shutdown()


# --- the pre-warm pool --------------------------------------------------------

@req
def test_warm_worker_is_adopted_and_replaced(tmp_path):
    mgr = _manager(tmp_path, cap=2,
                   warm_picker=lambda: ("mega_starmie", "ignored"))
    try:
        assert mgr.warm_agent() == "mega_starmie"      # standby booted at init
        warm_proc = mgr._warm[2]
        table = _create(mgr)                           # matching agent: adopt it
        assert table._proc is warm_proc
        assert mgr.warm_agent() == "mega_starmie"      # a fresh standby took its place
        assert mgr._warm[2] is not warm_proc
        snap = _wait(table, 0)                         # adopted worker actually plays
        assert snap["state"] == "acting"
        mgr.concede(table.id)
        assert _wait(table, snap["seq"])["state"] == "over"
    finally:
        mgr.shutdown()


@req
def test_agent_mismatch_falls_back_to_a_cold_worker(tmp_path):
    mgr = _manager(tmp_path, cap=2,
                   warm_picker=lambda: ("other_bot", "ignored"))
    try:
        warm_proc = mgr._warm[2]
        table = _create(mgr)                           # wants mega_starmie
        assert table._proc is not warm_proc            # cold spawn, warm untouched
        assert mgr.warm_agent() == "other_bot"
        snap = _wait(table, 0)                         # cold path still plays
        assert snap["state"] == "acting"
    finally:
        mgr.shutdown()


@req
def test_no_picker_means_no_standby(tmp_path):
    mgr = _manager(tmp_path, cap=1)
    try:
        assert mgr.warm_agent() is None
        table = _create(mgr)
        assert _wait(table, 0)["state"] == "acting"
    finally:
        mgr.shutdown()


@req
def test_concede_ends_immediately(tmp_path):
    mgr = _manager(tmp_path, cap=1)
    table = _create(mgr)
    try:
        snap = _wait(table, 0)
        mgr.concede(table.id)
        snap = _wait(table, snap["seq"])
        assert snap["state"] == "over" and table.forfeit == "concede"
    finally:
        mgr.shutdown()
