from types import SimpleNamespace

from common.api import ActionIdentity
from common.decision import EvaluationStatus
from common.ledger import EvaluationModel
from cgpy.experiment import (
    TeacherCoverage, TeacherModelRecord, TeacherSearchConfiguration,
    TeacherStopReason,
)
from teacher_helpers import end_only_snapshot


class _Engine:
    key = "root-a"


class _Runtime:
    def __init__(self, engine):
        self.engine = engine
        self.knowledge = "legal-knowledge"
        self.observed = []
        self.pregame = []

    def decide(self, observation):
        self.pregame.append(observation)
        return SimpleNamespace(chosen=(3,))

    def observe(self, observation):
        self.observed.append(observation)
        self.engine.key = observation["key"]
        return SimpleNamespace(
            turn=SimpleNamespace(number=observation["current"]["turn"]),
            decision_key=observation.get("information_key", observation["key"]))


class _Environment:
    def __init__(self, engine, *, perspective_seat, knowledge):
        self.root = object()
        self.engine = engine
        self.perspective_seat = perspective_seat
        self.knowledge = knowledge

    def state_key(self, _node):
        return SimpleNamespace(digest=self.engine.key)

    def legal_actions(self, _node):
        return (
            SimpleNamespace(identity=ActionIdentity("pick", (("name", "a"),)),
                            selection=(1,)),
            SimpleNamespace(identity=ActionIdentity("pick", (("name", "b"),)),
                            selection=(2,)),
        )


def _result(root, chosen, extra=()):
    action = ActionIdentity("pick", (("name", chosen),))
    policy = [SimpleNamespace(state_key=root, action=action)]
    policy.extend(SimpleNamespace(
        state_key=key, action=ActionIdentity("pick", (("name", name),)))
                  for key, name in extra)
    return SimpleNamespace(
        root_state_key=root, preferred_action=action, selected_policy=tuple(policy),
        coverage=TeacherCoverage.COMPLETE, value_quality=EvaluationStatus.COMPLETE,
        stop_reason=TeacherStopReason.COMPLETE, failure=None,
    )


class _Searcher:
    def __init__(self, results):
        self.results = iter(results)
        self.calls = []

    def search(self, **request):
        from sim.teacher_agent import LiveTeacherSearch

        self.calls.append(request)
        result = next(self.results)
        policy = tuple((entry.state_key, entry.action) for entry in result.selected_policy)
        return LiveTeacherSearch(result, policy)


def test_teacher_agent_reuses_policy_and_researches_an_uncovered_live_state():
    from sim.teacher_agent import TeacherMatchAgent

    engine = _Engine()
    runtime = _Runtime(engine)
    searcher = _Searcher([
        _result("root-a", "a", (("covered-b", "b"),)),
        _result("uncovered-c", "b"),
    ])
    saved = []
    agent = TeacherMatchAgent(
        runtime=runtime, perspective_seat=1, base_seed=654,
        searcher=searcher, engine_source=lambda: engine,
        environment_factory=_Environment,
        result_sink=lambda index, result: saved.append((index, result.root_state_key)),
    )

    assert agent.act({"key": "root-a", "current": {"turn": 1}}) == [1]
    assert agent.act({"key": "covered-b", "current": {"turn": 1}}) == [2]
    assert agent.act({"key": "uncovered-c", "current": {"turn": 1}}) == [2]

    assert len(searcher.calls) == 2
    assert [call["knowledge"] for call in searcher.calls] == [
        "legal-knowledge", "legal-knowledge"]
    assert [call["perspective_seat"] for call in searcher.calls] == [1, 1]
    assert saved == [(0, "root-a"), (1, "uncovered-c")]


def test_teacher_agent_policy_is_invariant_to_hidden_engine_permutations():
    from sim.teacher_agent import TeacherMatchAgent

    engine = _Engine()
    runtime = _Runtime(engine)
    searcher = _Searcher([_result("visible-state", "a")])
    agent = TeacherMatchAgent(
        runtime=runtime, perspective_seat=0, base_seed=654, searcher=searcher,
        engine_source=lambda: engine, environment_factory=_Environment)

    assert agent.act({
        "key": "hidden-permutation-a", "information_key": "visible-state",
        "current": {"turn": 1},
    }) == [1]
    assert agent.act({
        "key": "hidden-permutation-b", "information_key": "visible-state",
        "current": {"turn": 1},
    }) == [1]

    assert len(searcher.calls) == 1


