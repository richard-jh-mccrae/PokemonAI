"""Live cgpy controller for complete Within-Horizon Teacher policies."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import tempfile
from time import perf_counter

from common.api import ActionIdentity
from cgpy.experiment import (
    TeacherBatchRunner, TeacherCoverage, TeacherExecutionConfiguration,
    TeacherModelRecord, TeacherSearchConfiguration, TeacherStopReason,
    TeacherSearchResult, TeacherWorkerStatus, TurnSearchEnvironment, WithinHorizonTeacher,
)


class TeacherSearchUnavailable(RuntimeError):
    def __init__(self, stop_reason: TeacherStopReason, message: str):
        super().__init__(message)
        self.stop_reason = stop_reason


@dataclass(frozen=True, slots=True)
class LiveTeacherCase:
    case_id: str
    engine: object
    perspective_seat: int
    knowledge: object
    experiment_seed: int
    model: TeacherModelRecord
    search_configuration: TeacherSearchConfiguration
    baseline_identity: str
    policy_path: str


@dataclass(frozen=True, slots=True)
class LiveTeacherSearch:
    result: TeacherSearchResult
    policy: tuple[tuple[str, ActionIdentity], ...]


def _tupleize(value):
    if isinstance(value, list):
        return tuple(_tupleize(child) for child in value)
    if isinstance(value, dict):
        return {key: _tupleize(child) for key, child in value.items()}
    return value


def _write_live_policy(path: Path, policy) -> None:
    document = [{
        "information_key": key,
        "action": {"kind": action.kind, "parts": action.parts},
    } for key, action in policy]
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(document, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    temporary.replace(path)


def _load_live_policy(path: Path) -> tuple[tuple[str, ActionIdentity], ...]:
    document = json.loads(path.read_text(encoding="utf-8"))
    return tuple((
        str(entry["information_key"]),
        ActionIdentity(str(entry["action"]["kind"]), _tupleize(entry["action"]["parts"])),
    ) for entry in document)


def _live_worker_entry(case: LiveTeacherCase, connection) -> None:
    try:
        environment = TurnSearchEnvironment.from_engine(
            case.engine, perspective_seat=case.perspective_seat,
            knowledge=case.knowledge)
        result = WithinHorizonTeacher().search_environment(
            environment, evaluation_model=case.model.to_model(),
            experiment_seed=case.experiment_seed,
            configuration=case.search_configuration,
            baseline_identity=case.baseline_identity)
        policy = {}
        for entry in result.selected_policy:
            information_key = environment.information_key(entry.state_key)
            previous = policy.setdefault(information_key, entry.action)
            if previous != entry.action:
                raise ValueError(
                    "one legal information state produced conflicting Teacher actions")
        _write_live_policy(Path(case.policy_path), policy.items())
        connection.send({"status": "completed", "result": result.dumps()})
    except Exception as exc:
        connection.send({
            "status": "error", "failure": f"{type(exc).__name__}: {exc}",
        })
    finally:
        connection.close()


class IsolatedTeacherSearcher:
    def __init__(self, *, model: TeacherModelRecord,
                 search_configuration: TeacherSearchConfiguration,
                 baseline_identity: str, root_timeout_seconds: float):
        self.model = model
        self.search_configuration = search_configuration
        self.baseline_identity = str(baseline_identity)
        self.root_timeout_seconds = float(root_timeout_seconds)

    def search(self, *, engine, perspective_seat: int, knowledge,
               experiment_seed: int, timeout_seconds: float | None = None):
        timeout = self.root_timeout_seconds
        if timeout_seconds is not None:
            timeout = min(timeout, float(timeout_seconds))
        if timeout <= 0:
            raise TeacherSearchUnavailable(
                TeacherStopReason.WORKER_TIMEOUT, "no time remains for Teacher root")
        with tempfile.TemporaryDirectory(prefix="teacher-live-policy-") as directory:
            policy_path = Path(directory) / "policy.json"
            case = LiveTeacherCase(
                case_id=f"live-{experiment_seed}", engine=engine,
                perspective_seat=int(perspective_seat), knowledge=knowledge,
                experiment_seed=int(experiment_seed), model=self.model,
                search_configuration=self.search_configuration,
                baseline_identity=self.baseline_identity, policy_path=str(policy_path))
            batch = TeacherBatchRunner(worker_target=_live_worker_entry).run(
                (case,), TeacherExecutionConfiguration(
                    workers=1, root_timeout_seconds=timeout))
            item = batch.items[0]
            if item.status is not TeacherWorkerStatus.COMPLETED or item.result is None:
                raise TeacherSearchUnavailable(
                    item.stop_reason, item.failure or "Teacher root returned no result")
            if not policy_path.is_file():
                raise TeacherSearchUnavailable(
                    TeacherStopReason.WORKER_ERROR,
                    "Teacher root returned no legal information policy")
            return LiveTeacherSearch(item.result, _load_live_policy(policy_path))


def _search_seed(base_seed: int, index: int, state_key: str) -> int:
    payload = f"{int(base_seed)}:{int(index)}:{state_key}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


class TeacherMatchAgent:
    def __init__(self, *, runtime, perspective_seat: int, base_seed: int,
                 searcher, result_sink=None, engine_source=None,
                 environment_factory=None):
        self.runtime = runtime
        self.perspective_seat = int(perspective_seat)
        self.base_seed = int(base_seed)
        self.searcher = searcher
        self.result_sink = result_sink
        self.engine_source = engine_source or self._live_engine
        self.environment_factory = environment_factory or TurnSearchEnvironment.from_engine
        self._policy = {}
        self._searches = 0
        self.episode_key = None
        self.last_telemetry = []
        self.last_telemetry_seconds = 0.0
        self.last_seconds = None
        self.last_timeout = False
        self.last_error = None

    @staticmethod
    def _live_engine():
        from cgpy.game import Battle

        if Battle.engine is None:
            raise RuntimeError("cgpy live engine is unavailable")
        return Battle.engine

    def begin_episode(self, episode_key: str) -> None:
        self.episode_key = str(episode_key)
        self._policy.clear()
        self._searches = 0

    def alive(self) -> bool:
        return True

    def close(self) -> None:
        return None

    @property
    def search_count(self) -> int:
        return self._searches

    def _selection(self, environment, action) -> list[int]:
        matches = tuple(candidate for candidate in environment.legal_actions(environment.root)
                        if candidate.identity == action)
        if len(matches) != 1:
            raise ValueError("Teacher policy action is not uniquely legal in the live state")
        return list(matches[0].selection)

    def act(self, observation: dict, timeout=None) -> list[int] | None:
        self.last_timeout = False
        self.last_error = None
        self.last_telemetry = []
        started = perf_counter()
        try:
            if int(observation["current"]["turn"]) <= 0:
                return list(self.runtime.decide(observation).chosen)
            state = self.runtime.observe(observation)
            engine = self.engine_source()
            environment = self.environment_factory(
                engine, perspective_seat=self.perspective_seat,
                knowledge=self.runtime.knowledge)
            information_key = state.decision_key
            action = self._policy.get(information_key)
            if action is None:
                seed = _search_seed(self.base_seed, self._searches, information_key)
                search = self.searcher.search(
                    engine=engine.fork() if hasattr(engine, "fork") else engine,
                    perspective_seat=self.perspective_seat,
                    knowledge=self.runtime.knowledge, experiment_seed=seed,
                    timeout_seconds=timeout)
                result = search.result
                search_index = self._searches
                self._searches += 1
                if self.result_sink is not None:
                    self.result_sink(search_index, result)
                if result.coverage is not TeacherCoverage.COMPLETE \
                        or result.preferred_action is None:
                    raise RuntimeError(
                        f"Teacher search {result.coverage.value} "
                        f"({result.stop_reason.value}): {result.failure or 'no preferred action'}")
                for key, selected in search.policy:
                    previous = self._policy.setdefault(key, selected)
                    if previous != selected:
                        raise RuntimeError(
                            "one legal information state produced conflicting Teacher actions")
                action = self._policy.get(information_key)
                if action is None:
                    raise RuntimeError(
                        "complete Teacher policy omitted its live legal information state")
            return self._selection(environment, action)
        except TeacherSearchUnavailable as exc:
            self.last_timeout = exc.stop_reason is TeacherStopReason.WORKER_TIMEOUT
            self.last_error = f"Teacher search unavailable ({exc.stop_reason.value}): {exc}"
            return None
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            return None
        finally:
            self.last_seconds = perf_counter() - started


__all__ = (
    "IsolatedTeacherSearcher", "LiveTeacherCase", "LiveTeacherSearch", "TeacherMatchAgent",
    "TeacherSearchUnavailable",
)
