import time

from common.ledger import EvaluationModel
from cgpy.experiment import ExperimentSnapshot
from cgpy.experiment.teacher_batch import TeacherBatchRunner
from cgpy.experiment.teacher_batch_contracts import (
    TeacherBatchCase,
    TeacherBatchResult,
    TeacherExecutionConfiguration,
    TeacherModelRecord,
    TeacherWorkerStatus,
)
from cgpy.experiment.teacher_contracts import TeacherSearchConfiguration
from teacher_helpers import end_only_snapshot


def _error_worker(case, connection):
    if case.case_id == "slow":
        time.sleep(0.05)
    connection.send({"status": "error", "failure": case.case_id})
    connection.close()


def _stall_worker(_case, connection):
    time.sleep(2.0)
    connection.close()


def _case(case_id, model, snapshot_path="unused"):
    return TeacherBatchCase(case_id, snapshot_path, 605, model)


def test_batch_runner_uses_explicit_process_limit_and_restores_input_order():
    model = TeacherModelRecord.from_model(EvaluationModel.build())
    cases = (_case("slow", model), _case("fast", model))

    result = TeacherBatchRunner(worker_target=_error_worker).run(
        cases, TeacherExecutionConfiguration(workers=8, root_timeout_seconds=2.0))

    assert result.requested_workers == 8
    assert result.effective_workers == 2
    assert [item.case_id for item in result.items] == ["slow", "fast"]
    assert [item.failure for item in result.items] == ["slow", "fast"]
    assert TeacherBatchResult.loads(result.dumps()) == result


def test_batch_runner_kills_only_the_root_that_exceeds_the_outer_timeout():
    model = TeacherModelRecord.from_model(EvaluationModel.build())

    result = TeacherBatchRunner(worker_target=_stall_worker).run(
        (_case("stuck", model),),
        TeacherExecutionConfiguration(workers=1, root_timeout_seconds=0.05))

    assert result.items[0].status is TeacherWorkerStatus.UNAVAILABLE
    assert result.items[0].stop_reason.value == "worker_timeout"
    assert result.items[0].result is None


def test_branch_batch_deadline_also_expires_queued_branches():
    model = TeacherModelRecord.from_model(EvaluationModel.build())

    result = TeacherBatchRunner(worker_target=_stall_worker).run(
        (_case("active", model), _case("queued", model)),
        TeacherExecutionConfiguration(workers=1, root_timeout_seconds=30.0),
        timeout_seconds=0.05)

    assert [item.case_id for item in result.items] == ["active", "queued"]
    assert all(item.status is TeacherWorkerStatus.UNAVAILABLE for item in result.items)
    assert all(item.stop_reason.value == "worker_timeout" for item in result.items)
    assert all("branch batch" in item.failure for item in result.items)


def test_spawned_worker_loads_snapshot_and_returns_serialized_teacher_result(tmp_path):
    snapshot_path = end_only_snapshot(
        "mega_starmie", tmp_path / "root.snapshot.json.gz")
    model = TeacherModelRecord.from_model(EvaluationModel.build())

    result = TeacherBatchRunner().run(
        (_case("root-1", model, str(snapshot_path)),),
        TeacherExecutionConfiguration(workers=1, root_timeout_seconds=30.0))

    item = result.items[0]
    assert item.status is TeacherWorkerStatus.COMPLETED
    assert item.result is not None
    assert item.result.coverage.value == "complete"
    assert item.result.snapshot_id == ExperimentSnapshot.load(snapshot_path).snapshot_id


def test_completed_worker_preserves_an_incomplete_search_stop_reason(tmp_path):
    snapshot_path = end_only_snapshot(
        "mega_starmie", tmp_path / "capped.snapshot.json.gz")
    model = TeacherModelRecord.from_model(EvaluationModel.build())
    case = TeacherBatchCase(
        "capped", str(snapshot_path), 605, model,
        TeacherSearchConfiguration(node_cap=1))

    result = TeacherBatchRunner().run(
        (case,), TeacherExecutionConfiguration(root_timeout_seconds=30.0))

    assert result.items[0].status is TeacherWorkerStatus.COMPLETED
    assert result.items[0].result.coverage.value == "incomplete"
    assert result.items[0].stop_reason.value == "node_cap"
