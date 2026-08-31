"""Process-isolated execution of independent Within-Horizon Teacher roots."""
from __future__ import annotations

import multiprocessing
from dataclasses import dataclass
from time import monotonic, sleep

from .snapshot import ExperimentSnapshot
from .teacher import WithinHorizonTeacher
from .teacher_batch_contracts import (
    TeacherBatchCase,
    TeacherBatchItem,
    TeacherBatchResult,
    TeacherExecutionConfiguration,
    TeacherWorkerStatus,
)
from .teacher_contracts import TeacherSearchResult, TeacherStopReason


def _worker_entry(case: TeacherBatchCase, connection) -> None:
    try:
        snapshot = ExperimentSnapshot.load(case.snapshot_path)
        result = WithinHorizonTeacher().search(
            snapshot, evaluation_model=case.model.to_model(),
            experiment_seed=case.experiment_seed,
            configuration=case.search_configuration,
            baseline_identity=case.baseline_identity)
        connection.send({"status": "completed", "result": result.dumps()})
    except Exception as exc:
        connection.send({
            "status": "error",
            "failure": f"{type(exc).__name__}: {exc}",
        })
    finally:
        connection.close()


@dataclass(slots=True)
class _ActiveWorker:
    process: object
    connection: object
    started: float


def _stop_process(worker: _ActiveWorker) -> None:
    worker.connection.close()
    if worker.process.is_alive():
        worker.process.terminate()
    worker.process.join(timeout=1.0)
    if worker.process.is_alive():
        worker.process.kill()
        worker.process.join(timeout=1.0)


def _message_item(case_id: str, message: dict) -> TeacherBatchItem:
    if message.get("status") == "completed":
        result = TeacherSearchResult.loads(message["result"])
        return TeacherBatchItem(
            case_id, TeacherWorkerStatus.COMPLETED, result.stop_reason, result)
    return TeacherBatchItem(
        case_id, TeacherWorkerStatus.UNAVAILABLE, TeacherStopReason.WORKER_ERROR,
        failure=str(message.get("failure") or "worker returned no result"))


class TeacherBatchRunner:
    def __init__(self, *, worker_target=_worker_entry, clock=monotonic,
                 context_name: str = "spawn"):
        self.worker_target = worker_target
        self.clock = clock
        self.context_name = context_name

    def run(self, cases, configuration: TeacherExecutionConfiguration =
            TeacherExecutionConfiguration()) -> TeacherBatchResult:
        cases = tuple(cases)
        identities = tuple(case.case_id for case in cases)
        if len(set(identities)) != len(identities):
            raise ValueError("Teacher Batch Cases require unique identities")
        started = self.clock()
        effective = min(configuration.workers, len(cases))
        if not cases:
            return TeacherBatchResult(
                (), configuration.workers, 0, max(0.0, self.clock() - started))
        context = multiprocessing.get_context(self.context_name)
        pending = iter(enumerate(cases))
        active: dict[int, _ActiveWorker] = {}
        items: list[TeacherBatchItem | None] = [None] * len(cases)
        exhausted = False

        def launch() -> None:
            nonlocal exhausted
            while not exhausted and len(active) < effective:
                entry = next(pending, None)
                if entry is None:
                    exhausted = True
                    return
                index, case = entry
                receiver, sender = context.Pipe(duplex=False)
                process = context.Process(
                    target=self.worker_target, args=(case, sender),
                    name=f"teacher-root-{index}")
                process.start()
                sender.close()
                active[index] = _ActiveWorker(process, receiver, self.clock())

        launch()
        while active:
            progressed = False
            now = self.clock()
            for index, worker in tuple(active.items()):
                case = cases[index]
                if worker.connection.poll():
                    try:
                        message = worker.connection.recv()
                    except EOFError:
                        message = {"status": "error", "failure": "worker pipe closed"}
                    items[index] = _message_item(case.case_id, message)
                    _stop_process(worker)
                    del active[index]
                    progressed = True
                    continue
                if not worker.process.is_alive():
                    items[index] = TeacherBatchItem(
                        case.case_id, TeacherWorkerStatus.UNAVAILABLE,
                        TeacherStopReason.WORKER_ERROR,
                        failure=f"worker exited with code {worker.process.exitcode}")
                    _stop_process(worker)
                    del active[index]
                    progressed = True
                    continue
                if now - worker.started >= configuration.root_timeout_seconds:
                    items[index] = TeacherBatchItem(
                        case.case_id, TeacherWorkerStatus.UNAVAILABLE,
                        TeacherStopReason.WORKER_TIMEOUT,
                        failure=(f"worker exceeded {configuration.root_timeout_seconds:g}s "
                                 "root timeout"))
                    _stop_process(worker)
                    del active[index]
                    progressed = True
            launch()
            if active and not progressed:
                sleep(min(0.01, configuration.root_timeout_seconds / 10.0))
        elapsed = max(0.0, self.clock() - started)
        return TeacherBatchResult(
            tuple(items), configuration.workers, effective, elapsed)


__all__ = ("TeacherBatchRunner",)