def test_live_policy_sidecar_handles_more_than_a_pipe_buffer(tmp_path):
    from sim.teacher_agent import _load_live_policy, _write_live_policy

    action = ActionIdentity("pick", (("name", "a"),))
    policy = tuple((f"information-{index:06d}", action) for index in range(10_000))
    path = tmp_path / "policy.json"

    _write_live_policy(path, policy)

    assert path.stat().st_size > 64 * 1024
    assert _load_live_policy(path) == policy


def test_teacher_agent_delegates_pregame_without_starting_search():
    from sim.teacher_agent import TeacherMatchAgent

    engine = _Engine()
    runtime = _Runtime(engine)
    searcher = _Searcher([])
    agent = TeacherMatchAgent(
        runtime=runtime, perspective_seat=0, base_seed=1, searcher=searcher,
        engine_source=lambda: engine, environment_factory=_Environment)
    observation = {"key": "pregame", "current": {"turn": 0}}

    assert agent.act(observation) == [3]
    assert runtime.pregame == [observation]
    assert runtime.observed == []
    assert searcher.calls == []


def test_teacher_agent_rejects_incomplete_search_without_fallback():
    from sim.teacher_agent import TeacherMatchAgent

    engine = _Engine()
    runtime = _Runtime(engine)
    failed = SimpleNamespace(
        root_state_key="root-a", preferred_action=None, selected_policy=(),
        coverage=TeacherCoverage.INCOMPLETE,
        value_quality=EvaluationStatus.UNAVAILABLE,
        stop_reason=TeacherStopReason.NODE_CAP, failure="teacher node cap reached",
    )
    saved = []
    agent = TeacherMatchAgent(
        runtime=runtime, perspective_seat=0, base_seed=1,
        searcher=_Searcher([failed]), engine_source=lambda: engine,
        environment_factory=_Environment,
        result_sink=lambda index, result: saved.append((index, result.coverage)),
    )

    assert agent.act({"key": "root-a", "current": {"turn": 1}}) is None
    assert "incomplete" in agent.last_error
    assert "node_cap" in agent.last_error
    assert agent.last_timeout is False
    assert saved == [(0, TeacherCoverage.INCOMPLETE)]


def test_teacher_agent_reports_an_isolated_worker_timeout_without_fallback():
    from sim.teacher_agent import TeacherMatchAgent, TeacherSearchUnavailable

    class TimedOutSearcher:
        def search(self, **_request):
            raise TeacherSearchUnavailable(
                TeacherStopReason.WORKER_TIMEOUT, "root exceeded its outer timeout")

    runtime = _Runtime(_Engine())
    agent = TeacherMatchAgent(
        runtime=runtime, perspective_seat=0, base_seed=1,
        searcher=TimedOutSearcher(), engine_source=lambda: runtime.engine,
        environment_factory=_Environment,
    )

    assert agent.act({"key": "root-a", "current": {"turn": 1}}) is None
    assert agent.last_timeout is True
    assert "worker_timeout" in agent.last_error
    assert runtime.pregame == []


def test_teacher_agent_rejects_a_policy_action_missing_from_the_legal_menu():
    from sim.teacher_agent import TeacherMatchAgent

    engine = _Engine()
    runtime = _Runtime(engine)
    agent = TeacherMatchAgent(
        runtime=runtime, perspective_seat=0, base_seed=1,
        searcher=_Searcher([_result("root-a", "missing")]),
        engine_source=lambda: engine, environment_factory=_Environment)

    assert agent.act({"key": "root-a", "current": {"turn": 1}}) is None
    assert "not uniquely legal" in agent.last_error


def test_isolated_searcher_runs_a_live_engine_root_in_a_spawned_process():
    from sim.teacher_agent import IsolatedTeacherSearcher

    snapshot = end_only_snapshot("mega_starmie")
    searcher = IsolatedTeacherSearcher(
        model=TeacherModelRecord.from_model(EvaluationModel.build()),
        search_configuration=TeacherSearchConfiguration(),
        baseline_identity="frozen-test-baseline",
        root_timeout_seconds=30.0,
    )

    search = searcher.search(
        engine=snapshot.fork_engine(),
        perspective_seat=snapshot.observation.seat,
        knowledge=snapshot.observation.knowledge,
        experiment_seed=654,
    )

    assert search.result.coverage is TeacherCoverage.COMPLETE
    assert search.result.preferred_action is not None
    assert dict(search.policy)[snapshot.observation.decision_key] == \
        search.result.preferred_action
