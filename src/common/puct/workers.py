from __future__ import annotations

import copyreg
import io
import multiprocessing
import os
import pickle
import time
from dataclasses import dataclass
from multiprocessing.process import BaseProcess
from types import MappingProxyType
from typing import Callable, Protocol
from queue import Empty, Queue
from threading import Thread
from common.cards.card_facts import Clause


class _Pipe(Protocol):
    def send_bytes(self, buf: bytes) -> None: ...
    def recv_bytes(self, maxlength: int) -> bytes: ...
    def close(self) -> None: ...


def _mapping_proxy(value):
    return MappingProxyType(value)


def _reduce_proxy(value):
    return _mapping_proxy, (dict(value),)


def _clause(kind, params):
    return Clause(kind, **params)


def _reduce_clause(value):
    return _clause, (value.kind, dict(value.params))


def _encode(value):
    buffer = io.BytesIO()
    encoder = pickle.Pickler(buffer, protocol=pickle.HIGHEST_PROTOCOL)
    encoder.dispatch_table = {**copyreg.dispatch_table, MappingProxyType: _reduce_proxy, Clause: _reduce_clause}
    encoder.dump(value)
    return buffer.getvalue()


@dataclass(frozen=True, slots=True)
class WorkItem:
    task_id: int
    function: Callable
    arguments: tuple
    affinity: str | None = None


@dataclass(frozen=True, slots=True)
class WorkResult:
    task_id: int
    value: object
    error_type: str | None
    error: str | None
    process_id: int
    seconds: float
    started_at: float = 0.0


@dataclass(frozen=True, slots=True)
class WorkStarted:
    task_id: int


def _serve(connection, message_limit):
    try:
        while True:
            packet = connection.recv_bytes(message_limit)
            if not packet:
                return
            item = pickle.loads(packet)
            connection.send_bytes(_encode(WorkStarted(item.task_id)))
            started = time.monotonic()
            try:
                value = item.function(*item.arguments)
                result = WorkResult(item.task_id, value, None, None, os.getpid(), time.monotonic() - started, started)
            except Exception as exc:
                result = WorkResult(item.task_id, None, type(exc).__name__, str(exc)[:2000],
                                    os.getpid(), time.monotonic() - started, started)
            encoded = _encode(result)
            if len(encoded) > message_limit:
                encoded = _encode(WorkResult(item.task_id, None, "MessageLimit", "worker result exceeds IPC cap",
                                             os.getpid(), time.monotonic() - started))
            connection.send_bytes(encoded)
    except (EOFError, BrokenPipeError, OSError):
        return
    finally:
        connection.close()


class BoundedWorkers:
    def __init__(self, count: int, *, outstanding_limit: int, message_limit: int = 16 * 1024 * 1024):
        if count < 1 or outstanding_limit < 1 or message_limit < 1:
            raise ValueError("worker limits must be positive")
        self.count = count
        self.outstanding_limit = outstanding_limit
        self.message_limit = message_limit
        self.processes: list[BaseProcess] = []
        self.connections: list[_Pipe] = []
        self.closed = False
        self.transport_threads: list[Thread] = []
        self.started_tasks: set[int] = set()
        self.dispatched_tasks: set[int] = set()
        self.interrupted = False
        self.affinities: dict[str, _Pipe] = {}

    def _exchange(self, connection, packet, task_id, replies):
        try:
            connection.send_bytes(packet)
            result = pickle.loads(connection.recv_bytes(self.message_limit))
            if isinstance(result, WorkStarted):
                replies.put((connection, result))
                result = pickle.loads(connection.recv_bytes(self.message_limit))
        except Exception as exc:
            result = WorkResult(task_id, None, type(exc).__name__, str(exc), 0, 0.0)
        replies.put((connection, result))

    def _start(self):
        if self.processes:
            return
        context = multiprocessing.get_context("spawn")
        try:
            for _ in range(self.count):
                parent, child = context.Pipe()
                process = context.Process(target=_serve, args=(child, self.message_limit), daemon=True)
                process.start()
                child.close()
                self.connections.append(parent)
                self.processes.append(process)
        except Exception:
            self.close()
            raise

    @property
    def alive(self):
        return any(process.is_alive() for process in self.processes)

    def run_batch(self, items: tuple[WorkItem, ...], *, deadline: float,
                  cancelled=None) -> tuple[WorkResult, ...]:
        self.started_tasks = set()
        self.dispatched_tasks = set()
        self.interrupted = False
        if self.closed:
            raise RuntimeError("worker facility is closed")
        if len(items) > self.outstanding_limit or len({item.task_id for item in items}) != len(items):
            raise ValueError("invalid outstanding work batch")
        if not items or time.monotonic() >= deadline:
            return ()
        self._start()
        packets = tuple(_encode(item) for item in items)
        if any(len(packet) > self.message_limit for packet in packets):
            raise ValueError("worker request exceeds IPC cap")
        pending: dict[_Pipe, int] = {}
        results: dict[int, WorkResult] = {}
        next_index = 0
        replies: Queue[tuple[_Pipe, WorkStarted | WorkResult]] = Queue(maxsize=self.count)
        while next_index < len(items) or pending:
            if cancelled is not None and cancelled():
                self.interrupted = True
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            for connection, process in zip(self.connections, self.processes):
                if connection not in pending and next_index < len(items):
                    item = items[next_index]
                    owner = None if item.affinity is None else self.affinities.get(item.affinity)
                    if owner is not None and owner is not connection:
                        continue
                    if not process.is_alive():
                        results[item.task_id] = WorkResult(
                            item.task_id, None, "WorkerExited", "worker exited unexpectedly",
                            process.pid or 0, 0.0)
                        next_index += 1
                        continue
                    if item.affinity is not None:
                        self.affinities[item.affinity] = connection
                    pending[connection] = item.task_id
                    self.dispatched_tasks.add(item.task_id)
                    transport = Thread(target=self._exchange, args=(
                        connection, packets[next_index], item.task_id, replies), daemon=True)
                    self.transport_threads = [thread for thread in self.transport_threads if thread.is_alive()]
                    self.transport_threads.append(transport)
                    transport.start()
                    next_index += 1
            try:
                connection, result = replies.get(timeout=min(remaining, 0.05))
            except Empty:
                continue
            task_id = pending[connection]
            if result.task_id != task_id:
                pending.pop(connection)
                results[task_id] = WorkResult(
                    task_id, None, "TaskIdentityMismatch",
                    "worker returned an unexpected task identity", 0, 0.0)
                continue
            if isinstance(result, WorkStarted):
                self.started_tasks.add(task_id)
                continue
            pending.pop(connection)
            if time.monotonic() < deadline:
                results[task_id] = result
        if pending or next_index < len(items):
            self.close()
        return tuple(results[item.task_id] for item in items if item.task_id in results)

    def close(self):
        if self.closed:
            return
        self.closed = True
        for process in self.processes:
            if process.is_alive():
                process.terminate()
        deadline = time.monotonic() + 1.0
        for process in self.processes:
            process.join(max(0.0, deadline - time.monotonic()))
            if process.is_alive():
                process.kill()
                process.join(max(0.0, deadline - time.monotonic()))
        for connection in self.connections:
            connection.close()
        for thread in self.transport_threads:
            thread.join(max(0.0, deadline - time.monotonic()))

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
